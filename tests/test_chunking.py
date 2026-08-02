"""Unit tests for chunking logic — no external services required."""

from app.core.chunking.base import (
    MAX_EMBED_TOKENS,
    count_tokens,
    embed_token_count,
    naive_merge,
    naive_merge_with_origins,
    split_oversized_table_chunk,
)
from app.core.chunking.models import Chunk, ChunkType
from app.core.chunking.table_extract import _resolve, is_ditto, is_unit_ditto

SAMPLE_TEXT = (
    "The quick brown fox jumps over the lazy dog. "
    "She sells seashells by the seashore. "
    "How much wood would a woodchuck chuck if a woodchuck could chuck wood? "
    "Peter Piper picked a peck of pickled peppers. "
    "Red lorry yellow lorry. "
    "Unique New York unique New York you know you need unique New York. "
) * 10  # ~600 tokens when repeated 10 times


def test_count_tokens_non_empty():
    assert count_tokens("Hello world") > 0


def test_count_tokens_empty():
    assert count_tokens("") == 0


def test_naive_merge_respects_budget():
    sections = SAMPLE_TEXT.split(". ")
    chunks = naive_merge(sections, chunk_token_num=512, overlap_percent=15)
    for chunk in chunks:
        # Allow up to 1.5x budget for the last partial chunk
        assert count_tokens(chunk) <= 512 * 1.5, f"Chunk exceeds budget: {count_tokens(chunk)}"


def test_naive_merge_non_empty_output():
    sections = ["Hello world.", "This is a test."]
    chunks = naive_merge(sections, chunk_token_num=512, overlap_percent=15)
    assert len(chunks) >= 1
    assert all(c.strip() for c in chunks)


def test_naive_merge_empty_input():
    assert naive_merge([], chunk_token_num=512, overlap_percent=15) == []


def test_naive_merge_with_origins_matches_naive_merge():
    sections = SAMPLE_TEXT.split(". ")
    plain = naive_merge(sections, chunk_token_num=256)
    with_origins = naive_merge_with_origins(sections, chunk_token_num=256)
    assert [t for t, _ in with_origins] == plain


def test_naive_merge_origins_point_at_contributing_section():
    """The origin index is what carries a page number onto a merged chunk."""
    sections = SAMPLE_TEXT.split(". ")
    result = naive_merge_with_origins(sections, chunk_token_num=128)
    assert len(result) > 1, "expected the sample to split into several chunks"
    origins = [o for _, o in result]
    assert origins == sorted(origins)
    assert all(0 <= o < len(sections) for o in origins)


# ─── Merged-cell / ditto resolution ────────────────────────────────────────


class _FakeRow:
    """Stands in for pdfplumber's Row.

    `cells[i] is None` where a taller cell from an earlier row covers this
    grid position. Present cells carry a real (x0, top, x1, bottom) bbox,
    because _resolve now uses the geometry to tell a merged-cell body apart
    from a hole in the ruling lines.
    """

    COL_W = 100.0
    ROW_H = 10.0

    def __init__(self, cells, row_idx=0):
        top = row_idx * self.ROW_H
        self.bbox = (0.0, top, len(cells) * self.COL_W, top + self.ROW_H)
        self.cells = [
            None
            if c is None
            else (i * self.COL_W, top, (i + 1) * self.COL_W, top + self.ROW_H)
            for i, c in enumerate(cells)
        ]


def _rows(*layouts):
    return [_FakeRow(cells, i) for i, cells in enumerate(layouts)]


def _word(text, col, row_idx):
    """A page word centred inside (col, row_idx) of the _FakeRow grid."""
    x0 = col * _FakeRow.COL_W + 10
    top = row_idx * _FakeRow.ROW_H + 2
    return {"text": text, "x0": x0, "x1": x0 + 30, "top": top, "bottom": top + 6}


