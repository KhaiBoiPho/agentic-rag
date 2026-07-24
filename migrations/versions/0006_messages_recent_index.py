"""Composite index for fast "recent N messages" history lookup.

The chat endpoint fetches the last ~10 messages of a conversation as
context on every turn: WHERE conversation_id = ? ORDER BY created_at DESC
LIMIT 10. The existing single-column ix_messages_conversation_id can't
serve the ORDER BY, so add (conversation_id, created_at) — the query then
becomes an index range scan with no sort.

Revision ID: 0006_messages_recent_index
Revises: 0005_usage_records
Create Date: 2026-07-22
"""
from __future__ import annotations

from alembic import op

revision = "0006_messages_recent_index"
down_revision = "0005_usage_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_messages_conversation_created", table_name="messages")
