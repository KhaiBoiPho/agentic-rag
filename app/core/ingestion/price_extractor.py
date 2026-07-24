"""Extract structured material-price rows from Vietnamese construction
price-announcement annex tables (Sở Xây dựng công văn + phụ lục) and direct
vendor/manufacturer quote PDFs.

Table layouts differ per region and even per vendor file, so this is a
heuristic column-mapper rather than a single fixed-schema parser: it looks
for header keywords to locate the name/unit/price columns, forward-fills
sparse "group header" rows (a common rendering of merged cells) into
`material_category`, and — critically — skips rows it cannot confidently
map instead of guessing, surfacing them as warnings. A wrong material/price
match here produces a wrong construction cost downstream, so silence on
uncertain rows is the safer failure mode than a best-effort guess.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO

import pdfplumber

from app.db.postgres.repositories.material_price_repo import MaterialPriceRow

# ─── Source-file classification (plan §1.3) ────────────────────────────────

_ANNEX_RE = re.compile(r"phu[_\s]?luc|^pl[_\s]?\d|^00_pl", re.IGNORECASE)
_ANNOUNCEMENT_RE = re.compile(r"^\d|^00_\d|cbgvl|tb-sxd|sxd-qlcl|sxd-ktvlxd", re.IGNORECASE)


def classify_source_file(filename: str) -> str:
    """official_announcement | official_annex | vendor_quote — used to set
    document-level metadata and to weight source priority per the source
    hierarchy in the domain guide (giá công bố Sở > giá lẻ, nhưng báo giá
    NSX/đại lý ưu tiên hơn khi vật liệu có thương hiệu cụ thể)."""
    stem = filename.rsplit("/", 1)[-1]
    if _ANNEX_RE.search(stem):
        return "official_annex"
    if _ANNOUNCEMENT_RE.search(stem) and "công ty" not in stem.lower() and "cong ty" not in stem.lower():
        return "official_announcement"
    return "vendor_quote"


# ─── Header column detection ───────────────────────────────────────────────

_NAME_KEYWORDS = [
    "tên vật liệu", "ten vat lieu", "loại vật liệu", "tên hàng", "quy cách",
    "danh mục vật liệu", "danh mục giá vật liệu", "danh mục",
]
_UNIT_KEYWORDS = ["đơn vị", "don vi", "đvt"]
_CATEGORY_KEYWORDS = ["nhóm vật liệu", "nhom vat lieu"]
_PRICE_AT_SOURCE_KEYWORDS = ["tại nơi sản xuất", "tai noi san xuat", "tại mỏ", "tai mo"]
_PRICE_AT_SITE_KEYWORDS = ["tại chân công trình", "tai chan cong trinh", "đến chân công trình"]
_PRICE_GENERIC_KEYWORDS = [
    "giá bán", "gia ban", "đơn giá", "don gia",
    "giá công bố", "gia cong bo", "công bố giá", "cong bo gia",
    # e.g. "Giá quý II/2026" — a bare quarter/period label used as the price
    # column header in some annexes instead of "giá bán"/"đơn giá".
    "giá quý", "gia quy",
]


def _norm(cell: str | None) -> str:
    return re.sub(r"\s+", " ", (cell or "").strip().lower())


def _norm_ws(text: str) -> str:
    """Collapse whitespace/newlines without lowercasing — for values stored
    and later matched with ILIKE (lookup_material_price)."""
    return re.sub(r"\s+", " ", text).strip()


_MAX_HEADER_CELL_LEN = 60


def _find_col(header_cells: list[str], keywords: list[str]) -> int | None:
    for i, cell in enumerate(header_cells):
        norm = _norm(cell)
        # Decorative title/note rows (e.g. "BẢNG CÔNG BỐ GIÁ MỘT SỐ VẬT LIỆU
        # XÂY DỰNG...") can coincidentally contain a keyword phrase — real
        # column-header labels are short, so long cells are not candidates.
        if len(norm) > _MAX_HEADER_CELL_LEN:
            continue
        if any(kw in norm for kw in keywords):
            return i
    return None


_NUMBER_RE = re.compile(r"[\d.,]+")


def _parse_price(cell: str | None) -> float | None:
    """Vietnamese number format: '.' thousands separator, ',' decimal.

    pdfplumber occasionally splits a single number with a stray space right
    after the leading digit(s) (e.g. "1 8.000" for "18.000") due to
    font-kerning artifacts in the source PDF. Only collapse that specific
    leading-digit gap, not every space, so a genuine two-number cell (e.g.
    a "min max" range separated by whitespace) isn't merged into one."""
    if not cell:
        return None
    cell = re.sub(r"^(\d{1,2})\s+(?=\d)", r"\1", cell.strip())
    match = _NUMBER_RE.search(cell)
    if not match:
        return None
    raw = match.group(0)
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        # ambiguous single separator with 3 trailing digits -> thousands sep
        raw = raw.replace(",", "") if len(raw.split(",")[-1]) == 3 else raw.replace(",", ".")
    else:
        raw = raw.replace(".", "") if len(raw.split(".")[-1]) == 3 else raw
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None