def test_is_ditto_markers():
    assert is_ditto("-nt-")
    assert is_ditto(" nt ")
    assert is_ditto("như trên")
    assert not is_ditto("-"), "a bare dash is ambiguous outside the unit column"
    assert not is_ditto("đ/bộ")


def test_is_unit_ditto_accepts_bare_dash():
    assert is_unit_ditto("-")
    assert is_unit_ditto("-nt-")
    assert not is_unit_ditto("đ/m")


def test_resolve_fills_vertically_merged_cell():
    """The real failure this fixes: a technical standard stated once for a
    whole product family left every other row looking standard-less."""
    grid = [
        ["1", "DHP-STR02A 30W", "đ/bộ", "CE, ENEC, RoHS", "4.446.000"],
        ["2", "DHP-STR02A 40W", "-", "", "5.087.250"],
        ["3", "DHP-STR02A 50W", "-", "", "5.785.500"],
    ]
    rows = _rows([1, 1, 1, 1, 1], [1, 1, 1, None, 1], [1, 1, 1, None, 1])
    out = _resolve(grid, rows, [])
    assert [r[3] for r in out] == ["CE, ENEC, RoHS"] * 3
    # A bare "-" is left alone here; only the price extractor's unit column
    # resolves it, where "-" cannot be a real value.
    assert [r[2] for r in out] == ["đ/bộ", "-", "-"]


def test_resolve_keeps_genuinely_blank_ruled_cell_blank():
    grid = [["a", "note"], ["b", ""]]
    rows = _rows([1, 1], [1, 1])  # both cells really exist
    assert _resolve(grid, rows, [])[1][1] == ""


def test_resolve_expands_ditto_marker():
    grid = [["Đèn A", "Công ty TNHH CDE VINA"], ["Đèn B", "-nt-"]]
    rows = _rows([1, 1], [1, 1])
    assert _resolve(grid, rows, [])[1][1] == "Công ty TNHH CDE VINA"


def test_resolve_recovers_text_from_a_hole_instead_of_inheriting():
    """Incomplete ruling lines look identical to a merged cell in the grid,
    but the page still has words sitting in the hole. Inheriting there
    fabricated a price: "Cấp phối A Dmax25 … 298.182" was stored as 7 đ/m3,
    a stale digit from an earlier row (121 rows in the corpus)."""
    grid = [["Đá 1x2", "436.364"], ["Cấp phối A Dmax25", ""]]
    rows = _rows([1, 1], [1, None])
    words = [_word("298.182", col=1, row_idx=1)]
    assert _resolve(grid, rows, words)[1][1] == "298.182"


def test_resolve_still_inherits_when_the_hole_is_empty():
    """The genuine merged cell: nothing is drawn in the covered region, so
    forward-filling remains the right answer."""
    grid = [["Đèn A", "CE, RoHS"], ["Đèn B", ""]]
    rows = _rows([1, 1], [1, None])
    assert _resolve(grid, rows, [])[1][1] == "CE, RoHS"


# ─── Embedding budget ──────────────────────────────────────────────────────


def _table_chunk(n_rows: int, context: str = "") -> Chunk:
    rows = ["<tr><th>Tên</th><th>Đơn vị</th><th>Giá</th></tr>"]
    rows += [
        f"<tr><td>Vật liệu số {i}</td><td>tấn</td><td>1.450.000</td></tr>" for i in range(n_rows)
    ]
    html = "<table>\n" + "\n".join(rows) + "\n</table>"
    return Chunk(
        content=html,
        chunk_type=ChunkType.TABLE,
        context_above=context,
        context_below=context,
        token_count=count_tokens(html),
    )


def test_embed_token_count_includes_context():
    """What the embeddings API sees is full_content, not content."""
    chunk = _table_chunk(5, context="ngữ cảnh " * 50)
    assert embed_token_count(chunk) > chunk.token_count


