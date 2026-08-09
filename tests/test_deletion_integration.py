"""Deleting a document or a knowledge base must leave NO retrievable vector.

THE INCIDENT THIS PINS
----------------------
Postgres cascades stop at the store boundary. `KnowledgeBase.documents` has
`cascade="all, delete-orphan"`, so deleting a KB removed its Document rows and
its material_prices rows — and left every vector in Qdrant. One production KB
deletion left **4.060 orphaned points**.

They were not inert. Retrieval filters on `kb_id`, and the orphaned payloads
still carried it, so a knowledge base the user had deleted kept supplying
citations. A purge script cleans up existing residue
(`scripts/purge_orphaned_vectors.py`); this file exists so the leak cannot come
back.

WHY THESE ASSERT ON A QUERY, NOT ON A CALL
------------------------------------------
Asserting "delete() was called with a filter that looks right" is exactly the
reasoning that let the bug ship: every layer was correct on its own and the
chain simply ended early. So the store here is a real one (in-memory, filter-
honouring — see tests/fake_qdrant.py), points go in through the ingest path's
own `upsert_chunks`, and the assertion is that a SEARCH afterwards finds
nothing. A live-Qdrant version of the same checks runs at the bottom when a
server is reachable.
"""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

import app.db.qdrant.client as qc
from app.core.chunking.models import Chunk, ChunkType
from app.db.qdrant.client import QdrantStore
from tests.fake_qdrant import FakeQdrantClient

KB_A = str(uuid.uuid4())
KB_B = str(uuid.uuid4())
DOC_1 = str(uuid.uuid4())
DOC_2 = str(uuid.uuid4())
USER = uuid.uuid4()


def chunk(doc_id: str, kb_id: str, text: str, region: str = "HCM") -> Chunk:
    return Chunk(
        document_id=doc_id,
        kb_id=kb_id,
        filename="BangGia.pdf",
        chunk_type=ChunkType.TABLE,
        content=text,
        page_num=1,
        token_count=8,
        metadata={"region": region, "price_period": "2026-06"},
    )


@pytest.fixture
async def store():
    """A QdrantStore backed by the filter-honouring in-memory double."""
    s = QdrantStore()
    s._client = FakeQdrantClient()
    s._collection = "test_chunks"
    await s.ensure_collection()
    await s.upsert_chunks(
        [
            chunk(DOC_1, KB_A, "Xi măng PCB40 — 1.450.000 đ/tấn"),
            chunk(DOC_1, KB_A, "Thép D12 — 18.000 đ/kg"),
            chunk(DOC_2, KB_A, "Cát xây tô — 250.000 đ/m3"),
            chunk("doc-other", KB_B, "Gạch ống — 1.200 đ/viên"),
        ],
        embeddings=[[0.1] * 8, [0.2] * 8, [0.3] * 8, [0.4] * 8],
    )
    return s


async def retrievable(store: QdrantStore, kb_id: str) -> list[dict]:
    """Everything still reachable through the normal retrieval path."""
    points = await store.search(
        query_vector=[0.1] * 8, kb_id=kb_id, top_k=100, score_threshold=0.0
    )
    return [p.payload for p in points]


class TestStoreLevelDeletion:
    async def test_the_fixture_is_actually_retrievable_first(self, store):
        """Guards against a false pass: if nothing were retrievable to begin
        with, every deletion assertion below would be vacuously true."""
        assert len(await retrievable(store, KB_A)) == 3
        assert len(await retrievable(store, KB_B)) == 1

    async def test_document_deletion_leaves_no_retrievable_payload(self, store):
        await store.delete_by_document(DOC_1)
        left = await retrievable(store, KB_A)
        assert all(p["document_id"] != DOC_1 for p in left)
        assert len(left) == 1  # DOC_2 untouched

    async def test_kb_deletion_leaves_no_retrievable_payload(self, store):
        """THE regression. Before the fix this returned all three points."""
        await store.delete_by_kb(KB_A)
        assert await retrievable(store, KB_A) == []

    async def test_kb_deletion_does_not_touch_other_knowledge_bases(self, store):
        await store.delete_by_kb(KB_A)
        assert len(await retrievable(store, KB_B)) == 1

    async def test_no_orphan_survives_anywhere_in_the_collection(self, store):
        """Retrieval is kb-scoped, so a kb-scoped query cannot see an orphan
        whose kb_id was rewritten or lost. Check the raw store too."""
        await store.delete_by_kb(KB_A)
        remaining = [rec["payload"] for rec in store._client.points.values()]
        assert all(p["kb_id"] != KB_A for p in remaining)
        assert len(remaining) == 1

    async def test_deleting_an_absent_kb_is_a_no_op(self, store):
        await store.delete_by_kb(str(uuid.uuid4()))
        assert len(store._client.points) == 4


# ─── Through the HTTP endpoints ──────────────────────────────────────────────