@dataclass
class TableParseResult:
    rows: list[MaterialPriceRow]
    warnings: list[str]


@dataclass
class _ColumnMapping:
    name_col: int
    unit_col: int
    category_col: int | None
    price_site_col: int | None
    price_source_col: int | None
    price_generic_col: int | None


def _is_legend_row(row: list[str | None]) -> bool:
    """A decorative '1','2','3'...  column-index row, sometimes repeated at
    the top of every page for a table that spans many pages."""
    cells = [(c or "").strip() for c in row]
    non_empty = [c for c in cells if c]
    return bool(non_empty) and all(c.isdigit() for c in non_empty)


def _detect_header(table: list[list[str | None]]) -> tuple[int, _ColumnMapping] | None:
    """Returns (header_end_row_idx, mapping) or None if no header found.

    Headers here commonly span 2+ physical rows (e.g. "GIÁ BÁN..." on one
    row, "Tại nơi sản xuất" / "Tại chân công trình" sub-labels on the next),
    so keyword hits are merged across a window instead of requiring them
    all on one row — the first row that matches nothing after the window
    has started marks the end of the header block.
    """
    header_idx = None
    name_col = unit_col = category_col = price_site_col = price_source_col = price_generic_col = None
    for i, raw_row in enumerate(table[:6]):
        cells = [c or "" for c in raw_row]
        # Decorative title/subtitle rows are typically one long cell spanning
        # the row with the rest empty (a merged cell flattened by pdfplumber)
        # and can coincidentally contain a keyword phrase (e.g. a title like
        # "BẢNG CÔNG BỐ GIÁ ..." matching "công bố giá"). A real header row
        # has multiple distinct short labels, so require >=2 non-empty cells.
        if sum(1 for c in cells if c.strip()) <= 1:
            continue
        n = _find_col(cells, _NAME_KEYWORDS)
        u = _find_col(cells, _UNIT_KEYWORDS)
        c = _find_col(cells, _CATEGORY_KEYWORDS)
        ps = _find_col(cells, _PRICE_AT_SITE_KEYWORDS)
        po = _find_col(cells, _PRICE_AT_SOURCE_KEYWORDS)
        pg = _find_col(cells, _PRICE_GENERIC_KEYWORDS) if ps is None and po is None else None
        hit = any(v is not None for v in (n, u, c, ps, po, pg))

        if not hit:
            if header_idx is not None:
                break  # header block ended at the previous row
            continue

        header_idx = i
        name_col = name_col if name_col is not None else n
        unit_col = unit_col if unit_col is not None else u
        category_col = category_col if category_col is not None else c
        price_site_col = price_site_col if price_site_col is not None else ps
        price_source_col = price_source_col if price_source_col is not None else po
        price_generic_col = price_generic_col if price_generic_col is not None else pg

    if header_idx is None or name_col is None or unit_col is None:
        return None
    if price_site_col is None and price_source_col is None and price_generic_col is None:
        return None

    # Skip a trailing decorative "column index" row (e.g. '1','2','3'...)
    # sometimes rendered right after the real header labels.
    if header_idx + 1 < len(table) and _is_legend_row(table[header_idx + 1]):
        header_idx += 1

    mapping = _ColumnMapping(name_col, unit_col, category_col, price_site_col, price_source_col, price_generic_col)
    return header_idx, mapping


