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
    for table in page.find_tables():
        grid = table.extract()
        if not grid:
            continue
        raw = [[(c or "").strip() for c in row] for row in grid]
        tables.append((_resolve(grid, table.rows), raw))
    return tables


def _resolve(grid: list[list[str | None]], rows) -> list[list[str]]:
    ncol = max((len(r) for r in grid), default=0)
    last: list[str] = [""] * ncol
    resolved: list[list[str]] = []

    for row_idx, raw_row in enumerate(grid):
        geom_cells = rows[row_idx].cells if row_idx < len(rows) else []
        out_row: list[str] = []
        for col_idx in range(ncol):
            text = (raw_row[col_idx] or "").strip() if col_idx < len(raw_row) else ""
            covered_by_merge = col_idx < len(geom_cells) and geom_cells[col_idx] is None

            if covered_by_merge or is_ditto(text):
                out_row.append(last[col_idx])
            else:
                out_row.append(text)
                last[col_idx] = text
        resolved.append(out_row)

    return resolved
