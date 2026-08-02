"""OCR fallback for scanned/image-only PDFs.

PdfChunker (PyMuPDF text blocks + pdfplumber tables) returns zero chunks for
pages that are just a scanned image with no text layer — silently, since
that's a legitimate PDF, not a parse error. This module renders each such
page to an image and asks a vision model to transcribe it.

Two passes per page, deliberately by two DIFFERENT models
-------------------------------------------------------
1. **Structured pass** (`openrouter_vision_table_model`) asks for HTML
   `<table>` markup, so a scanned price annex produces real TABLE chunks
   that go through the same `_detect_header` / `_parse_data_rows` path as a
   text-layer PDF — and therefore reaches `material_prices`. Before this,
   OCR output was plain text only: a scanned price list became searchable
   prose and contributed zero price rows.

2. **Plain pass** (`openrouter_vision_model`, cheaper) transcribes the same
   image as flat text and is used *only* to cross-check the numbers in the
   structured output.

Using two different models is the point. A model asked to emit table markup
can invent a cell to make a row "come out even", and a second opinion from
the same model would repeat the same invention. Any money-like number in the
HTML that does not also appear in the independent plain transcription is
blanked — the cell becomes empty rather than carrying a number nothing
corroborates. A missing price reports as "no data"; a hallucinated one
becomes a wrong construction cost.

Only invoked when normal extraction yields no chunks at all — running a
vision model per page on every PDF would be slow and unnecessary for the
documents that already have a real text layer.
"""

from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass, field

from app.config import settings
from app.core.chunking.base import add_table_context, count_tokens, naive_merge_with_origins
from app.core.chunking.models import Chunk, ChunkType
from app.core.llm.openrouter import OpenRouterClient

logger = logging.getLogger(__name__)

_RENDER_DPI = 200

_TABLE_BLOCK_RE = re.compile(r"<table\b.*?</table>", re.IGNORECASE | re.DOTALL)
_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_CELL_RE = re.compile(r"<t([dh])\b[^>]*>(.*?)</t\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")

