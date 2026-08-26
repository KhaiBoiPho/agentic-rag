"""Add material_prices.size_spec — "Quy cách" (dimension/size), separate
from the existing `spec` column.

`spec` was originally meant to hold "Quy cách" (its old inline comment
literally said so), but price_extractor.py's column detection was later
repurposed to map it to "Tiêu chuẩn kỹ thuật" (technical standard) instead —
see _SPEC_KEYWORDS's docstring — without the comment or a dedicated column
ever being updated to match. The two are genuinely different columns in the
source tables (a row can have both "JIS, AS/NZS, ASTM" AND "≥1.00-1.40mm"),
answering different questions ("quy cách thế nào" wants the size, not the
standard) — a size question was answering "chưa có dữ liệu" because nothing
was ever asked to capture it at all.

Nullable, no backfill — same reasoning as migration 0011 (page_num): the
value has to come from re-parsing the original PDF, which this system does
not retain after ingestion. Existing rows get size_spec = NULL until their
document is re-uploaded.

Revision ID: 0012_material_prices_size_spec
Revises: 0011_material_prices_page_num
Create Date: 2026-08-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_material_prices_size_spec"
down_revision = "0011_material_prices_page_num"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "material_prices",
        sa.Column("size_spec", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("material_prices", "size_spec")
