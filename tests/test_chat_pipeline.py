"""End-to-end tests over the chat SSE endpoint — the acceptance criteria.

These drive `/api/v1/chat/stream` with the LLM, retriever and repositories
stubbed, and assert on the SSE frames the client actually receives. That is
the layer the P0 bug lived in: every component below it already had the region,
and the defect was in what the endpoint chose to serialize.

Anything touching Postgres/Qdrant/OpenRouter is patched; nothing here needs a
running service.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.retrieval.retriever import RetrievedChunk

# ─── Harness ─────────────────────────────────────────────────────────────────


class FakeLLM:
    """Records what it was asked, streams back a canned reply."""

    def __init__(self, reply: str = "Câu trả lời.", classify: str = "GENERAL_CHAT"):
        self.reply = reply
        self.classify = classify
        self.stream_calls: list[dict] = []
        self.chat_calls: list[dict] = []

    async def stream_chat(self, messages, model=None, temperature=0.7, max_tokens=2048):
        self.stream_calls.append({"messages": messages, "model": model})
        yield self.reply

    async def chat(self, messages=None, model=None, **kwargs):
        self.chat_calls.append({"messages": messages, "model": model})
        # Off-topic guard wants YES/NO; the route classifier wants a label.
        system = (messages or [{}])[0].get("content", "")
        if "YES hoặc NO" in system:
            return "YES"
        if "EXACT_STRUCTURED" in system:
            return self.classify
        return ""


class FakeRetriever:
    def __init__(self, chunks: list[RetrievedChunk]):
        self.all = chunks
        self.calls: list[dict] = []

    async def search(self, query, kb_id, top_k=5, score_threshold=0.5, region=None, **kw):
        self.calls.append({"query": query, "region": region})
        # Mirror QdrantStore.search's region filter: the asked-for region plus
        # chunks that carry no region at all.
        if region:
            return [c for c in self.all if c.region in (region, "")][:top_k]
        return self.all[:top_k]


class FakeMsgRepo:
    def __init__(self):
        self.added: list[tuple] = []

    async def ensure_conversation(self, *a, **kw):
        return None

    async def get_recent(self, *a, **kw):
        return []

    async def add(self, conv_id, role, content, sources=None):
        self.added.append((role, content, sources))


class FakePriceRepo:
    def __init__(self, rows_by_region: dict[str, list]):
        self.rows_by_region = rows_by_region
        self.calls: list[dict] = []

    async def lookup(self, *, region=None, material_name=None, **kw):
        self.calls.append({"region": region, "material_name": material_name})
        return self.rows_by_region.get(region, [])


def price_row(name, region, price, doc_id=None, page_num=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        document_id=doc_id or uuid.uuid4(),
        material_name=name,
        material_category="xi măng",
        region=region,
        price_ex_vat=price,
        unit="tấn",
        spec=None,
        manufacturer="Vicem",
        price_basis="tai_chan_cong_trinh",
        source_type="official_annex",
        price_period="2026-06",
        notes=None,
        raw_row_text=f"{name} {region} {price}",
        page_num=page_num,
    )


def chunk(cid, filename, region, content="Bảng giá vật liệu", score=0.7):
    return RetrievedChunk(
        chunk_id=cid,
        document_id=f"doc-{cid}",
        document_name=filename,
        content=content,
        score=score,
        page_num=1,
        chunk_type="table",
        region=region,
        price_period="2026-06",
    )


@pytest.fixture
def client_factory(monkeypatch):
    """Builds a test client with the whole external world stubbed."""
    from app.api import deps
    from app.main import create_app

    def build(*, llm=None, retriever=None, price_rows=None, msg_repo=None):
        llm = llm or FakeLLM()
        retriever = retriever or FakeRetriever([])
        msg_repo = msg_repo or FakeMsgRepo()
        price_repo = FakePriceRepo(price_rows or {})

        import app.api.v1.chat as chat_mod
        import app.core.chat.price_answer as pa_mod
        import app.core.pricing.service as svc_mod

        monkeypatch.setattr(chat_mod, "OpenRouterClient", lambda: llm)
        monkeypatch.setattr(chat_mod, "Retriever", lambda: retriever)
        monkeypatch.setattr(chat_mod, "MessageRepository", lambda: msg_repo)

        async def fake_lookup(**kwargs):
            kwargs.setdefault("repo", price_repo)
            if kwargs.get("repo") is None:
                kwargs["repo"] = price_repo
            return await _real_lookup(**kwargs)

        _real_lookup = svc_mod.lookup_material_record
        monkeypatch.setattr(chat_mod, "lookup_material_record", fake_lookup)

        async def fake_filenames(ids):
            return {i: "BangGia-VLXD.pdf" for i in ids}

        monkeypatch.setattr(pa_mod, "_document_filenames", fake_filenames)

        async def fake_scope(body, user_id):
            return (body.kb_id or "kb-1"), "Dự toán giá nhà"

        monkeypatch.setattr(chat_mod, "_resolve_rag_scope", fake_scope)

        async def fake_record(*a, **kw):
            return None

        monkeypatch.setattr(chat_mod, "_record_usage", fake_record)

        app = create_app()
        app.dependency_overrides[deps.get_current_user] = lambda: SimpleNamespace(
            id=uuid.uuid4(), email="t@t.vn"
        )
        return app, llm, retriever, msg_repo, price_repo

    return build


async def run_stream(app, body: dict) -> list[dict]:
    """POST the chat stream and return the parsed SSE events."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/chat/stream", json=body)
        assert resp.status_code == 200, resp.text
        text = resp.text
    return [
        json.loads(line[len("data: ") :])
        for line in text.splitlines()
        if line.startswith("data: ")
    ]


