"""The KB toggle has to reach the ingest job — end to end through the endpoint.

Picking the right profile in isolation is worthless if the upload endpoint
drops it on the way to RabbitMQ, which is exactly what the price path used to
do with the chunk settings.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient


class FakeKB:
    def __init__(self, price_extraction=False, table_heavy_chunking=False):
        self.id = uuid.uuid4()
        self.price_extraction = price_extraction
        self.table_heavy_chunking = table_heavy_chunking


@pytest.fixture
def upload_client(monkeypatch):
    """Returns (client_builder, published) where `published` collects every job
    that would have been queued."""
    published: list[dict] = []

    async def fake_publish(*, kb_id, user_id, filename, content, config, mode="standard"):
        published.append({"kb_id": kb_id, "filename": filename, "config": config, "mode": mode})
        return "job-1"

    def build(kb: FakeKB):
        import app.api.v1.documents as docs_mod
        from app.api import deps
        from app.main import create_app

        monkeypatch.setattr(docs_mod, "publish_ingest_job", fake_publish)

        class Repo:
            async def get_by_id(self, kb_id):
                return kb

        monkeypatch.setattr(
            "app.db.postgres.repositories.kb_repo.KnowledgeBaseRepository", lambda: Repo()
        )

        app = create_app()
        app.dependency_overrides[deps.get_current_user] = lambda: SimpleNamespace(
            id=uuid.uuid4(), email="t@t.vn"
        )
        return app

    return build, published


async def post_upload(app, kb_id="kb-1", qs=""):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/api/v1/documents/upload/{kb_id}{qs}",
            files={"file": ("doc.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
    return resp


class TestFlagReachesTheJob:
    async def test_flag_off_queues_the_standard_profile(self, upload_client):
        build, published = upload_client
        resp = await post_upload(build(FakeKB()))
        assert resp.status_code == 202
        cfg = published[0]["config"]
        assert cfg["chunk_profile"] == "standard"
        assert cfg["table_cap_tokens"] == 3000
        assert cfg["table_context_size"] == 128

    async def test_flag_on_queues_the_table_heavy_profile(self, upload_client):
        build, published = upload_client
        resp = await post_upload(build(FakeKB(table_heavy_chunking=True)))
        assert resp.status_code == 202
        cfg = published[0]["config"]
        assert cfg["chunk_profile"] == "table_heavy"
        assert cfg["table_cap_tokens"] == 1500
        assert cfg["table_context_size"] == 0

    async def test_the_price_path_also_carries_the_profile(self, upload_client):
        """This is the one that was broken: `_publish_price_job` sent only
        region/price_period, so a price KB always got the defaults — the one
        corpus that most needs the table-heavy profile was the one corpus that
        could not be given it."""
        build, published = upload_client
        app = build(FakeKB(price_extraction=True, table_heavy_chunking=True))
        resp = await post_upload(app, qs="?region=HCM&price_period=2026-06")
        assert resp.status_code == 202
        job = published[0]
        assert job["mode"] == "price_extraction"
        assert job["config"]["chunk_profile"] == "table_heavy"
        assert job["config"]["table_cap_tokens"] == 1500
        # and the price metadata still travels
        assert job["config"]["region"] == "HCM"
        assert job["config"]["price_period"] == "2026-06"

    async def test_price_extraction_without_table_heavy_keeps_the_defaults(self, upload_client):
        """The two flags are independent — turning price extraction on must not
        drag the chunking profile along with it."""
        build, published = upload_client
        app = build(FakeKB(price_extraction=True))
        await post_upload(app, qs="?region=HCM")
        assert published[0]["config"]["chunk_profile"] == "standard"

    async def test_per_upload_override_beats_the_kb_profile(self, upload_client):
        build, published = upload_client
        app = build(FakeKB(table_heavy_chunking=True))
        await post_upload(app, qs="?table_cap_tokens=900")
        cfg = published[0]["config"]
        assert cfg["table_cap_tokens"] == 900
        assert cfg["chunk_profile"] == "table_heavy"  # baseline still recorded

    async def test_price_upload_still_rejects_a_missing_region(self, upload_client):
        """Regression — the region guard must survive the profile plumbing."""
        build, _ = upload_client
        resp = await post_upload(build(FakeKB(price_extraction=True)))
        assert resp.status_code == 400
