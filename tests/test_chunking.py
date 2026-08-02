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
    """Stands in for pdfplumber's Row: `cells[i] is None` where a taller cell
    from an earlier row covers this grid position."""

    def __init__(self, cells):
        self.cells = cells


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
    rows = [
        _FakeRow([1, 1, 1, 1, 1]),
        _FakeRow([1, 1, 1, None, 1]),
        _FakeRow([1, 1, 1, None, 1]),
    ]
    out = _resolve(grid, rows)
    assert [r[3] for r in out] == ["CE, ENEC, RoHS"] * 3
    # A bare "-" is left alone here; only the price extractor's unit column
    # resolves it, where "-" cannot be a real value.
    assert [r[2] for r in out] == ["đ/bộ", "-", "-"]


def test_resolve_keeps_genuinely_blank_ruled_cell_blank():
    grid = [["a", "note"], ["b", ""]]
    rows = [_FakeRow([1, 1]), _FakeRow([1, 1])]  # both cells really exist
    assert _resolve(grid, rows)[1][1] == ""


def test_resolve_expands_ditto_marker():
    grid = [["Đèn A", "Công ty TNHH CDE VINA"], ["Đèn B", "-nt-"]]
    rows = [_FakeRow([1, 1]), _FakeRow([1, 1])]
    assert _resolve(grid, rows)[1][1] == "Công ty TNHH CDE VINA"


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
