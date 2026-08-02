"""Add knowledge_bases.price_extraction — per-KB toggle for structured
price-row extraction into material_prices.

Replaces the hard-coded PRICE_EXTRACTION_KB_IDS = {KB_PRICING_ID} check in
app/api/v1/documents.py, which meant only one fixed KB could ever feed the
price database and user-created KBs never could. All 4 system KBs are
backfilled to true: "Dự toán giá nhà" and "Báo giá doanh nghiệp" are price
documents by definition, and running the extractor over the other two is
harmless — a document with no price table simply yields 0 rows (surfaced in
the UI as "0 dòng giá") while its RAG chunks are unaffected.

Revision ID: 0008_kb_price_extraction
Revises: 0007_add_vendor_standards_kb
Create Date: 2026-08-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_kb_price_extraction"
down_revision = "0007_add_vendor_standards_kb"
branch_labels = None
depends_on = None

# Must match app/core/bootstrap/constants.py
SYSTEM_KB_IDS = (
    "00000000-0000-0000-0000-000000000101",
    "00000000-0000-0000-0000-000000000102",
    "00000000-0000-0000-0000-000000000103",
    "00000000-0000-0000-0000-000000000104",
)


def upgrade() -> None:
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "price_extraction",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.get_bind().execute(
        sa.text(
            "UPDATE knowledge_bases SET price_extraction = true, updated_at = now() "
            "WHERE id = ANY(CAST(:ids AS uuid[]))"
        ),
        {"ids": list(SYSTEM_KB_IDS)},
    )


def downgrade() -> None:
    op.drop_column("knowledge_bases", "price_extraction")