@pytest.fixture
def api(monkeypatch):
    """The real DELETE endpoints, with Postgres repositories doubled and the
    filter-honouring Qdrant behind the real QdrantStore."""
    from app.api import deps
    from app.main import create_app

    fake = FakeQdrantClient()

    def build(*, kb_owned=True, doc_exists=True):
        store_holder: dict = {}

        def make_store():
            s = QdrantStore()
            s._client = fake
            s._collection = "test_chunks"
            store_holder["store"] = s
            return s

        monkeypatch.setattr(qc, "QdrantStore", make_store)

        deleted: dict = {"kb": False, "doc": False}

        class KBRepo:
            async def get(self, kb_id, user_id):
                return SimpleNamespace(id=kb_id) if kb_owned else None

            async def delete(self, kb_id, user_id):
                deleted["kb"] = kb_owned
                return kb_owned

        class DocRepo:
            async def get_by_id(self, doc_id, user_id):
                return SimpleNamespace(id=doc_id) if doc_exists else None

            async def delete(self, doc_id, user_id):
                deleted["doc"] = True

        # knowledge_base.py binds the repository at MODULE import, so the
        # source module is the wrong patch target — it would silently fall
        # through to real Postgres. documents.py imports its repository inside
        # the handler, so there the source module is the right one.
        monkeypatch.setattr(
            "app.api.v1.knowledge_base.KnowledgeBaseRepository", lambda: KBRepo()
        )
        monkeypatch.setattr(
            "app.db.postgres.repositories.document_repo.DocumentRepository", lambda: DocRepo()
        )

        app = create_app()
        app.dependency_overrides[deps.get_current_user] = lambda: SimpleNamespace(
            id=USER, email="t@t.vn"
        )
        return app, fake, deleted, store_holder

    return build


async def seed(fake: FakeQdrantClient):
    s = QdrantStore()
    s._client = fake
    s._collection = "test_chunks"
    await s.upsert_chunks(
        [
            chunk(DOC_1, KB_A, "Xi măng PCB40"),
            chunk(DOC_2, KB_A, "Cát xây tô"),
            chunk("doc-other", KB_B, "Gạch ống"),
        ],
        embeddings=[[0.1] * 8, [0.2] * 8, [0.3] * 8],
    )
    return s


class TestEndpointDeletion:
    async def test_delete_kb_endpoint_removes_every_vector(self, api):
        app, fake, deleted, _ = api()
        store = await seed(fake)
        assert len(await retrievable(store, KB_A)) == 2

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.delete(f"/api/v1/kb/{KB_A}")
        assert resp.status_code == 204
        assert deleted["kb"] is True
        assert await retrievable(store, KB_A) == []
        assert len(await retrievable(store, KB_B)) == 1

    async def test_delete_document_endpoint_removes_its_vectors(self, api):
        app, fake, deleted, _ = api()
        store = await seed(fake)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.delete(f"/api/v1/documents/{DOC_1}")
        assert resp.status_code == 204
        left = await retrievable(store, KB_A)
        assert all(p["document_id"] != DOC_1 for p in left)
        assert len(left) == 1

    async def test_a_kb_the_caller_does_not_own_loses_no_vectors(self, api):
        """Ownership is checked BEFORE the destructive call. Without that
        ordering, a 404-shaped request would still wipe someone else's data."""
        app, fake, deleted, _ = api(kb_owned=False)
        store = await seed(fake)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.delete(f"/api/v1/kb/{KB_A}")
        assert resp.status_code == 404
        assert deleted["kb"] is False
        assert len(await retrievable(store, KB_A)) == 2, "vectors deleted on a rejected request"

    async def test_a_system_kb_is_refused_and_keeps_its_vectors(self, api):
        from app.core.bootstrap.constants import KB_PRICING_ID

        app, fake, _, _ = api()
        store = QdrantStore()
        store._client = fake
        store._collection = "test_chunks"
        await store.upsert_chunks(
            [chunk("d", KB_PRICING_ID, "Xi măng")], embeddings=[[0.1] * 8]
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.delete(f"/api/v1/kb/{KB_PRICING_ID}")
        assert resp.status_code == 403
        assert len(await retrievable(store, KB_PRICING_ID)) == 1

    async def test_a_missing_document_deletes_nothing(self, api):
        app, fake, deleted, _ = api(doc_exists=False)
        store = await seed(fake)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.delete(f"/api/v1/documents/{DOC_1}")
        assert resp.status_code == 404
        assert len(await retrievable(store, KB_A)) == 2


# ─── Against a real Qdrant, when one is reachable ────────────────────────────

_LIVE = os.getenv("QDRANT_INTEGRATION_TEST") == "1"


@pytest.mark.skipif(not _LIVE, reason="set QDRANT_INTEGRATION_TEST=1 with a live Qdrant")
class TestAgainstLiveQdrant:
    """The same guarantee against a real server.

    Skipped by default so CI stays hermetic; run it before a release:

        QDRANT_INTEGRATION_TEST=1 pytest tests/test_deletion_integration.py -v

    It uses its own throwaway collection and deletes it afterwards, so it never
    touches the real one.
    """

    @pytest.fixture
    async def live_store(self):
        store = QdrantStore()
        store._collection = f"test_deletion_{uuid.uuid4().hex[:8]}"
        await store.ensure_collection()
        yield store
        await store._client.delete_collection(store._collection)

    async def test_kb_deletion_leaves_nothing_retrievable(self, live_store):
        import app.config as cfg

        dim = cfg.settings.embed_dim
        await live_store.upsert_chunks(
            [chunk(DOC_1, KB_A, "Xi măng PCB40"), chunk("d2", KB_B, "Gạch ống")],
            embeddings=[[0.01] * dim, [0.02] * dim],
        )
        assert len(await retrievable(live_store, KB_A)) == 1

        await live_store.delete_by_kb(KB_A)
        assert await retrievable(live_store, KB_A) == []
        assert len(await retrievable(live_store, KB_B)) == 1

    async def test_document_deletion_leaves_nothing_retrievable(self, live_store):
        import app.config as cfg

        dim = cfg.settings.embed_dim
        await live_store.upsert_chunks(
            [chunk(DOC_1, KB_A, "Xi măng PCB40"), chunk(DOC_2, KB_A, "Cát xây tô")],
            embeddings=[[0.01] * dim, [0.02] * dim],
        )
        await live_store.delete_by_document(DOC_1)
        left = await retrievable(live_store, KB_A)
        assert all(p["document_id"] != DOC_1 for p in left)
        assert len(left) == 1
