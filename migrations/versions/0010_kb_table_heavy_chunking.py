"""Add knowledge_bases.table_heavy_chunking — per-KB choice of ChunkProfile.

Until now one set of chunking constants served every document: text merged at
512 tokens, tables capped at 3.000, and 128 tokens of surrounding prose glued
onto every table chunk. That is the right configuration for the documents it
was measured on (scripts/eval_chunk_cap.py — prose with incidental tables),
and it stays the default.

It is the wrong configuration for a published price appendix, which is table
from page 1 to page 699. There is no surrounding prose to borrow: what sits
above a table on such a page is a page header or the tail of the previous
table, so `add_table_context` adds noise and spends token budget on it. The
500-question retrieval study (scripts/eval_final_500.py) measured that case on
its own and landed on cap 1.500 with table context off.

This column selects between the two (app/core/chunking/profiles.py). Default
false — every existing KB keeps exactly the behaviour it has today, and
already-ingested documents are untouched either way: the flag only decides how
the NEXT upload is cut.

No backfill, deliberately. Turning it on for the price KBs would silently
change how their future uploads are chunked without anyone asking for it, and
the two system price KBs already hold documents chunked the old way — mixing
profiles inside one KB is a decision for whoever owns that KB, made in the UI.

Revision ID: 0010_kb_table_heavy_chunking
Revises: 0009_price_name_matching
Create Date: 2026-08-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_kb_table_heavy_chunking"
down_revision = "0009_price_name_matching"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "table_heavy_chunking",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("knowledge_bases", "table_heavy_chunking")