def done_event(events: list[dict]) -> dict:
    return next(e for e in events if e.get("done"))


BASE = {
    "message": "",
    "kb_id": "kb-1",
    "conversation_id": None,
    "use_rag": True,
    "top_k": 5,
    "score_threshold": 0.5,
}


# ─── The P0 bug, end to end ──────────────────────────────────────────────────


class TestWrongRegionSourceChips:
    async def test_12_12_hcm_question_never_ships_hanoi_or_danang_chips(self, client_factory):
        """ACCEPTANCE: "Hỏi giá TP.HCM không bao giờ hiện source chip Hà Nội/Đà Nẵng."

        The retriever is deliberately given all three regions' chunks — the old
        endpoint passed them straight through, and the chip rendered the
        filename, so the user saw "…DaNang…pdf" under a TP.HCM answer.
        """
        retriever = FakeRetriever(
            [
                chunk("c1", "BangGia-VLXD-HCM.pdf", "HCM"),
                chunk("c2", "BangGia-VLXD-HaNoi.pdf", "HN"),
                chunk("c3", "BangGia-VLXD-DaNang.pdf", "DN"),
            ]
        )
        app, _, retr, _, _ = client_factory(retriever=retriever)
        events = await run_stream(
            app, {**BASE, "message": "Xi măng PCB40 ở TPHCM khác PCB30 thế nào?"}
        )
        sources = done_event(events)["sources"]

        assert sources, "the answer should still be cited"
        assert {s["region"] for s in sources} == {"HCM"}
        assert not any("HaNoi" in s["document_name"] for s in sources)
        assert not any("DaNang" in s["document_name"] for s in sources)
        # Retrieval itself must be region-scoped. The old code only did this on
        # the pricing KB (`body.kb_id == KB_PRICING_ID`), so Agentic/Project
        # turns searched every region and had no filter to fall back on.
        assert retr.calls[0]["region"] == "HCM"

    async def test_wrong_region_chunks_are_dropped_even_if_retrieval_returns_them(
        self, client_factory
    ):
        """The second line of defence, tested on its own.

        The vector-store filter is not the whole fix: it keeps chunks with no
        region tag, and a legacy corpus has plenty of those. This retriever
        ignores the `region` argument entirely — exactly the pre-fix call — so
        what survives to the client is down to the source-level filter.
        """

        class IgnoresRegion(FakeRetriever):
            async def search(self, query, kb_id, top_k=5, score_threshold=0.5, region=None, **kw):
                self.calls.append({"query": query, "region": region})
                return self.all[:top_k]

        retriever = IgnoresRegion(
            [
                chunk("c1", "BangGia-VLXD-HCM.pdf", "HCM"),
                chunk("c2", "BangGia-VLXD-HaNoi.pdf", "HN"),
                chunk("c3", "BangGia-VLXD-DaNang.pdf", "DN"),
            ]
        )
        app, *_ = client_factory(retriever=retriever)
        events = await run_stream(
            app, {**BASE, "message": "Xi măng PCB40 ở TPHCM khác PCB30 thế nào?"}
        )
        assert {s["region"] for s in done_event(events)["sources"]} == {"HCM"}

    async def test_every_source_carries_its_own_region(self, client_factory):
        retriever = FakeRetriever([chunk("c1", "BangGia-VLXD-HCM.pdf", "HCM")])
        app, *_ = client_factory(retriever=retriever)
        events = await run_stream(app, {**BASE, "message": "Xi măng PCB40 là gì?"})
        for s in done_event(events)["sources"]:
            assert "region" in s and "region_label" in s
            assert "source_kind" in s

    async def test_12_16_legacy_untagged_chunk_shows_no_region_not_the_requested_one(
        self, client_factory
    ):
        retriever = FakeRetriever(
            [chunk("c1", "KienThucNen.docx", "", content="Xi măng PCB40 là xi măng hỗn hợp.")]
        )
        app, *_ = client_factory(retriever=retriever)
        events = await run_stream(
            app, {**BASE, "message": "Xi măng PCB40 ở TPHCM là gì và khác PCB30 thế nào?"}
        )
        src = done_event(events)["sources"][0]
        assert src["region"] is None
        assert src["region_label"] == "Không gắn vùng"

    async def test_12_13_multi_region_comparison_keeps_both_regions(self, client_factory):
        retriever = FakeRetriever(
            [
                chunk("c1", "hcm.pdf", "HCM"),
                chunk("c2", "hn.pdf", "HN"),
                chunk("c3", "dn.pdf", "DN"),
            ]
        )
        app, *_ = client_factory(retriever=retriever)
        events = await run_stream(
            app,
            {
                **BASE,
                "message": "Xi măng PCB40 ở Hà Nội và TPHCM khác nhau thế nào về tiêu chuẩn?",
            },
        )
        regions = {s["region"] for s in done_event(events)["sources"]}
        assert regions == {"HN", "HCM"}

    async def test_wrong_region_chunks_never_reach_the_model_either(self, client_factory):
        """Filtering only the CHIPS would leave the answer text wrong. The
        context handed to the model is built from the same filtered set."""
        retriever = FakeRetriever(
            [
                chunk("c1", "hcm.pdf", "HCM", content="HCM: 1.450.000 đ/tấn"),
                chunk("c2", "hn.pdf", "HN", content="HN: 1.380.000 đ/tấn"),
            ]
        )
        app, llm, *_ = client_factory(retriever=retriever)
        await run_stream(app, {**BASE, "message": "Xi măng PCB40 ở TPHCM là gì?"})
        prompt = json.dumps(llm.stream_calls[-1]["messages"], ensure_ascii=False)
        assert "1.450.000" in prompt
        assert "1.380.000" not in prompt

    async def test_15_persisted_sources_keep_their_region(self, client_factory):
        retriever = FakeRetriever([chunk("c1", "hcm.pdf", "HCM")])
        app, _, _, msg_repo, _ = client_factory(retriever=retriever)
        await run_stream(
            app, {**BASE, "message": "Xi măng PCB40 ở TPHCM là gì?", "conversation_id": "conv-1"}
        )
        _, _, stored = msg_repo.added[-1]
        assert stored[0]["region"] == "HCM"