def _parse_data_rows(
    data_rows: list[list[str | None]],
    mapping: _ColumnMapping,
    current_category: str,
) -> tuple[list[MaterialPriceRow], list[str], str]:
    rows: list[MaterialPriceRow] = []
    warnings: list[str] = []
    name_col, unit_col, category_col = mapping.name_col, mapping.unit_col, mapping.category_col
    price_site_col, price_source_col, price_generic_col = (
        mapping.price_site_col, mapping.price_source_col, mapping.price_generic_col,
    )

    for row in data_rows:
        cells = [c or "" for c in row]
        if len(cells) <= max(name_col, unit_col):
            continue

        name = cells[name_col].strip()
        unit = cells[unit_col].strip()

        non_empty = [c.strip() for c in cells if c and c.strip()]
        cat_cell = cells[category_col].strip() if category_col is not None and category_col < len(cells) else ""

        # Sparse "group header" row: material name column is empty but the
        # category column (or, less commonly, the name column itself) carries
        # a group label — a common flattening of merged cells for a
        # material-group heading (e.g. "I | XI MĂNG | | | ...").
        if unit == "" and len(non_empty) <= 2 and (cat_cell or name):
            current_category = cat_cell or name
            continue

        if not name or not unit:
            continue

        # Header/category cells commonly wrap across lines in the source PDF
        # (e.g. "Đá xây\ndựng") — collapse to single-space so ILIKE lookups
        # by category/name (lookup_material_price) actually match.
        name = _norm_ws(name)
        material_category = _norm_ws(cat_cell or current_category or "chưa phân loại")

        priced_any = False
        if price_source_col is not None and price_source_col < len(cells):
            price = _parse_price(cells[price_source_col])
            if price is not None:
                rows.append(
                    MaterialPriceRow(
                        region="", material_category=material_category, material_name=name,
                        unit=unit, price_ex_vat=price, price_basis="tai_mo",
                        source_type="", raw_row_text=" | ".join(non_empty),
                    )
                )
                priced_any = True
        if price_site_col is not None and price_site_col < len(cells):
            price = _parse_price(cells[price_site_col])
            if price is not None:
                rows.append(
                    MaterialPriceRow(
                        region="", material_category=material_category, material_name=name,
                        unit=unit, price_ex_vat=price, price_basis="tai_chan_cong_trinh",
                        source_type="", raw_row_text=" | ".join(non_empty),
                    )
                )
                priced_any = True
        if price_generic_col is not None and price_generic_col < len(cells):
            price = _parse_price(cells[price_generic_col])
            if price is not None:
                rows.append(
                    MaterialPriceRow(
                        region="", material_category=material_category, material_name=name,
                        unit=unit, price_ex_vat=price, price_basis="khong_ro",
                        source_type="", raw_row_text=" | ".join(non_empty),
                    )
                )
                priced_any = True

        if not priced_any and name and unit:
            warnings.append(f"Không đọc được giá cho dòng: {' | '.join(non_empty)[:120]}")

    return rows, warnings, current_category


def parse_price_table(table: list[list[str | None]]) -> TableParseResult:
    """Parse a single, self-contained table (with its own header). For
    multi-page annexes where the table continues across pages without
    repeating the header, use extract_price_rows instead."""
    if not table or len(table) < 2:
        return TableParseResult([], [])

    detected = _detect_header(table)
    if detected is None:
        return TableParseResult([], ["Không nhận diện được header bảng (thiếu cột tên vật liệu/đơn vị) — bỏ qua bảng."])

    header_end, mapping = detected
    rows, warnings, _ = _parse_data_rows(table[header_end + 1 :], mapping, "")
    return TableParseResult(rows, warnings)


def extract_price_rows(content: bytes, region: str, source_type: str) -> TableParseResult:
    """Entry point: run pdfplumber table extraction over the whole PDF.

    A price table commonly spans many pages without repeating its text
    header (only a decorative column-index row may repeat) — so the column
    mapping and the running material_category are carried forward from the
    last page that DID have a detectable header, rather than re-detecting
    per page. This is what makes continuation pages (see Đà Nẵng PhuLuc1.pdf,
    128 pages / 1 table) parse instead of being skipped.
    """
    all_rows: list[MaterialPriceRow] = []
    all_warnings: list[str] = []
    last_mapping: _ColumnMapping | None = None
    last_col_count: int | None = None
    current_category = ""

    with pdfplumber.open(BytesIO(content)) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            for table in page.extract_tables():
                if not table:
                    continue
                col_count = max((len(r) for r in table[:3]), default=0)

                detected = _detect_header(table)
                if detected is not None:
                    header_end, last_mapping = detected
                    last_col_count = col_count
                    data_rows = table[header_end + 1 :]
                elif last_mapping is not None and col_count == last_col_count:
                    # No header on this table, but same column count as the
                    # last mapped table — treat as a genuine continuation
                    # (e.g. a table split across many pages). A DIFFERENT
                    # column count means this is a different table/section
                    # entirely, so the old mapping must NOT be reused —
                    # applying it would silently misread the wrong columns.
                    data_rows = table[1:] if _is_legend_row(table[0]) else table
                else:
                    all_warnings.append(
                        f"page {page_idx + 1}: Không nhận diện được header bảng "
                        "(thiếu cột tên vật liệu/đơn vị) — bỏ qua bảng."
                    )
                    continue

                rows, warnings, current_category = _parse_data_rows(data_rows, last_mapping, current_category)
                for r in rows:
                    r.region = region
                    r.source_type = source_type
                all_rows.extend(rows)
                all_warnings.extend(f"page {page_idx + 1}: {w}" for w in warnings)

    return TableParseResult(all_rows, all_warnings)
