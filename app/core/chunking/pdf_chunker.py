"""PDF chunker — layout-aware text + table extraction.

Strategy (RAGFlow-inspired):
  1. Use pdfplumber for table extraction + table bounding boxes per page.
  2. Use PyMuPDF (fitz) for text blocks, dropping blocks that fall inside a
     table's bbox (their content is already carried, with row/column
     structure intact, by the table chunk).
  3. Interleave text sections and table chunks in reading order.
  4. Apply naive_merge to text sections, keep tables as standalone chunks.
  5. Attach table_context_size tokens of surrounding text to each table chunk.

Tables that continue across a page break are handled explicitly: pdfplumber
sees one table per page, so without help the first data row of every
continuation page would be emitted as the header row. See _resolve_header().
"""

from __future__ import annotations

import re
from io import BytesIO

import fitz  # PyMuPDF
import pdfplumber

from app.core.chunking.base import (
    BaseChunker,
    add_table_context,
    count_tokens,
    naive_merge_with_origins,
)
from app.core.chunking.models import Chunk, ChunkType
from app.core.chunking.table_extract import extract_tables_resolved, repair_spaced_number

# A text block whose centre lies inside a table's bbox is table content that
# PyMuPDF reported as loose text. The margin absorbs the small disagreement
# between pdfplumber's ruling-line bbox and PyMuPDF's glyph-run bbox.
_TABLE_BBOX_MARGIN = 2.0

_MAX_HEADER_CELL_LEN = 60

# A header row labels columns; a material-group heading row ("Thiết bị điện |
# - | Cty CP Bảo Phước") is also short, textual and price-free, so shape alone
# cannot tell them apart. Requiring at least one recognisable column label
# does — and when nothing matches, emitting no <th> is the safe outcome.
_HEADER_LABELS = (
    "stt",
    "tt",
    "số tt",
    "tên",
    "danh mục",
    "nhóm",
    "quy cách",
    "đơn vị",
    "đvt",
    "giá",
    "đơn giá",
    "tiêu chuẩn",
    "nhà sản xuất",
    "xuất xứ",
    "ghi chú",
    "vận chuyển",
    "thành tiền",
    "khối lượng",
    "mã hiệu",
)