# ─── Forced tool path ────────────────────────────────────────────────────────


class TestExactPriceGoesToTheToolFirst:
    async def test_price_question_calls_the_price_tool_not_retrieval(self, client_factory):
        """ACCEPTANCE: "Exact price request đi tool trước, không RAG trước."""
        retriever = FakeRetriever([chunk("c1", "hn.pdf", "HN")])
        app, _, retr, _, price_repo = client_factory(
            retriever=retriever,
            price_rows={"HCM": [price_row("Xi măng PCB40 Hà Tiên", "HCM", 1_450_000)]},
        )
        events = await run_stream(app, {**BASE, "message": "Giá xi măng PCB40 ở TPHCM?"})

        assert price_repo.calls, "the price tool must run"
        assert price_repo.calls[0]["region"] == "HCM"
        assert retr.calls == [], "no retrieval before/instead of the tool on an exact price"
        done = done_event(events)
        assert done["route"] == "exact_structured"
        assert done["source_kinds"] == ["tool"]

    async def test_tool_source_carries_the_rows_region(self, client_factory):
        app, *_ = client_factory(
            price_rows={"HCM": [price_row("Xi măng PCB40 Hà Tiên", "HCM", 1_450_000)]}
        )
        events = await run_stream(app, {**BASE, "message": "Giá xi măng PCB40 ở TPHCM?"})
        src = done_event(events)["sources"][0]
        assert src["source_kind"] == "tool"
        assert src["authority"] == "authoritative"
        assert src["region"] == "HCM"

    async def test_tool_source_carries_the_rows_page_num(self, client_factory):
        """The citation chip used to show only a filename — no way to find
        the row in a long phụ lục. page_num must flow from the DB row all
        the way to the SSE payload, same path as filename/region."""
        app, *_ = client_factory(
            price_rows={
                "HCM": [price_row("Xi măng PCB40 Hà Tiên", "HCM", 1_450_000, page_num=17)]
            }
        )
        events = await run_stream(app, {**BASE, "message": "Giá xi măng PCB40 ở TPHCM?"})
        src = done_event(events)["sources"][0]
        assert src["page_num"] == 17

    async def test_the_presenter_is_given_the_exact_number(self, client_factory):
        app, llm, *_ = client_factory(
            price_rows={"HCM": [price_row("Xi măng PCB40 Hà Tiên", "HCM", 1_450_000)]}
        )
        await run_stream(app, {**BASE, "message": "Giá xi măng PCB40 ở TPHCM?"})
        prompt = llm.stream_calls[-1]["messages"][0]["content"]
        assert "1,450,000" in prompt.replace(".", ",")
        assert "GIỮ NGUYÊN 100%" in prompt


