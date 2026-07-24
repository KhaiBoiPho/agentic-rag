"""Fixed IDs for the system-owned knowledge bases seeded at deploy time.

These UUIDs are referenced from both the Alembic migration that creates the
rows (migrations/versions/0003_seed_system_kb.py) and the app-startup
ingestion task (app/core/bootstrap/seed.py) — they must stay in sync, which
is why they live here instead of being inlined in both places.
"""

from __future__ import annotations

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"
SYSTEM_USER_EMAIL = "system@internal.agentic-rag"

KB_KNOWLEDGE_ID = "00000000-0000-0000-0000-000000000101"
KB_KNOWLEDGE_NAME = "Kiến thức xây dựng"

KB_PRICING_ID = "00000000-0000-0000-0000-000000000102"
KB_PRICING_NAME = "Dự toán giá nhà"

SEED_DATA_DIR = "seed_data"
SEED_KNOWLEDGE_DIR = f"{SEED_DATA_DIR}/knowledge"
SEED_PRICE_REGIONS = ["HN", "DN", "HCM"]  # subfolders under seed_data/prices/

SYSTEM_KB_IDS = {KB_KNOWLEDGE_ID, KB_PRICING_ID}


def is_system_kb(kb_id: str) -> bool:
    """True for the two seeded, read-only knowledge bases — callers use this
    to reject uploads/deletes against them regardless of who's asking (see
    app/api/v1/documents.py, app/api/v1/knowledge_base.py)."""
    return kb_id in SYSTEM_KB_IDS
