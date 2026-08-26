"""Add material_prices.page_num — which page of the source PDF a price row
was read from.

Every price citation chip up to now showed only the source document's
filename, never the page — a user checking a 100+ page phụ lục had no way to
jump to the right spot. The page number was always available at parse time
(price_tables.py's `_from_pdf` already walks `pdf.pages` and labels each
table "page N"), it just wasn't threaded through into the row that gets
persisted. See price_extractor.py's `extract_price_rows` for where it's now
captured, and app/core/chat/sources.py — `AnswerSource.page_num` and
`tool_source(page_num=...)` already existed (RAG chunk citations have used
them since pdf_chunker.py), this only wires material_prices rows into the
same, already-built pipe.

Nullable, no backfill: DOCX/Markdown price lists have no page concept (their
`iter_price_tables` adapters label tables "table N", not a page), and — more
importantly — a row ingested before this migration has no way to recover
which page it came from without re-parsing the original PDF bytes, which
this system does not retain after ingestion. Existing rows simply have
page_num = NULL and the chip omits the page, same as it does today; only
documents uploaded (or re-uploaded) after this change get a page number.

Revision ID: 0011_material_prices_page_num
Revises: 0010_kb_table_heavy_chunking
Create Date: 2026-08-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_material_prices_page_num"
down_revision = "0010_kb_table_heavy_chunking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "material_prices",
        sa.Column("page_num", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("material_prices", "page_num")