class TestNotFoundIsTerminal:
    async def test_12_7_no_hcm_price_never_borrows_hanoi(self, client_factory):
        """ACCEPTANCE: "Tool không có giá HCM không được lấy giá HN/DN hoặc giá
        từ RAG." The retriever is loaded with a Hà Nội price chunk precisely so
        the old fall-through would have had something to grab."""
        retriever = FakeRetriever(
            [chunk("c2", "hn.pdf", "HN", content="Xi măng PCB40: 1.380.000 đ/tấn")]
        )
        app, llm, retr, _, _ = client_factory(
            retriever=retriever, price_rows={"HN": [price_row("Xi măng PCB40", "HN", 1_380_000)]}
        )
        events = await run_stream(app, {**BASE, "message": "Giá xi măng PCB40 ở TPHCM?"})

        text = "".join(e.get("delta", "") for e in events)
        assert "Không tìm thấy dữ liệu giá đã xác minh" in text
        assert "1.380.000" not in text
        assert llm.stream_calls == [], "no model call — nothing to present"
        assert done_event(events)["sources"] == [], "a blocked answer cites nothing"

    async def test_12_5_missing_region_asks_instead_of_guessing(self, client_factory):
        app, _, _, _, price_repo = client_factory(
            price_rows={"HCM": [price_row("Xi măng PCB40", "HCM", 1_450_000)]}
        )
        events = await run_stream(app, {**BASE, "message": "Giá xi măng PCB40?"})
        text = "".join(e.get("delta", "") for e in events)
        assert "khu vực nào" in text
        assert price_repo.calls == [], "never query on a guessed region"

    async def test_12_8_ambiguous_asks_which_product(self, client_factory):
        app, *_ = client_factory(
            price_rows={
                "HCM": [
                    price_row("Xi măng PCB40 Hà Tiên", "HCM", 1_450_000),
                    price_row("Xi măng trắng PCW40", "HCM", 3_900_000),
                ]
            }
        )
        events = await run_stream(app, {**BASE, "message": "Giá xi măng ở TPHCM?"})
        text = "".join(e.get("delta", "") for e in events)
        assert "Bạn muốn xem loại nào" in text
        # AMBIGUOUS is not "no data" — real, sourced rows WERE found (they're
        # listed by name/price in the reply above); only picking ONE is
        # refused. The candidates must still cite their source document,
        # same as any FOUND answer — see chat.py's AMBIGUOUS branch.
        done = next(e for e in events if e.get("done"))
        assert done["sources"], "an ambiguous answer must still cite the candidates it named"

    async def test_ambiguous_candidates_are_document_sourced_not_bare_names(self, client_factory):
        """The listed candidates come from real material_prices rows, not
        thin air — each one must carry provenance a user can check."""
        app, *_ = client_factory(
            price_rows={
                "HCM": [
                    price_row("Xi măng PCB40 Hà Tiên", "HCM", 1_450_000),
                    price_row("Xi măng trắng PCW40", "HCM", 3_900_000),
                ]
            }
        )
        events = await run_stream(app, {**BASE, "message": "Giá xi măng ở TPHCM?"})
        done = next(e for e in events if e.get("done"))
        assert len(done["sources"]) == 2
        assert all(s.get("filename") == "BangGia-VLXD.pdf" for s in done["sources"])


