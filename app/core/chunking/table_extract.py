"""Merged-cell aware table extraction — shared by the RAG chunker and the
structured price extractor so both see the same grid.

Why this exists
---------------
`page.extract_tables()` puts the text of a vertically-merged cell only in the
row where the cell physically starts and leaves every continuation row empty.
In the Đà Nẵng electrical-materials annex the "Tiêu chuẩn kỹ thuật" cell is
merged across a whole product family, so only the *first* lamp model ends up
associated with "CE, ENEC, IEC60598-2-3, RoHS…" — a question like "tiêu chuẩn
RoHS áp dụng cho những vật liệu nào" then retrieves a chunk where 11 of 12
products look like they have no standard at all, and the model fills the gap
from its own knowledge.

The fix is geometric, not heuristic: pdfplumber's `Table.rows[r].cells[c]` is
`None` exactly when no cell *starts* at that grid position because a taller
cell from above covers it. A genuinely blank-but-ruled cell has a real bbox,
so it stays blank. That distinction is what makes forward-filling safe here.

...with one exception that has to be checked, not assumed. `cells[c] is None`
also happens when the PDF's ruling lines are simply INCOMPLETE — the grid has
a hole where a real cell was drawn without borders. pdfplumber drops any text
inside such a hole (it has no cell to attach it to), and forward-filling then
puts a value from a previous row where a real, different value belongs. In
the Đà Nẵng aggregates annex that turned "Cấp phối A Dmax25 … 298.182 đ/m3"
into "… 7 đ/m3", inheriting a stale digit from six rows above — 121 rows in
the corpus carried a fabricated price of 7 đ.

The two cases are distinguishable by looking at the page: the body of a real
merged cell is EMPTY (its text sits in the row where the cell starts), while
a grid hole still has words sitting in it. So before inheriting, check
whether the cell's own region contains text — if it does, that text belongs
to this row. See _recover_hole().

Ditto markers ("-nt-" = "như trên") are a second, textual form of the same
"same as the row above" idea and are expanded here too — but only markers
that cannot mean anything else. A bare "-" is deliberately NOT treated as a
ditto marker at this layer (it also means "not applicable"); the price
extractor resolves it only for the unit column, where "-" is not a valid
value. See resolve_unit_ditto().
"""

from __future__ import annotations

import re

# Unambiguous "same as above" markers. A bare "-" is excluded on purpose —
# see the module docstring.
_DITTO_RE = re.compile(
    r"^\s*(?:-{1,2}\s*nt\s*-{1,2}|nt\.?|-//-|\"|''|,,|như\s+trên|nhu\s+tren)\s*$",
    re.IGNORECASE,
)

# A "-" used as a unit is never a real unit of measure, so in that one column
# it can only be a ditto marker for the merged/repeated unit above.
_UNIT_DITTO_RE = re.compile(r"^\s*[-–—]+\s*$")


def is_ditto(cell: str | None) -> bool:
    return bool(cell) and bool(_DITTO_RE.match(cell))


def is_unit_ditto(cell: str | None) -> bool:
    return bool(cell) and (bool(_UNIT_DITTO_RE.match(cell)) or is_ditto(cell))


def extract_tables_resolved(page) -> list[list[list[str]]]:
    """Like `page.extract_tables()` but with vertically-merged cells filled
    down and ditto markers expanded.

    Returns plain `str` cells (never `None`) so callers don't need to guard.
    """
    return [resolved for resolved, _ in extract_tables_with_raw(page)]


def extract_tables_with_raw(page) -> list[tuple[list[list[str]], list[list[str]]]]:
    """extract_tables_resolved(), but each table is paired with its unfilled
    grid.

    Callers that classify rows by *emptiness* need the raw grid: a
    material-group heading row ("Cáp điện lực hạ thế – 0,6/1kV (1 lõi…)") is
    recognised by having almost every cell empty, and filling it from the
    merged cells above would disguise it as an ordinary data row.
    """
    tables: list[tuple[list[list[str]], list[list[str]]]] = []
    found = page.find_tables()
    # Fetched once per page, not once per table — extract_words() re-walks
    # every character on the page, and a 699-page annex has several tables
    # per page.
    words = _page_words(page) if found else []
    for table in found:
        grid = table.extract()
        if not grid:
            continue
        raw = [[(c or "").strip() for c in row] for row in grid]
        tables.append((_resolve(grid, table.rows, words), raw))
    return tables


def _page_words(page) -> list[dict]:
    """Words with coordinates, fetched once per page. Returns [] if the
    backend can't supply them, in which case hole recovery is simply skipped
    and behaviour falls back to plain forward-filling."""
    try:
        return page.extract_words()
    except Exception:
        return []


def _column_spans(rows, ncol: int) -> list[tuple[float, float] | None]:
    """Horizontal extent of each column, taken from whichever rows DO have a
    bbox at that index. A hole has no bbox of its own, so its x-range has to
    be borrowed from its column."""
    spans: list[tuple[float, float] | None] = [None] * ncol
    for row in rows:
        for col_idx, cell in enumerate(row.cells[:ncol]):
            if cell is None or spans[col_idx] is not None:
                continue
            spans[col_idx] = (cell[0], cell[2])
    return spans


def _recover_hole(words: list[dict], x_span, y_span) -> str:
    """Text sitting inside a bbox the table grid has no cell for.

    Matched by word CENTRE rather than overlap, so a word straddling a column
    boundary is claimed by exactly one column instead of both.
    """
    if not words or x_span is None or y_span is None:
        return ""
    x0, x1 = x_span
    top, bottom = y_span
    found = [
        w
        for w in words
        if x0 <= (w["x0"] + w["x1"]) / 2 <= x1 and top <= (w["top"] + w["bottom"]) / 2 <= bottom
    ]
    found.sort(key=lambda w: w["x0"])
    return " ".join(w["text"] for w in found).strip()


def _resolve(grid: list[list[str | None]], rows, words: list[dict]) -> list[list[str]]:
    ncol = max((len(r) for r in grid), default=0)
    spans = _column_spans(rows, ncol)
    last: list[str] = [""] * ncol
    resolved: list[list[str]] = []

    for row_idx, raw_row in enumerate(grid):
        row = rows[row_idx] if row_idx < len(rows) else None
        geom_cells = row.cells if row is not None else []
        y_span = (row.bbox[1], row.bbox[3]) if row is not None else None

        out_row: list[str] = []
        for col_idx in range(ncol):
            text = (raw_row[col_idx] or "").strip() if col_idx < len(raw_row) else ""
            covered_by_merge = col_idx < len(geom_cells) and geom_cells[col_idx] is None

            if covered_by_merge:
                # Look before inheriting: a real merged-cell body is empty,
                # so anything found here is this row's own value.
                own = _recover_hole(words, spans[col_idx], y_span)
                if own:
                    out_row.append(own)
                    last[col_idx] = own
                    continue

            if covered_by_merge or is_ditto(text):
                out_row.append(last[col_idx])
            else:
                out_row.append(text)
                last[col_idx] = text
        resolved.append(out_row)

    return resolved