def test_split_leaves_room_for_context():
    """The real bug this guards: a chunk whose content fits the budget but
    whose content+context does not still failed the whole embedding batch."""
    context = "ngữ cảnh bao quanh bảng giá. " * 60
    chunk = _table_chunk(900, context=context)
    assert embed_token_count(chunk) > MAX_EMBED_TOKENS

    pieces = split_oversized_table_chunk(chunk)
    assert len(pieces) > 1
    for piece in pieces:
        assert embed_token_count(piece) <= MAX_EMBED_TOKENS


def test_split_keeps_header_in_every_piece():
    pieces = split_oversized_table_chunk(_table_chunk(900))
    assert len(pieces) > 1
    for piece in pieces:
        assert "<th>Tên</th>" in piece.content


# ─── OCR structured pass ───────────────────────────────────────────────────

from app.core.ingestion.ocr_fallback import (  # noqa: E402
    _normalise,
    _numbers,
    _parse_tables,
    _verify,
)
from app.core.ingestion.price_extractor import (  # noqa: E402
    _fill_table_wide_unit,
    _is_legend_row,
)

_PAGE = """Mức giá niêm yết
<table>
<tr><td>STT</td><td>Tên vật liệu</td><td>Đơn vị</td><td>Giá bán</td></tr>
<tr><td>[1]</td><td>[2]</td><td>[3]</td><td>[4]</td></tr>
<tr><td>1</td><td>XM Power Cement</td><td>Tấn</td><td>1.287.037</td></tr>
<tr><td>2</td><td>XM Hà Tiên PCB40</td><td></td><td>1.717.593</td></tr>
</table>
Ghi chú: giá chưa gồm VAT."""


def test_parse_tables_splits_html_from_prose():
    tables, prose = _parse_tables(_PAGE)
    assert len(tables) == 1
    assert tables[0][2] == ["1", "XM Power Cement", "Tấn", "1.287.037"]
    assert "Mức giá niêm yết" in prose and "<table" not in prose


def test_normalise_pads_short_rows_on_the_right():
    """Leading columns must stay aligned — the column mapping depends on them."""
    grid = _normalise([["a", "b", "c"], ["d", "e"], ["f", "g", "h"]])
    assert grid[1] == ["d", "e", ""]


def test_bracketed_index_row_is_a_legend_row():
    """ "[1] [2] [3]" was parsed as data, yielding a product named "[3]"."""
    assert _is_legend_row(["[1]", "[2]", "[3]", "[4]"])
    assert _is_legend_row(["1", "2", "3"])
    assert not _is_legend_row(["1", "XM Power Cement", "Tấn"])


def test_verify_blanks_only_uncorroborated_numbers():
    """A price the independent pass never saw becomes empty, not wrong."""
    grid = [["XM A", "1.287.037"], ["XM B", "9.999.999"]]
    out, blanked = _verify(grid, _numbers("giá 1.287.037 đồng"))
    assert blanked == 1
    assert out[0][1] == "1.287.037"
    assert out[1] == ["XM B", ""]


def test_numbers_ignores_separator_style():
    assert _numbers("1.287.037") == _numbers("1,287,037")


def test_fill_table_wide_unit_fills_only_the_unit_column():
    """A unit merged down the whole sheet is placed once by OCR; a note
    printed against one row must NOT be spread the same way."""
    rows = [
        ["1", "XM A", "", "Hàng đặt", "1.287.037"],
        ["2", "XM B", "Tấn", "", "1.717.593"],
        ["3", "XM C", "", "", "1.703.704"],
    ]
    out = _fill_table_wide_unit(rows, unit_col=2)
    assert [r[2] for r in out] == ["Tấn", "Tấn", "Tấn"]
    assert [r[3] for r in out] == ["Hàng đặt", "", ""]


def test_fill_table_wide_unit_leaves_per_row_units_alone():
    rows = [["1", "A", "Tấn", "1"], ["2", "B", "m3", "2"], ["3", "C", "", "3"]]
    assert _fill_table_wide_unit(rows, unit_col=2)[2][2] == ""
