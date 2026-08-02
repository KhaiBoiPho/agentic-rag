"""Source-format adapters that feed the price extractor a uniform grid.

`extract_price_rows` used to call pdfplumber directly, which had two
consequences beyond "PDF only":

  * Uploading a .md or .docx into a price-extraction KB raised inside
    pdfplumber, and PriceExtractionPipeline turned that into
    `status = error` for the whole document — the RAG chunks were already in
    Qdrant, so the document looked broken while actually being searchable.
  * The Markdown price lists in this corpus (HoChiMinh-BangGiaVLXD-*.md,
    BaoGia-DoanhNghiepVLXD-ToanQuoc-2026.md) are real published price tables
    and never reached material_prices at all. That is why HCM had 38 price
    rows against Hà Nội's 6.601.

Every adapter yields `(page_label, resolved_grid, raw_grid)`:

  resolved — merged cells filled down, ditto markers ("-nt-") expanded
  raw      — the same block untouched, so the caller can still recognise a
             group-heading row by its emptiness (see price_extractor
             _parse_data_rows)

For PDF the two differ because of real merged cells (geometry from
pdfplumber). For Markdown they differ only by ditto expansion — the format
has no merged cells. For DOCX python-docx already repeats a merged cell's
text across every grid position it covers, so `resolved` comes free and the
raw grid is reconstructed by blanking positions that continue a vertical
merge (identified by the underlying `<w:tc>` element being the same object).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from io import BytesIO

from app.core.chunking.table_extract import extract_tables_with_raw, is_ditto

Grid = list[list[str]]
TableTriple = tuple[str, Grid, Grid]


def iter_price_tables(content: bytes, filename: str) -> Iterator[TableTriple]:
    """Dispatch on file extension. Unknown extensions yield nothing, which the
    caller reports as "0 price rows" rather than an error."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "pdf":
        yield from _from_pdf(content)
    elif ext in {"docx", "doc"}:
        yield from _from_docx(content)
    elif ext in {"md", "markdown", "txt"}:
        yield from _from_markdown(content)


# ─── PDF ────────────────────────────────────────────────────────────────────


def _from_pdf(content: bytes) -> Iterator[TableTriple]:
    import pdfplumber

    with pdfplumber.open(BytesIO(content)) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            for resolved, raw in extract_tables_with_raw(page):
                if resolved:
                    yield f"page {page_idx + 1}", resolved, raw


# ─── DOCX ───────────────────────────────────────────────────────────────────


def _from_docx(content: bytes) -> Iterator[TableTriple]:
    from docx import Document

    doc = Document(BytesIO(content))
    for table_idx, table in enumerate(doc.tables):
        resolved: Grid = []
        raw: Grid = []
        prev_tcs: list[object] = []
        for row in table.rows:
            cells = list(row.cells)
            # These KB documents were converted from Markdown that itself came
            # from a PDF→MD tool, so the LaTeX artefacts survive the round trip
            # into .docx as well — strip them here too, not just in _from_markdown.
            resolved_row = [_strip_latex(c.text.strip()) for c in cells]
            # A vertically merged cell is handed back by python-docx as the
            # same <w:tc> element on every row it spans, with the text
            # repeated. Same element as the row above => continuation.
            raw_row = [
                "" if i < len(prev_tcs) and cells[i]._tc is prev_tcs[i] else resolved_row[i]
                for i in range(len(cells))
            ]
            resolved.append(_expand_ditto(resolved_row, resolved))
            raw.append(raw_row)
            prev_tcs = [c._tc for c in cells]
        if resolved:
            yield f"table {table_idx + 1}", resolved, raw


# ─── Markdown ───────────────────────────────────────────────────────────────

_MD_SEPARATOR_RE = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")

# These Markdown files were produced by a PDF→MD converter that emitted LaTeX
# math for symbols and units, so raw cells read "Thép cuộn $\phi$ 6" and
# "$\mathrm{đồng/m^3}$". Left alone, that lands in material_name/unit and both
# breaks the ILIKE lookup and shows up verbatim in a quote to the user.
_LATEX_CMD_RE = re.compile(r"\\(?:mathrm|mathbf|mathit|text|textbf|rm)\s*\{([^{}]*)\}")
_LATEX_SYMBOLS = {
    r"\phi": "Ø",
    r"\Phi": "Ø",
    r"\times": "x",
    r"\pm": "±",
    r"\le": "≤",
    r"\ge": "≥",
    r"\%": "%",
    r"\,": " ",
    r"\ ": " ",
}
_SUPERSCRIPT_RE = re.compile(r"\^\{?(\d)\}?")


def _strip_latex(text: str) -> str:
    if "$" not in text and "\\" not in text:
        return text
    out = _LATEX_CMD_RE.sub(r"\1", text)
    for cmd, repl in _LATEX_SYMBOLS.items():
        out = out.replace(cmd, repl)
    out = _SUPERSCRIPT_RE.sub(r"\1", out)
    out = out.replace("$", "")
    return re.sub(r"\s+", " ", out).strip()


def _from_markdown(content: bytes) -> Iterator[TableTriple]:
    text = content.decode("utf-8", errors="replace")
    block: list[str] = []
    table_idx = 0

    def flush() -> Iterator[TableTriple]:
        nonlocal table_idx, block
        # A single "| … |" line is not a table; a real one has a header, a
        # separator and at least one data row.
        if len(block) >= 3:
            grid = [_split_md_row(line) for line in block if not _MD_SEPARATOR_RE.match(line)]
            grid = [r for r in grid if any(c.strip() for c in r)]
            if len(grid) >= 2:
                table_idx += 1
                raw = [list(r) for r in grid]
                resolved: Grid = []
                for row in grid:
                    resolved.append(_expand_ditto(row, resolved))
                yield f"table {table_idx}", resolved, raw
        block = []

    for line in text.splitlines():
        if line.lstrip().startswith("|"):
            block.append(line)
        elif block:
            yield from flush()
    yield from flush()


def _split_md_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    # A price cell may hold several regional variants separated by <br>
    # ("1,726,852 (Hồ Chí Minh) <br> 1,504,630 (HCM Phú Hòa Đông)"). Keep only
    # the first: the extractor stores one price per row, and inventing rows
    # for the rest would attribute them to the wrong locality.
    return [
        _strip_latex(re.split(r"<br\s*/?>", c, maxsplit=1)[0].strip()) for c in stripped.split("|")
    ]


def _expand_ditto(row: list[str], previous: Grid) -> list[str]:
    """Replace "-nt-"/"như trên" with the value from the nearest row above.

    Bare "-" is left alone here for the same reason as in table_extract: only
    the unit column can safely read it as a repeat, and that decision belongs
    to the extractor which knows which column is the unit."""
    out = list(row)
    for i, cell in enumerate(out):
        if not is_ditto(cell):
            continue
        for prev in reversed(previous):
            if i < len(prev) and prev[i] and not is_ditto(prev[i]):
                out[i] = prev[i]
                break
    return out