class TestMixedRequests:
    async def test_mixed_uses_tool_for_numbers_and_rag_for_prose(self, client_factory):
        """ACCEPTANCE: "Mixed request dùng tool cho số và RAG cho chữ."""
        retriever = FakeRetriever(
            [chunk("c1", "hcm.pdf", "HCM", content="Giá công bố chưa bao gồm thuế VAT.")]
        )
        app, llm, retr, _, price_repo = client_factory(
            retriever=retriever,
            price_rows={"HCM": [price_row("Xi măng PCB40 Hà Tiên", "HCM", 1_450_000)]},
        )
        events = await run_stream(
            app, {**BASE, "message": "Giá xi măng PCB40 ở TPHCM đã gồm VAT chưa?"}
        )
        done = done_event(events)
        assert done["route"] == "mixed"
        assert price_repo.calls and retr.calls, "both lanes run"
        assert set(done["source_kinds"]) == {"tool", "rag"}
        prompt = llm.stream_calls[-1]["messages"][0]["content"]
        assert "TƯ LIỆU THAM KHẢO" in prompt
        assert "KHÔNG lấy số từ đây" in prompt

    async def test_a_partially_found_comparison_names_the_missing_region(
        self, client_factory
    ):
        """Hà Nội has a row, TP.HCM does not. Presenting only Hà Nội would read
        as a complete answer — the missing region has to be stated."""
        app, llm, _, _, price_repo = client_factory(
            price_rows={"HN": [price_row("Xi măng PCB40", "HN", 1_380_000)], "HCM": []}
        )
        await run_stream(
            app, {**BASE, "message": "Giá xi măng PCB40 ở Hà Nội và TPHCM là bao nhiêu?"}
        )
        prompt = llm.stream_calls[-1]["messages"][0]["content"]
        assert "KHÔNG có dữ liệu giá đã xác minh cho: TP. Hồ Chí Minh" in prompt
        assert {c["region"] for c in price_repo.calls} == {"HN", "HCM"}

    async def test_mixed_supporting_sources_are_region_scoped(self, client_factory):
        retriever = FakeRetriever(
            [chunk("c1", "hcm.pdf", "HCM"), chunk("c2", "hn.pdf", "HN")]
        )
        app, *_ = client_factory(
            retriever=retriever,
            price_rows={"HCM": [price_row("Xi măng PCB40", "HCM", 1_450_000)]},
        )
        events = await run_stream(
            app, {**BASE, "message": "Giá xi măng PCB40 ở TPHCM đã gồm VAT chưa?"}
        )
        assert {s["region"] for s in done_event(events)["sources"]} == {"HCM"}


# ─── Regressions the fix must not cause ──────────────────────────────────────


