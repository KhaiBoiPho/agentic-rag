"""Seed system user + 2 system-owned knowledge bases (empty rows only).

Pure SQL insert, idempotent (ON CONFLICT DO NOTHING) — this is deliberately
NOT where document ingestion happens: migrations run synchronously and
shouldn't call async pipelines / OpenRouter over the network. The actual
file ingestion (chunk/embed/extract into these KBs) runs as a background
task on app startup — see app/core/bootstrap/seed.py, gated on
document_count == 0 so it only does real work once.

IDs here must match app/core/bootstrap/constants.py.

Revision ID: 0003_seed_system_kb
Revises: 0002_material_prices
Create Date: 2026-07-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_seed_system_kb"
down_revision = "0002_material_prices"
branch_labels = None
depends_on = None

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"
SYSTEM_USER_EMAIL = "system@internal.agentic-rag"
KB_KNOWLEDGE_ID = "00000000-0000-0000-0000-000000000101"
KB_KNOWLEDGE_NAME = "Kiến thức xây dựng"
KB_PRICING_ID = "00000000-0000-0000-0000-000000000102"
KB_PRICING_NAME = "Dự toán giá nhà"


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text(
            """
            INSERT INTO users (id, email, hashed_password, full_name, is_active, created_at, updated_at)
            VALUES (:id, :email, '', 'System', true, now(), now())
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"id": SYSTEM_USER_ID, "email": SYSTEM_USER_EMAIL},
    )

    for kb_id, name, description in [
        (KB_KNOWLEDGE_ID, KB_KNOWLEDGE_NAME, "Playbook đo bóc/ước lượng, QCVN 16:2023, kiến thức vật liệu xây dựng"),
        (KB_PRICING_ID, KB_PRICING_NAME, "Công văn/phụ lục công bố giá vật liệu xây dựng — Hà Nội, Đà Nẵng, TPHCM"),
    ]:
        conn.execute(
            sa.text(
                """
                INSERT INTO knowledge_bases (id, user_id, name, description, document_count, created_at, updated_at)
                VALUES (:id, :user_id, :name, :description, 0, now(), now())
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {"id": kb_id, "user_id": SYSTEM_USER_ID, "name": name, "description": description},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM knowledge_bases WHERE id IN (:k1, :k2)"),
                 {"k1": KB_KNOWLEDGE_ID, "k2": KB_PRICING_ID})
    conn.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": SYSTEM_USER_ID})
