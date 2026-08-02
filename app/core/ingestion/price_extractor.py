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
from collections.abc import Iterable
from dataclasses import dataclass

from app.core.chunking.table_extract import is_unit_ditto
from app.core.ingestion.price_tables import iter_price_tables
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
    if (
        _ANNOUNCEMENT_RE.search(stem)
        and "công ty" not in stem.lower()
        and "cong ty" not in stem.lower()
    ):
        return "official_announcement"
    return "vendor_quote"


# ─── Header column detection ───────────────────────────────────────────────

_NAME_KEYWORDS = [
    "tên vật liệu",
    "ten vat lieu",
    "loại vật liệu",
    "tên hàng",
    "quy cách",
    "danh mục vật liệu",
    "danh mục giá vật liệu",
    "danh mục",
]
_UNIT_KEYWORDS = ["đơn vị", "don vi", "đvt"]
_CATEGORY_KEYWORDS = ["nhóm vật liệu", "nhom vat lieu"]
# "Tiêu chuẩn kỹ thuật" / "Nhà sản xuất" are usually rendered as one cell
# merged down the whole product family, so they only became readable once
# merged cells were filled (table_extract). They answer questions the price
# columns cannot ("tiêu chuẩn RoHS/IEC 62262 áp dụng cho vật liệu nào").
_SPEC_KEYWORDS = ["tiêu chuẩn kỹ thuật", "tieu chuan ky thuat", "tiêu chuẩn", "tieu chuan"]
_MANUFACTURER_KEYWORDS = [
    "nhà sản xuất",
    "nha san xuat",
    "hãng sản xuất",
    "nhà cung cấp",
    "nha cung cap",
    "đơn vị cung cấp",
]
_PRICE_AT_SOURCE_KEYWORDS = ["tại nơi sản xuất", "tai noi san xuat", "tại mỏ", "tai mo"]
_PRICE_AT_SITE_KEYWORDS = ["tại chân công trình", "tai chan cong trinh", "đến chân công trình"]
_PRICE_GENERIC_KEYWORDS = [
    "giá bán",
    "gia ban",
    "đơn giá",
    "don gia",
    "giá công bố",
    "gia cong bo",
    "công bố giá",
    "cong bo gia",
    # e.g. "Giá quý II/2026" — a bare quarter/period label used as the price
    # column header in some annexes instead of "giá bán"/"đơn giá".
    "giá quý",
    "gia quy",
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
    spec_col: int | None = None
    manufacturer_col: int | None = None


_LEGEND_CELL_RE = re.compile(r"^[\[\(]?\d{1,2}[\]\)]?$")


def _is_legend_row(row: list[str | None]) -> bool:
    """A decorative '1','2','3'... column-index row, sometimes repeated at the
    top of every page for a table that spans many pages.

    The brackets matter: the Vicem Hà Tiên price sheet prints this row as
    "[1] [2] [3] …", which the bare-digit test missed, so it was parsed as a
    data row and produced a material literally named "[3]" priced at 12."""
    cells = [(c or "").strip() for c in row]
    non_empty = [c for c in cells if c]
    return bool(non_empty) and all(_LEGEND_CELL_RE.match(c) for c in non_empty)


def _detect_header(table: list[list[str | None]]) -> tuple[int, _ColumnMapping] | None:
    """Returns (header_end_row_idx, mapping) or None if no header found.

    Headers here commonly span 2+ physical rows (e.g. "GIÁ BÁN..." on one
    row, "Tại nơi sản xuất" / "Tại chân công trình" sub-labels on the next),
    so keyword hits are merged across a window instead of requiring them
    all on one row — the first row that matches nothing after the window
    has started marks the end of the header block.
    """
    header_idx = None
    name_col = unit_col = category_col = price_site_col = price_source_col = price_generic_col = (
        None
    )
    spec_col = manufacturer_col = None
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
        sp = _find_col(cells, _SPEC_KEYWORDS)
        mf = _find_col(cells, _MANUFACTURER_KEYWORDS)
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
        spec_col = spec_col if spec_col is not None else sp
        manufacturer_col = manufacturer_col if manufacturer_col is not None else mf

    if header_idx is None or name_col is None or unit_col is None:
        return None
    if price_site_col is None and price_source_col is None and price_generic_col is None:
        return None

    # Skip the decorative "column index" row(s) (e.g. '1','2','3'... or
    # '[1]','[2]'...) that follow the real header labels. Scanning forward
    # rather than checking only the next row matters for multi-level headers:
    # in the Vicem Hà Tiên sheet the index row sits two rows below the header
    # labels, behind the sub-label row, and was being parsed as a product
    # called "[3]" priced at 12.
    while header_idx + 1 < len(table) and _is_legend_row(table[header_idx + 1]):
        header_idx += 1

    mapping = _ColumnMapping(
        name_col,
        unit_col,
        category_col,
        price_site_col,
        price_source_col,
        price_generic_col,
        spec_col,
        manufacturer_col,
    )
    return header_idx, mapping


_ORDINAL_RE = re.compile(r"^\d{1,3}$")


def _row_ordinal(cells: list[str]) -> int | None:
    """The 'STT/TT' running number, if this row starts with one.

    These annexes restart the numbering at 1 for every material group, so a
    reset is the one reliable signal that a new group began — including when
    the group has no heading row at all (vendor blocks identify themselves
    only through the manufacturer column)."""
    for cell in cells[:2]:
        text = cell.strip()
        if text:
            return int(text) if _ORDINAL_RE.match(text) else None
    return None


_ORG_RE = re.compile(
    r"c[ôo]ng\s*ty|\bcty\b|\btnhh\b|\bcp\b|\bcổ\s*phần\b|t[ậa]p\s*đo[àa]n|nh[àa]\s*m[áa]y"
    r"|doanh\s*nghi[ệe]p|c[ơo]\s*s[ởo]\s|chi\s*nh[áa]nh|h[ợo]p\s*t[áa]c\s*x[ãa]|\bdntn\b",
    re.IGNORECASE,
)


def _is_label(text: str) -> bool:
    """Textual enough to be a group heading — rules out an ordinal ("5") or a
    roman numeral left alone in the TT column."""
    stripped = text.strip()
    return len(stripped) >= 4 and not stripped.replace(".", "").isdigit()


def _looks_like_org(text: str) -> bool:
    """The "Nhà sản xuất / Ghi chú" column mixes the vendor's name with its
    address, phone number and delivery notes on the rows below it. Only the
    name identifies the manufacturer, so anything that doesn't read as an
    organisation is left for the running value to cover."""
    return bool(text) and bool(_ORG_RE.search(text))


@dataclass
class _ParseState:
    """Carried across tables/pages: a price table runs for dozens of pages and
    its group headings, units and column mapping all live on earlier pages."""

    category: str = ""
    unit: str = ""
    manufacturer: str = ""
    # True while the last heading row's category/manufacturer have not yet
    # been claimed by a group. Prevents one group's heading from labelling
    # the *next* group.
    heading_unclaimed: bool = False


def _fill_table_wide_unit(data_rows: list[list[str]], unit_col: int) -> list[list[str]]:
    """Fill the UNIT column when the whole table shares one unit.

    Only for grids with no geometry to consult (OCR). "Đơn vị: Tấn" is often a
    single cell merged down every row of the sheet; pdfplumber reports that
    merge and §2.6 fills it, but a vision transcription places the word once —
    typically near the vertical middle — leaving every row above it blank, out
    of reach of forward-filling.

    Restricted to the unit column on purpose. The same "one value, many
    blanks" shape appears in "Ghi chú" and "Điều kiện thương mại", where a
    note printed against one row applies to that row alone — filling those
    would invent data, the exact failure §2.6 avoids by using geometry. The
    unit is different: a priced row without a unit is meaningless, so a blank
    there can only be the merge. The column must still hold exactly ONE
    distinct value, so nothing can be filled with the wrong one."""
    if not data_rows or unit_col < 0:
        return data_rows
    ncol = max(len(r) for r in data_rows)
    out = [list(r) + [""] * (ncol - len(r)) for r in data_rows]
    if unit_col >= ncol:
        return out
    # Column-index rows are still in `data_rows` at this point (they are
    # skipped per-row later), and their "[4]" would count as a second distinct
    # unit, blocking the fill entirely.
    values = {r[unit_col].strip() for r in out if r[unit_col].strip() and not _is_legend_row(r)}
    if len(values) != 1:
        return out
    only = values.pop()
    for r in out:
        if not r[unit_col].strip():
            r[unit_col] = only
    return out


def _parse_data_rows(
    data_rows: list[list[str | None]],
    mapping: _ColumnMapping,
    state: _ParseState,
    raw_rows: list[list[str]] | None = None,
    assume_column_merges: bool = False,
) -> tuple[list[MaterialPriceRow], list[str]]:
    """`raw_rows`, when given, is the same block of rows *before* merged-cell
    fill — used only to recognise group-heading rows by their emptiness."""
    rows: list[MaterialPriceRow] = []
    warnings: list[str] = []
    name_col, unit_col, category_col = mapping.name_col, mapping.unit_col, mapping.category_col
    price_site_col, price_source_col, price_generic_col = (
        mapping.price_site_col,
        mapping.price_source_col,
        mapping.price_generic_col,
    )
    spec_col, manufacturer_col = mapping.spec_col, mapping.manufacturer_col

    if assume_column_merges:
        data_rows = _fill_table_wide_unit([[c or "" for c in r] for r in data_rows], unit_col)

    for row_idx, row in enumerate(data_rows):
        cells = [c or "" for c in row]
        if len(cells) <= max(name_col, unit_col):
            continue

        raw_cells = raw_rows[row_idx] if raw_rows is not None and row_idx < len(raw_rows) else cells

        # A column-index row ('1','2','3'… or '[1]','[2]'…) is never data,
        # wherever it appears — these repeat at the top of every page of a
        # multi-page annex, and behind a multi-level header they sit below the
        # sub-label row where the header-skip logic cannot reach. Left in, one
        # became a product named "[3]" priced at 12, and worse, seeded the
        # running unit with "[4]" for every row after it.
        if _is_legend_row(cells):
            continue

        name = cells[name_col].strip()
        unit = cells[unit_col].strip()

        # Vendor blocks state the unit once and write "-" (or "-nt-") on every
        # following row — a textual merged cell. "-" is never a real unit, so
        # in this one column it can only mean "same as above"; storing it
        # verbatim produced prices rendered as "4.250.000 đ/-" and made the
        # unit filter in MaterialPriceRepository.lookup() unusable.
        if (is_unit_ditto(unit) or not unit) and state.unit:
            # An empty unit cell is the same merged-cell situation as "-": the
            # value was printed once at the top of the span. pdfplumber's
            # geometry fills those (§2.6), but an OCR transcription has no
            # geometry — whether the model repeats the value is a coin flip,
            # and every unfilled row was being dropped by the `not unit`
            # guard below. `state.unit` only ever holds a real unit seen
            # earlier in the same table, so this cannot invent one.
            unit = state.unit
        elif unit and not is_unit_ditto(unit):
            state.unit = unit

        non_empty = [c.strip() for c in cells if c and c.strip()]
        cat_cell = (
            cells[category_col].strip()
            if category_col is not None and category_col < len(cells)
            else ""
        )

        # Sparse "group header" row: a material-group heading rendered as one
        # label with the rest of the row empty (e.g. "I | XI MĂNG | | | ...").
        #
        # Judged entirely on the RAW row, and the label is taken from whichever
        # column holds it — some annexes put it in the ordinal (TT) column, not
        # the name column. Both details matter: after merged-cell fill such a
        # row inherits the unit, standard and even the *material name* of the
        # family above it, so reading it as a data row would invent a priced
        # product that does not exist in the document.
        raw_non_empty = [c for c in raw_cells if c.strip()]
        raw_unit = raw_cells[unit_col].strip() if unit_col < len(raw_cells) else ""
        raw_name = raw_cells[name_col].strip() if name_col < len(raw_cells) else ""
        raw_cat = (
            raw_cells[category_col].strip()
            if category_col is not None and category_col < len(raw_cells)
            else ""
        )
        raw_priced = any(
            col is not None and col < len(raw_cells) and _parse_price(raw_cells[col]) is not None
            for col in (price_source_col, price_site_col, price_generic_col)
        )
        heading_label = raw_cat or raw_name or next((c for c in raw_non_empty if _is_label(c)), "")
        if raw_unit == "" and not raw_priced and len(raw_non_empty) <= 2 and heading_label:
            state.category = heading_label
            state.heading_unclaimed = True
            # A vendor block announces its company on this same heading row
            # ("Đèn led Thương hiệu: Philips OEM DHP | … | Công ty CP thiết bị
            # điện Đồng Hưng Phát"); the data rows below carry only "-nt-".
            if manufacturer_col is not None and manufacturer_col < len(raw_cells):
                heading_mfr = _norm_ws(raw_cells[manufacturer_col])
                if _looks_like_org(heading_mfr):
                    state.manufacturer = heading_mfr
            continue

        if not name or not unit:
            continue

        # New group starting (numbering restarted at 1) with no heading row of
        # its own: the previous group's label must not be inherited. Doing so
        # filed 47 CDE VINA lamp models under "Cáp vặn xoắn hạ thế", which made
        # lookup_material_price(material_category="đèn led") return nothing.
        if _row_ordinal(raw_cells) == 1:
            if state.heading_unclaimed:
                state.heading_unclaimed = False
            else:
                state.category = ""
                state.manufacturer = ""

        # Header/category cells commonly wrap across lines in the source PDF
        # (e.g. "Đá xây\ndựng") — collapse to single-space so ILIKE lookups
        # by category/name (lookup_material_price) actually match.
        name = _norm_ws(name)
        material_category = _norm_ws(cat_cell or state.category or "chưa phân loại")

        def _cell(col: int | None) -> str | None:
            if col is None or col >= len(cells):
                return None
            return _norm_ws(cells[col]) or None

        mfr_cell = _cell(manufacturer_col)
        if mfr_cell and _looks_like_org(mfr_cell):
            state.manufacturer = mfr_cell
        manufacturer = state.manufacturer or None

        priced_any = False
        for col, basis in (
            (price_source_col, "tai_mo"),
            (price_site_col, "tai_chan_cong_trinh"),
            (price_generic_col, "khong_ro"),
        ):
            if col is None or col >= len(cells):
                continue
            price = _parse_price(cells[col])
            if price is None:
                continue
            rows.append(
                MaterialPriceRow(
                    region="",
                    material_category=material_category,
                    material_name=name,
                    unit=unit,
                    price_ex_vat=price,
                    price_basis=basis,
                    source_type="",
                    raw_row_text=" | ".join(non_empty),
                    spec=_cell(spec_col),
                    manufacturer=manufacturer,
                )
            )
            priced_any = True

        if not priced_any and name and unit:
            warnings.append(f"Không đọc được giá cho dòng: {' | '.join(non_empty)[:120]}")

    return rows, warnings


def parse_price_table(table: list[list[str | None]]) -> TableParseResult:
    """Parse a single, self-contained table (with its own header). For
    multi-page annexes where the table continues across pages without
    repeating the header, use extract_price_rows instead."""
    if not table or len(table) < 2:
        return TableParseResult([], [])

    detected = _detect_header(table)
    if detected is None:
        return TableParseResult(
            [], ["Không nhận diện được header bảng (thiếu cột tên vật liệu/đơn vị) — bỏ qua bảng."]
        )

    header_end, mapping = detected
    rows, warnings = _parse_data_rows(table[header_end + 1 :], mapping, _ParseState())
    return TableParseResult(rows, warnings)


def extract_price_rows(
    content: bytes,
    region: str,
    source_type: str,
    filename: str = "",
    tables: Iterable[tuple[str, list[list[str]], list[list[str]]]] | None = None,
    assume_column_merges: bool = False,
) -> TableParseResult:
    """Entry point: walk every table in the document and map it to price rows.

    Source formats are handled by price_tables.iter_price_tables (PDF, DOCX,
    Markdown) so a Markdown price list feeds material_prices exactly like a
    PDF annex does. An unsupported extension yields no tables at all, which
    surfaces as 0 rows + one warning rather than an exception — a document
    that has no price table is a normal outcome, not a failed ingest.

    A price table commonly spans many pages without repeating its text
    header (only a decorative column-index row may repeat) — so the column
    mapping and the running material_category are carried forward from the
    last table that DID have a detectable header, rather than re-detecting
    per page. This is what makes continuation pages (see Đà Nẵng PhuLuc1.pdf,
    128 pages / 1 table) parse instead of being skipped.

    `filename` defaults to "" for backwards compatibility with callers that
    only passed bytes; that path is treated as PDF, which is what those
    callers meant.
    """
    all_rows: list[MaterialPriceRow] = []
    all_warnings: list[str] = []
    last_mapping: _ColumnMapping | None = None
    last_col_count: int | None = None
    state = _ParseState()

    # `tables` lets a caller supply an already-extracted grid — the OCR
    # fallback passes the tables its vision pass produced, so a scanned price
    # annex feeds material_prices too instead of only becoming searchable text.
    source_tables = (
        tables if tables is not None else iter_price_tables(content, filename or "x.pdf")
    )

    for label, table, raw_table in source_tables:
        if not table:
            continue
        col_count = max((len(r) for r in table[:3]), default=0)

        detected = _detect_header(table)
        if detected is not None:
            header_end, last_mapping = detected
            last_col_count = col_count
            data_rows = table[header_end + 1 :]
            raw_data_rows = raw_table[header_end + 1 :]
        elif last_mapping is not None and col_count == last_col_count:
            # No header on this table, but same column count as the last
            # mapped table — treat as a genuine continuation (e.g. a table
            # split across many pages). A DIFFERENT column count means this
            # is a different table/section entirely, so the old mapping must
            # NOT be reused — applying it would silently misread the wrong
            # columns.
            skip = 1 if _is_legend_row(table[0]) else 0
            data_rows = table[skip:]
            raw_data_rows = raw_table[skip:]
        else:
            all_warnings.append(
                f"{label}: Không nhận diện được header bảng "
                "(thiếu cột tên vật liệu/đơn vị) — bỏ qua bảng."
            )
            continue

        rows, warnings = _parse_data_rows(
            data_rows, last_mapping, state, raw_data_rows, assume_column_merges
        )
        for r in rows:
            r.region = region
            r.source_type = source_type
        all_rows.extend(rows)
        all_warnings.extend(f"{label}: {w}" for w in warnings)

    return TableParseResult(all_rows, all_warnings)