class PdfChunker(BaseChunker):
    def chunk(self, filename: str, content: bytes, **kwargs) -> list[Chunk]:
        doc_id = kwargs.get("document_id", "")
        kb_id = kwargs.get("kb_id", "")

        raw_items = self._extract_ordered(content)
        merged = self._merge_and_contextualize(raw_items)

        chunks: list[Chunk] = []
        for item in merged:
            c = Chunk(
                content=item["text"],
                chunk_type=item["chunk_type"],
                document_id=doc_id,
                kb_id=kb_id,
                filename=filename,
                page_num=item.get("page", 0),
                context_above=item.get("context_above", ""),
                context_below=item.get("context_below", ""),
                token_count=count_tokens(item["text"]),
            )
            chunks.append(c)

        return chunks

    # ─── Internal ────────────────────────────────────────────────────────────

    def _extract_ordered(self, content: bytes) -> list[dict]:
        """Return list of {page, y, text, chunk_type} sorted in reading order."""
        items: list[dict] = []

        # Tables first: their bboxes are needed to filter the text blocks.
        with pdfplumber.open(BytesIO(content)) as pdf:
            table_by_page, bbox_by_page = self._extract_tables(pdf)

        with fitz.open(stream=content, filetype="pdf") as pdf_doc:
            text_by_page = self._extract_text_blocks(pdf_doc, bbox_by_page)

        all_pages = set(text_by_page.keys()) | set(table_by_page.keys())
        for page_idx in sorted(all_pages):
            page_items: list[dict] = []

            for block in text_by_page.get(page_idx, []):
                page_items.append(
                    {
                        "page": page_idx,
                        "y": block["y"],
                        "text": block["text"],
                        "chunk_type": ChunkType.TEXT,
                    }
                )

            for tbl in table_by_page.get(page_idx, []):
                page_items.append(
                    {
                        "page": page_idx,
                        "y": tbl["y"],
                        "text": tbl["text"],
                        "chunk_type": ChunkType.TABLE,
                    }
                )

            # sort by vertical position within each page
            page_items.sort(key=lambda x: x["y"])
            items.extend(page_items)

        return items

    def _extract_text_blocks(
        self, doc: fitz.Document, bbox_by_page: dict[int, list[tuple]]
    ) -> dict[int, list[dict]]:
        result: dict[int, list[dict]] = {}
        for page_idx, page in enumerate(doc):
            blocks = page.get_text("blocks")
            boxes = bbox_by_page.get(page_idx, [])
            result[page_idx] = []
            for b in blocks:
                # b = (x0, y0, x1, y1, text, block_no, block_type)
                text = b[4].strip()
                if not text or b[6] != 0:  # skip image blocks
                    continue
                if _in_any_bbox(b, boxes):
                    # Already represented — with its row/column relationships —
                    # by the table chunk for this region. Keeping it would both
                    # duplicate the content and, because PyMuPDF emits table
                    # cells as independent blocks in unpredictable order, feed
                    # scrambled cell fragments into neighbouring text chunks
                    # and into table context_above/context_below.
                    continue
                result[page_idx].append({"y": b[1], "text": text})
        return result

    def _extract_tables(
        self, pdf: pdfplumber.PDF
    ) -> tuple[dict[int, list[dict]], dict[int, list[tuple]]]:
        """Returns ({page: [{y, text}]}, {page: [bbox]}).

        Merged cells are filled down and ditto markers expanded before the
        grid is rendered to HTML — see table_extract.extract_tables_resolved.
        """
        result: dict[int, list[dict]] = {}
        bboxes: dict[int, list[tuple]] = {}

        prev_header: list[str] | None = None
        prev_ncol: int | None = None

        for page_idx, page in enumerate(pdf.pages):
            grids = extract_tables_resolved(page)
            if not grids:
                continue
            page_tables = page.find_tables()
            result[page_idx] = []
            bboxes[page_idx] = []

            for i, grid in enumerate(grids):
                if not grid:
                    continue
                header, body, prev_header, prev_ncol = _resolve_header(grid, prev_header, prev_ncol)
                html = self._table_to_html(header, body)
                if not html:
                    continue
                bbox = page_tables[i].bbox if i < len(page_tables) else None
                y = bbox[1] if bbox else 0
                result[page_idx].append({"y": y, "text": html})
                if bbox:
                    bboxes[page_idx].append(bbox)

        return result, bboxes

    def _table_to_html(self, header: list[str] | None, body: list[list[str]]) -> str:
        """Render lưới đã giải ô gộp thành HTML, có sửa số bị lỗi font.

        Sửa số ở đây là bắt buộc chứ không phải làm đẹp: cùng một ô giá đang
        đi ra hai đường dưới hai dạng khác nhau — `material_prices` lưu 12180
        (vì `_parse_price` đã nối lại) trong khi chunk đem embed giữ nguyên
        chuỗi hỏng "1 2.180". Model đọc chunk vì thế không đọc ra được con số,
        và mọi phép đo dựa trên khớp chuỗi cũng tưởng dòng đó biến mất.
        """
        if not header and not body:
            return ""
        html = ["<table>"]
        if header:
            cells = "".join(f"<th>{repair_spaced_number(c.strip())}</th>" for c in header)
            html.append(f"<tr>{cells}</tr>")
        for row in body:
            cells = "".join(f"<td>{repair_spaced_number(c.strip())}</td>" for c in row)
            html.append(f"<tr>{cells}</tr>")
        html.append("</table>")
        return "\n".join(html)

    def _merge_and_contextualize(self, items: list[dict]) -> list[dict]:
        """Merge text items, keep tables standalone, then add context to tables."""
        # Split into groups: consecutive text items are merged; tables are kept separate.
        result: list[dict] = []
        text_buffer: list[str] = []
        page_buffer: list[int] = []

        def flush_text():
            if not text_buffer:
                return
            # Each merged chunk reports the page of the FIRST section that went
            # into it. Tracking origins matters because the buffer can span
            # several pages before a table interrupts it — attributing every
            # resulting chunk to the last page seen would put the citation
            # dozens of pages away from the text it quotes.
            for text, origin_idx in naive_merge_with_origins(
                text_buffer,
                chunk_token_num=self.chunk_token_num,
                delimiter=self.delimiter,
                overlap_percent=self.overlap_percent,
            ):
                result.append(
                    {
                        "text": text,
                        "chunk_type": ChunkType.TEXT,
                        "page": page_buffer[origin_idx] if origin_idx < len(page_buffer) else 0,
                    }
                )
            text_buffer.clear()
            page_buffer.clear()

        for item in items:
            if item["chunk_type"] == ChunkType.TEXT:
                text_buffer.append(item["text"])
                page_buffer.append(item["page"])
            else:
                flush_text()
                result.append(item)

        flush_text()

        # Add context to table chunks
        add_table_context(result, self.table_context_size)
        return result