# Money-like tokens: at least 4 digits with Vietnamese grouping, or a plain
# run of 4+ digits. Short numbers (row indices, "50kg", "0%") are excluded —
# they are everywhere, would match by accident, and are not what a wrong
# transcription costs money on.
_MONEY_RE = re.compile(r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d{4,}")

TABLE_OCR_PROMPT = (
    "Transcribe this document page exactly as printed.\n"
    "- Prose, headings and notes: plain text lines.\n"
    "- EVERY table: output HTML <table>...</table>. One <tr> per visual row, "
    "one <td> per column. Every <tr> must have the same number of <td> as the "
    "widest row of that table.\n"
    "- A cell merged ACROSS ROWS: repeat its value in every row it spans.\n"
    "- A cell merged ACROSS COLUMNS: repeat its value in every column it spans.\n"
    "- A table with a multi-level header: output EVERY header row as its own "
    "<tr>, do not collapse them into one. A group heading such as "
    "'Giá bán (chưa bao gồm thuế...)' spanning four sub-columns must appear in "
    "all four cells of the upper header row, with the sub-labels underneath it "
    "in the next <tr>.\n"
    "- An empty cell: <td></td>.\n"
    "- Copy every number EXACTLY as printed, keeping the original separators. "
    "Never compute, round, reformat or invent a number. If a cell is "
    "unreadable, leave it empty rather than guessing.\n"
    "- Output only the transcription, no commentary."
)


@dataclass
class OcrResult:
    """Chunks for retrieval plus the tables, in the shape the price extractor
    consumes (`iter_price_tables`), so scanned price lists reach
    material_prices instead of only becoming searchable text."""

    chunks: list[Chunk] = field(default_factory=list)
    tables: list[tuple[str, list[list[str]], list[list[str]]]] = field(default_factory=list)
    pages_ocred: int = 0
    cells_blanked: int = 0


def _strip_tags(html: str) -> str:
    return _TAG_RE.sub(" ", html).replace("&nbsp;", " ").strip()


def _numbers(text: str) -> set[str]:
    """Money-like tokens, normalised so 1.287.037 and 1,287,037 compare equal."""
    return {m.group(0).replace(",", "").replace(".", "") for m in _MONEY_RE.finditer(text)}


def _parse_tables(text: str) -> tuple[list[list[list[str]]], str]:
    """Split a page transcription into (tables, remaining prose)."""
    tables: list[list[list[str]]] = []
    for block in _TABLE_BLOCK_RE.findall(text):
        grid: list[list[str]] = []
        for row_html in _ROW_RE.findall(block):
            # group(1) is the tag letter (d|h); group(2) is the cell content.
            grid.append([_strip_tags(c.group(2)) for c in _CELL_RE.finditer(row_html)])
        grid = [r for r in grid if any(c.strip() for c in r)]
        if len(grid) >= 2:
            tables.append(grid)
    return tables, _TABLE_BLOCK_RE.sub("\n", text).strip()


def _normalise(grid: list[list[str]]) -> list[list[str]]:
    """Pad every row to the table's modal width.

    Rows short by a cell or two are the common failure mode; padding on the
    right keeps the leading columns (STT, name, unit) aligned, which is what
    the column mapping depends on. Rows LONGER than modal are left alone —
    truncating them could silently drop a price."""
    if not grid:
        return grid
    widths = [len(r) for r in grid]
    modal = max(set(widths), key=widths.count)
    return [r + [""] * (modal - len(r)) if len(r) < modal else r for r in grid]


def _verify(grid: list[list[str]], corroborated: set[str]) -> tuple[list[list[str]], int]:
    """Blank any money-like cell whose number is absent from the plain pass.

    Blanking the cell rather than dropping the row keeps the material name and
    every corroborated figure on that row; the uncorroborated price simply
    reports as missing, which the price extractor already handles honestly."""
    blanked = 0
    out: list[list[str]] = []
    for row in grid:
        new_row = []
        for cell in row:
            nums = _numbers(cell)
            if nums and not nums.issubset(corroborated):
                blanked += 1
                new_row.append("")
            else:
                new_row.append(cell)
        out.append(new_row)
    return out, blanked


def _to_html(grid: list[list[str]]) -> str:
    lines = ["<table>"]
    for i, row in enumerate(grid):
        tag = "th" if i == 0 else "td"
        lines.append("<tr>" + "".join(f"<{tag}>{c.strip()}</{tag}>" for c in row) + "</tr>")
    lines.append("</table>")
    return "\n".join(lines)


async def ocr_pdf_to_document(
    content: bytes,
    filename: str,
    document_id: str,
    kb_id: str,
    chunk_token_num: int = 512,
    overlap_percent: int = 15,
    table_context_size: int = 128,
) -> OcrResult:
    # Imported here rather than at module scope so the parsing helpers
    # above stay importable (and unit-testable) without PyMuPDF present.
    import fitz  # PyMuPDF

    llm = OpenRouterClient()
    table_model = settings.openrouter_vision_table_model or settings.openrouter_vision_model

    # (page_index, kind, payload) in reading order, so tables stay between the
    # paragraphs they belong to — the same ordering PdfChunker builds by y.
    items: list[dict] = []
    result = OcrResult()

    with fitz.open(stream=content, filetype="pdf") as doc:
        for page_idx, page in enumerate(doc):
            pixmap = page.get_pixmap(dpi=_RENDER_DPI)
            image_b64 = base64.b64encode(pixmap.tobytes("png")).decode("ascii")

            try:
                structured = await llm.vision_ocr(
                    image_b64, model=table_model, prompt=TABLE_OCR_PROMPT, max_tokens=8192
                )
            except Exception as exc:
                logger.warning(
                    "OCR (structured) failed file=%s page=%d: %s — skipping page",
                    filename,
                    page_idx,
                    exc,
                )
                continue
            if not structured:
                continue
            result.pages_ocred += 1

            tables, prose = _parse_tables(structured)

            corroborated: set[str] = set()
            if tables:
                # Only worth a second call when there is structure to check.
                try:
                    plain = await llm.vision_ocr(image_b64)
                    corroborated = _numbers(plain)
                except Exception as exc:
                    logger.warning(
                        "OCR (plain cross-check) failed file=%s page=%d: %s — "
                        "keeping the structured numbers unverified",
                        filename,
                        page_idx,
                        exc,
                    )
                    corroborated = None  # type: ignore[assignment]

            if prose:
                items.append({"page": page_idx, "kind": "text", "text": prose})

            for t_idx, grid in enumerate(tables):
                grid = _normalise(grid)
                if corroborated is not None:
                    grid, blanked = _verify(grid, corroborated)
                    result.cells_blanked += blanked
                items.append({"page": page_idx, "kind": "table", "grid": grid})
                result.tables.append((f"page {page_idx + 1} bảng {t_idx + 1}", grid, grid))

    if not items:
        logger.warning("OCR found no readable content in any page of %s", filename)
        return result

    # Same assembly as PdfChunker: consecutive prose merges into token-bounded
    # chunks, each table stays its own chunk, then tables get their
    # surrounding text as context.
    assembled: list[dict] = []
    text_buffer: list[str] = []
    page_buffer: list[int] = []

    def flush_text() -> None:
        if not text_buffer:
            return
        for text, origin in naive_merge_with_origins(
            text_buffer, chunk_token_num=chunk_token_num, overlap_percent=overlap_percent
        ):
            assembled.append(
                {
                    "text": text,
                    "chunk_type": ChunkType.TEXT,
                    "page": page_buffer[origin] if origin < len(page_buffer) else 0,
                }
            )
        text_buffer.clear()
        page_buffer.clear()

    for item in items:
        if item["kind"] == "text":
            text_buffer.append(item["text"])
            page_buffer.append(item["page"])
        else:
            flush_text()
            assembled.append(
                {
                    "text": _to_html(item["grid"]),
                    "chunk_type": ChunkType.TABLE,
                    "page": item["page"],
                }
            )
    flush_text()

    add_table_context(assembled, table_context_size)

    result.chunks = [
        Chunk(
            content=a["text"],
            chunk_type=a["chunk_type"],
            document_id=document_id,
            kb_id=kb_id,
            filename=filename,
            page_num=a.get("page", 0),
            context_above=a.get("context_above", ""),
            context_below=a.get("context_below", ""),
            token_count=count_tokens(a["text"]),
            metadata={"source": "ocr"},
        )
        for a in assembled
    ]

    logger.info(
        "OCR fallback: %s -> %d page(s), %d chunk(s) (%d bảng), %d ô bị làm trống do "
        "không đối chiếu được",
        filename,
        result.pages_ocred,
        len(result.chunks),
        len(result.tables),
        result.cells_blanked,
    )
    return result


async def ocr_pdf_to_chunks(
    content: bytes,
    filename: str,
    document_id: str,
    kb_id: str,
    chunk_token_num: int = 512,
    overlap_percent: int = 15,
) -> list[Chunk]:
    """Chunks only — kept for callers that don't need the extracted tables."""
    res = await ocr_pdf_to_document(
        content,
        filename,
        document_id,
        kb_id,
        chunk_token_num=chunk_token_num,
        overlap_percent=overlap_percent,
    )
    return res.chunks
