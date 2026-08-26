"""Regression tests for app/core/ingestion/price_extractor.py.

No test file existed for this module before — every past fix here was only
verified by hand against the real corpus (per the module's own docstrings).
These pin the shapes of bugs already found and fixed, plus the wrong-unit-
column fix from this session, so a future change can't silently reopen one.
"""

from __future__ import annotations

from app.core.ingestion.price_extractor import (
    _ColumnMapping,
    _page_num_from_label,
    _ParseState,
    _parse_data_rows,
    extract_price_rows,
    parse_price_table,
)


def _row(*cells: str) -> list[str]:
    return list(cells)


class TestUnitSelfCorrection:
    """The Nishu company-block bug: unit_col mapped to "Vận chuyển" instead
    of "Đơn vị tính" for one sub-table, turning every unit into "Bao gồm"."""

    def test_recovers_the_real_unit_from_elsewhere_in_the_row(self):
        # 12 columns, matching the real corpus shape that triggered this bug:
        # STT | Nhóm vật liệu | Tên vật liệu | Đơn vị tính | Tiêu chuẩn kỹ
        # thuật | Quy cách | Nhà sản xuất | Xuất xứ | Điều kiện thương mại |
        # Vận chuyển | Ghi chú | Công bố giá.
        data_row = _row(
            "1",
            "bột bả nội thất",
            "BT- 01",
            "kg",
            "TCCS026:",
            "40kg/bao",
            "C.ty sơn NISHU",
            "Việt Nam",
            "",
            "Bao gồm",
            "",
            "5.625",
        )
        # unit_col deliberately wrong — mapped to "Vận chuyển" (index 9)
        # instead of "Đơn vị tính" (index 3), reproducing the real
        # header-detection bug directly rather than depending on
        # _detect_header happening to reproduce it from a header row.
        mapping = _ColumnMapping(
            name_col=2, unit_col=9, category_col=1, price_site_col=None,
            price_source_col=None, price_generic_col=11,
        )
        rows, warnings = _parse_data_rows([data_row], mapping, _ParseState())
        assert rows, f"should still produce a row (warnings={warnings})"
        assert rows[0].unit == "kg", f"expected self-corrected unit 'kg', got {rows[0].unit!r}"
        assert rows[0].price_ex_vat == 5625.0

    def test_leaves_a_correctly_mapped_unit_untouched(self):
        table = [
            _row("STT", "Tên vật liệu", "Đơn vị tính", "Đơn giá"),
            _row("1", "Xi măng PCB40", "kg", "1.300"),
        ]
        result = parse_price_table(table)
        assert result.rows[0].unit == "kg"
        assert result.rows[0].price_ex_vat == 1300.0

    def test_does_not_invent_a_unit_when_none_is_present_anywhere_in_the_row(self):
        table = [
            _row("STT", "Tên vật liệu", "Đơn vị tính", "Đơn giá"),
            _row("1", "Vật tư XYZ", "Bao gồm", "10.000"),
        ]
        result = parse_price_table(table)
        # No cell anywhere in this row is a recognized unit token — the
        # (wrong) header-mapped value is kept as-is rather than guessed away.
        assert result.rows[0].unit == "Bao gồm"


class TestDittoUnitForwardFill:
    """"-" / "-nt-" on a data row means "same unit as the row above" — must
    keep working after the self-correction runs first."""

    def test_ditto_still_inherits_the_running_unit(self):
        table = [
            _row("STT", "Tên vật liệu", "Đơn vị tính", "Đơn giá"),
            _row("1", "Cát vàng", "m3", "250.000"),
            _row("2", "Cát đen", "-", "180.000"),
        ]
        result = parse_price_table(table)
        assert [r.unit for r in result.rows] == ["m3", "m3"]


class TestCategoryHeadingRow:
    """A sparse group-heading row (label only, rest blank) must still be read
    as a heading, not a priceless data row, once the unit self-correction is
    in the mix."""

    def test_heading_row_is_not_treated_as_data(self):
        table = [
            _row("STT", "Tên vật liệu", "Đơn vị tính", "Đơn giá"),
            _row("I", "XI MĂNG", "", ""),
            _row("1", "Xi măng PCB40", "kg", "1.300"),
        ]
        result = parse_price_table(table)
        assert len(result.rows) == 1
        assert result.rows[0].material_category == "XI MĂNG"


class TestPageNumTagging:
    """Every citation chip used to show a filename and nothing else — no way
    to find the row in a 100+ page phụ lục. Page numbers were available at
    parse time all along (price_tables.py's PDF adapter labels each table
    "page N"); this just carries that label through onto the row."""

    def test_page_num_from_label(self):
        assert _page_num_from_label("page 12") == 12
        # OCR path (ocr_fallback.py) appends a table index to the label.
        assert _page_num_from_label("page 12 bảng 2") == 12
        # No page concept for DOCX/Markdown sources.
        assert _page_num_from_label("table 3") is None

    def test_extract_price_rows_tags_each_row_with_its_page(self):
        table = [
            _row("STT", "Tên vật liệu", "Đơn vị tính", "Đơn giá"),
            _row("1", "Xi măng PCB40", "kg", "1.300"),
        ]
        result = extract_price_rows(
            b"",
            region="HN",
            source_type="official_annex",
            filename="x.pdf",
            tables=[("page 7", table, table)],
        )
        assert len(result.rows) == 1
        assert result.rows[0].page_num == 7

    def test_a_source_with_no_page_concept_leaves_page_num_none(self):
        table = [
            _row("STT", "Tên vật liệu", "Đơn vị tính", "Đơn giá"),
            _row("1", "Xi măng PCB40", "kg", "1.300"),
        ]
        result = extract_price_rows(
            b"",
            region="HN",
            source_type="official_annex",
            filename="x.md",
            tables=[("table 1", table, table)],
        )
        assert len(result.rows) == 1
        assert result.rows[0].page_num is None