def _in_any_bbox(block, boxes: list[tuple]) -> bool:
    cx = (block[0] + block[2]) / 2
    cy = (block[1] + block[3]) / 2
    for x0, top, x1, bottom in boxes:
        if (
            x0 - _TABLE_BBOX_MARGIN <= cx <= x1 + _TABLE_BBOX_MARGIN
            and top - _TABLE_BBOX_MARGIN <= cy <= bottom + _TABLE_BBOX_MARGIN
        ):
            return True
    return False


def _looks_like_header(row: list[str]) -> bool:
    """A header row carries several short column labels and no prices."""
    cells = [c.strip() for c in row]
    non_empty = [c for c in cells if c]
    if len(non_empty) < 2:
        return False
    # Ô bị trộn chữ không được phép tước tư cách tiêu đề của cả hàng: nó dài
    # bất thường nên luôn vượt _MAX_HEADER_CELL_LEN, và bảng công bố giá vì thế
    # bị bỏ tiêu đề hoàn toàn — hàng nhãn bị đẩy xuống thành hàng dữ liệu.
    readable = [c for c in non_empty if not _scrambled(c)]
    if not readable:
        return False
    if any(len(c) > _MAX_HEADER_CELL_LEN for c in readable):
        return False
    # A cell that is purely a formatted number (e.g. "4.250.000") means this
    # is a data row, not a header.
    if any(c.replace(".", "").replace(",", "").isdigit() for c in non_empty):
        return False
    lowered = [c.lower() for c in readable]
    return any(label in cell for cell in lowered for label in _HEADER_LABELS)


_COL_NUM_RE = re.compile(r"^\[?\(?\d+\)?\]?$")


def _is_number_cell(cell: str) -> bool:
    return bool(cell) and cell.replace(".", "").replace(",", "").isdigit()


def _scrambled(cell: str) -> bool:
    """Ô tiêu đề bị pdfplumber rải xen kẽ chữ giữa các cột kề nhau.

    Khi tiêu đề có ô gộp trải trên nhiều cột con, phần chữ xuống dòng của các
    cột đó nằm cùng một dải toạ độ, và pdfplumber trả về chúng đan vào nhau:

        "Điều kiện thương mại"  ->  "t Đ hư iề ơ u n g k i m ện ạ i"

    Dấu hiệu ổn định là tỉ lệ token một ký tự cao bất thường — tiếng Việt viết
    bình thường hầu như không sinh ra chuỗi như vậy.
    """
    toks = cell.split()
    if len(toks) < 4:
        return False
    return sum(1 for t in toks if len(t) == 1) / len(toks) > 0.3


