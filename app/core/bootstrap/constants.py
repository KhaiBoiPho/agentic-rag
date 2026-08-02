"""Fixed IDs for the 4 system-owned knowledge bases.

These UUIDs are referenced from the Alembic migrations that create/update
the rows (migrations/versions/0003_seed_system_kb.py,
0007_add_vendor_standards_kb.py) and from the API layer's access-control
checks (is_system_kb) — they must stay in sync, which is why they live here
instead of being inlined in multiple places.

As of the 0007 migration, these 4 KBs start EMPTY and are populated by
manually uploading documents through the normal UI upload flow (same as any
user KB) — there is no more automatic seeding from seed_data/ at container
startup (see git history for the removed app/core/bootstrap/seed.py if that
behavior is ever wanted back). They stay "system" in the sense that their
identity/existence is fixed and the KB row itself can't be deleted — not in
the old stronger sense of "read-only, no uploads ever".
"""

from __future__ import annotations

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"
SYSTEM_USER_EMAIL = "system@internal.agentic-rag"

KB_KNOWLEDGE_ID = "00000000-0000-0000-0000-000000000101"
KB_KNOWLEDGE_NAME = "Kiến thức về VLXD cho kỹ sư"

KB_PRICING_ID = "00000000-0000-0000-0000-000000000102"
KB_PRICING_NAME = "Dự toán giá nhà"

KB_VENDOR_ID = "00000000-0000-0000-0000-000000000103"
KB_VENDOR_NAME = "Báo giá doanh nghiệp"

KB_STANDARDS_ID = "00000000-0000-0000-0000-000000000104"
KB_STANDARDS_NAME = "Quy chuẩn & tiêu chuẩn xây dựng Việt Nam"

SYSTEM_KB_IDS = {KB_KNOWLEDGE_ID, KB_PRICING_ID, KB_VENDOR_ID, KB_STANDARDS_ID}

# Structured price extraction is no longer a fixed list of KB ids — it is a
# per-KB setting (`knowledge_bases.price_extraction`, added in migration
# 0008) that any user can turn on for their own KB. All 4 system KBs are
# backfilled to true: a document with no readable price table simply yields
# 0 rows, which the UI shows as "0 dòng giá", and its RAG chunks are
# unaffected either way. See app/api/v1/documents.py:upload_document.


def is_system_kb(kb_id: str) -> bool:
    """True for the 4 fixed knowledge bases — callers use this to reject KB
    deletion regardless of who's asking (see app/api/v1/knowledge_base.py).
    Document upload/delete WITHIN a system KB is allowed (see
    app/api/v1/documents.py) — only the KB shell itself is protected."""
    return kb_id in SYSTEM_KB_IDS
