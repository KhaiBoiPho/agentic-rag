"""Add material_prices table + documents.doc_metadata JSONB column —
structured construction-material price storage for the price-lookup tool
(app/core/mcp/tools/price_lookup_tool.py), and per-document domain metadata
(region/source_type/price_period).

Revision ID: 0002_material_prices
Revises: 0001_initial_schema
Create Date: 2026-07-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_material_prices"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("doc_metadata", postgresql.JSONB(), nullable=True))

    op.create_table(
        "material_prices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("kb_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("knowledge_bases.id"), nullable=False),
        sa.Column("region", sa.String(8), nullable=False),
        sa.Column("material_category", sa.String(128), nullable=False),
        sa.Column("material_name", sa.String(512), nullable=False),
        sa.Column("spec", sa.String(512), nullable=True),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("price_ex_vat", sa.Numeric(18, 2), nullable=False),
        sa.Column("price_basis", sa.String(32), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("price_period", sa.String(16), nullable=True),
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manufacturer", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("raw_row_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_material_prices_document_id", "material_prices", ["document_id"])
    op.create_index("ix_material_prices_kb_id", "material_prices", ["kb_id"])
    op.create_index("ix_material_prices_region", "material_prices", ["region"])
    op.create_index("ix_material_prices_material_category", "material_prices", ["material_category"])
    op.create_index("ix_material_prices_material_name", "material_prices", ["material_name"])
    op.create_index(
        "ix_material_prices_lookup",
        "material_prices",
        ["region", "material_category", "price_period"],
    )


def downgrade() -> None:
    op.drop_table("material_prices")
    op.drop_column("documents", "doc_metadata")