def _merge_header_rows(top: list[str], sub: list[str]) -> list[str]:
    """Ghép tiêu đề hai tầng, bỏ ô bị trộn và ô đánh số cột.

    Ở các cột bên trái, tầng hai thường chỉ lặp lại nhãn của tầng một; ghép
    thẳng sẽ ra "Stt Stt". Nên bỏ qua phần đã có mặt trong chuỗi đang tích luỹ.
    """
    out = []
    for i in range(max(len(top), len(sub))):
        parts: list[str] = []
        for row in (top, sub):
            c = (row[i] if i < len(row) else "").strip()
            if not c or _scrambled(c) or _COL_NUM_RE.match(c):
                continue
            if any(c in p or p in c for p in parts):
                continue
            parts.append(c)
        out.append(" ".join(parts))
    return out


def _is_numbering_row(row: list[str]) -> bool:
    """Hàng chỉ chứa số thứ tự cột — "[1] [2] [3]…" — không mang thông tin."""
    cells = [c.strip() for c in row if c.strip()]
    return len(cells) >= 3 and all(_COL_NUM_RE.match(c) for c in cells)


def _has_usable_second_tier(top: list[str], sub: list[str]) -> bool:
    """Tầng hai chỉ đáng ghép khi nó bù được nhãn mà tầng một thiếu hoặc hỏng.

    Điều kiện này giữ cho bảng một tầng bình thường không bị đụng tới: nếu tầng
    một đã đủ nhãn sạch thì hàm trả về False và luồng cũ chạy nguyên vẹn.
    """
    cells = [c.strip() for c in sub]
    if len([c for c in cells if c]) < 2 or any(_is_number_cell(c) for c in cells):
        return False
    for i, cb in enumerate(cells):
        ca = (top[i] if i < len(top) else "").strip()
        if cb and not _scrambled(cb) and not _COL_NUM_RE.match(cb) and (not ca or _scrambled(ca)):
            return True
    return False


def _resolve_header(
    grid: list[list[str]],
    prev_header: list[str] | None,
    prev_ncol: int | None,
) -> tuple[list[str] | None, list[list[str]], list[str] | None, int | None]:
    """Decide which row (if any) is this table's header.

    pdfplumber extracts one table per page, so a table spanning N pages
    arrives as N independent tables. Three cases, in order:

      * the first row repeats the previous table's header  -> normal header
      * same column count but the first row is clearly data -> continuation;
        borrow the previous header so the chunk keeps its column labels
      * the first row looks like a header                   -> new header

    Anything else yields no header at all: emitting `<th>` around a data row
    is worse than emitting none, because it tells the model that a product
    name is a column label.
    """
    if not grid:
        return None, [], prev_header, prev_ncol

    first, rest = grid[0], grid[1:]
    ncol = max(len(r) for r in grid)

    normalized = [c.strip() for c in first]
    if prev_header is not None and normalized == [c.strip() for c in prev_header]:
        return first, rest, first, ncol

    if prev_header is not None and prev_ncol == ncol and not _looks_like_header(first):
        return prev_header, grid, prev_header, prev_ncol

    if _looks_like_header(first):
        # Tiêu đề hai tầng: nhãn của các cột con nằm ở hàng thứ hai, và ở hàng
        # đầu chính những cột đó lại là chuỗi bị trộn. Ghép hai tầng mới lấy
        # lại được nhãn — với bảng công bố giá, đó là ba cột khu vực KV 1/2/3.
        if rest and _has_usable_second_tier(first, rest[0]):
            merged = _merge_header_rows(first, rest[0])
            body = [r for r in rest[1:] if not _is_numbering_row(r)]
            return merged, body, merged, ncol
        return first, rest, first, ncol

    return None, grid, prev_header, prev_ncol
