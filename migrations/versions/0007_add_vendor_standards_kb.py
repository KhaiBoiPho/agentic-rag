"""Expand system KBs from 2 to 4, and update the existing 2's name/description.

Pure SQL, idempotent (ON CONFLICT DO NOTHING for inserts). All 4 start (or
stay) empty — as of this migration there is no more automatic seeding from
seed_data/ at app startup (app/core/bootstrap/seed.py was removed); every
system KB is populated by manually uploading documents through the normal
UI upload flow, same as any user KB. See
app/core/bootstrap/constants.py for the full rationale.

IDs here must match app/core/bootstrap/constants.py.

Revision ID: 0007_add_vendor_standards_kb
Revises: 0006_messages_recent_index
Create Date: 2026-07-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_add_vendor_standards_kb"
down_revision = "0006_messages_recent_index"
branch_labels = None
depends_on = None

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"

KB_KNOWLEDGE_ID = "00000000-0000-0000-0000-000000000101"
KB_KNOWLEDGE_NAME = "Kiến thức về VLXD cho kỹ sư"
KB_KNOWLEDGE_DESC = "Playbook đo bóc/ước lượng, QCVN 16:2023, kiến thức vật liệu xây dựng cho kỹ sư"

KB_PRICING_ID = "00000000-0000-0000-0000-000000000102"
KB_PRICING_NAME = "Dự toán giá nhà"
KB_PRICING_DESC = (
    "Báo giá VLXD lấy từ Hà Nội, Đà Nẵng, TPHCM — giá chung trung bình toàn quốc, dùng để dự toán giá nhà"
)

KB_VENDOR_ID = "00000000-0000-0000-0000-000000000103"
KB_VENDOR_NAME = "Báo giá doanh nghiệp"
KB_VENDOR_DESC = "Báo giá VLXD của các doanh nghiệp trên toàn quốc"

KB_STANDARDS_ID = "00000000-0000-0000-0000-000000000104"
KB_STANDARDS_NAME = "Quy chuẩn & tiêu chuẩn xây dựng Việt Nam"
KB_STANDARDS_DESC = "Quy chuẩn Việt Nam (QCVN) và tiêu chuẩn Việt Nam (TCVN) cho xây dựng do nhà nước quy định"


def upgrade() -> None:
    conn = op.get_bind()

    # update the 2 existing KBs' name/description to the new wording
    for kb_id, name, desc in [
        (KB_KNOWLEDGE_ID, KB_KNOWLEDGE_NAME, KB_KNOWLEDGE_DESC),
        (KB_PRICING_ID, KB_PRICING_NAME, KB_PRICING_DESC),
    ]:
        conn.execute(
            sa.text(
                "UPDATE knowledge_bases SET name = :name, description = :desc, updated_at = now() "
                "WHERE id = :id"
            ),
            {"id": kb_id, "name": name, "desc": desc},
        )

    # insert the 2 new KBs
    for kb_id, name, desc in [
        (KB_VENDOR_ID, KB_VENDOR_NAME, KB_VENDOR_DESC),
        (KB_STANDARDS_ID, KB_STANDARDS_NAME, KB_STANDARDS_DESC),
    ]:
        conn.execute(
            sa.text(
                """
                INSERT INTO knowledge_bases (id, user_id, name, description, document_count, created_at, updated_at)
                VALUES (:id, :user_id, :name, :description, 0, now(), now())
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {"id": kb_id, "user_id": SYSTEM_USER_ID, "name": name, "description": desc},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM knowledge_bases WHERE id IN (:k1, :k2)"),
        {"k1": KB_VENDOR_ID, "k2": KB_STANDARDS_ID},
    )
    for kb_id, name, desc in [
        (KB_KNOWLEDGE_ID, "Kiến thức xây dựng", "Playbook đo bóc/ước lượng, QCVN 16:2023, kiến thức vật liệu xây dựng"),
        (KB_PRICING_ID, "Dự toán giá nhà", "Công văn/phụ lục công bố giá vật liệu xây dựng — Hà Nội, Đà Nẵng, TPHCM"),
    ]:
        conn.execute(
            sa.text(
                "UPDATE knowledge_bases SET name = :name, description = :desc, updated_at = now() "
                "WHERE id = :id"
            ),
            {"id": kb_id, "name": name, "desc": desc},
        )