class TestRegressions:
    async def test_17_small_talk_still_calls_no_model(self, client_factory):
        app, llm, retr, _, price_repo = client_factory()
        events = await run_stream(app, {**BASE, "message": "xin chào"})
        assert llm.stream_calls == [] and llm.chat_calls == []
        assert retr.calls == [] and price_repo.calls == []
        assert "".join(e.get("delta", "") for e in events)

    async def test_18_fixed_intent_still_returns_a_form(self, client_factory):
        app, *_ = client_factory()
        events = await run_stream(
            app, {**BASE, "message": "dự toán chi phí xây nhà 100m2 ở Hà Nội hết bao nhiêu?"}
        )
        assert events[0]["type"] == "form_request"
        assert events[0]["form_id"] == "construction_cost"
        assert events[0]["prefill"]["region"] == "HN"

    async def test_19_topic_guard_still_runs_without_a_kb(self, client_factory):
        class Refusing(FakeLLM):
            async def chat(self, messages=None, model=None, **kwargs):
                self.chat_calls.append({"messages": messages})
                return "NO"

        app, llm, *_ = client_factory(llm=Refusing())
        events = await run_stream(
            app, {**BASE, "kb_id": None, "use_rag": False, "message": "Ai là vua Quang Trung?"}
        )
        text = "".join(e.get("delta", "") for e in events)
        assert "ngoài phạm vi" in text or "ngoài chuyên môn" in text

    async def test_21_sse_payload_stays_backward_compatible(self, client_factory):
        """An old client reads document_name/score/chunk_id off each source and
        `sources` off the done event. All of that must still be there."""
        retriever = FakeRetriever([chunk("c1", "hcm.pdf", "HCM")])
        app, *_ = client_factory(retriever=retriever)
        events = await run_stream(app, {**BASE, "message": "Xi măng PCB40 là gì?"})
        done = done_event(events)
        assert done["type"] == "text" and done["done"] is True
        assert isinstance(done["sources"], list)
        src = done["sources"][0]
        for legacy_key in ("chunk_id", "document_name", "content", "score"):
            assert legacy_key in src

    async def test_explicit_rag_mode_still_forces_rag_only(self, client_factory):
        """mode="rag" is the user overriding the router. It must not be
        hijacked by the forced-tool path."""
        retriever = FakeRetriever([chunk("c1", "hcm.pdf", "HCM")])
        app, llm, retr, _, price_repo = client_factory(
            retriever=retriever,
            price_rows={"HCM": [price_row("Xi măng PCB40", "HCM", 1_450_000)]},
        )
        await run_stream(app, {**BASE, "mode": "rag", "message": "Giá xi măng PCB40 ở TPHCM?"})
        assert price_repo.calls == []
        assert retr.calls, "RAG-only means retrieval runs"

    async def test_a_general_question_is_unaffected(self, client_factory):
        retriever = FakeRetriever([chunk("c1", "kb.docx", "")])
        app, llm, retr, _, price_repo = client_factory(retriever=retriever)
        events = await run_stream(app, {**BASE, "message": "Xi măng PCB40 là gì?"})
        assert price_repo.calls == []
        assert retr.calls
        assert done_event(events)["route"] == "document_rag"


# ─── Production model ────────────────────────────────────────────────────────


class TestProductionModel:
    async def test_24_no_model_in_the_request_uses_gemini_flash(self, client_factory):
        """ACCEPTANCE: "Production default là google/gemini-2.5-flash."

        Asserts the SHIPPED default, not the value the local `.env` resolves
        to — otherwise the test only checks whoever ran it has the right file.
        """
        from app.config import Settings

        assert (
            Settings.model_fields["openrouter_chat_model"].default == "google/gemini-2.5-flash"
        )

        retriever = FakeRetriever([chunk("c1", "hcm.pdf", "HCM")])
        app, llm, *_ = client_factory(retriever=retriever)
        await run_stream(app, {**BASE, "message": "Xi măng PCB40 là gì?"})
        # The endpoint forwards `model=None`; OpenRouterClient resolves it.
        assert llm.stream_calls[-1]["model"] is None

    def test_the_openrouter_client_resolves_none_to_the_production_model(self):
        import inspect

        from app.core.llm.openrouter import OpenRouterClient

        src = inspect.getsource(OpenRouterClient.chat)
        assert "settings.openrouter_chat_model" in src
        src = inspect.getsource(OpenRouterClient.chat_with_tools)
        assert "settings.openrouter_chat_model" in src

    async def test_26_an_explicit_model_override_still_wins(self, client_factory):
        retriever = FakeRetriever([chunk("c1", "hcm.pdf", "HCM")])
        app, llm, *_ = client_factory(retriever=retriever)
        await run_stream(
            app, {**BASE, "message": "Xi măng PCB40 là gì?", "model": "openai/gpt-4o"}
        )
        assert llm.stream_calls[-1]["model"] == "openai/gpt-4o"

    def test_27_no_nvidia_nim_endpoint_in_the_runtime(self):
        """ACCEPTANCE: "Không còn NIM trong runtime production."""
        import pathlib

        hits = []
        for path in pathlib.Path("app").rglob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            if "integrate.api.nvidia.com" in text or "nvidia/" in text:
                hits.append(str(path))
        assert hits == []
