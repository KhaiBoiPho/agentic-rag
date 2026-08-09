"""Hybrid retrieval query shape — what QdrantStore.search actually asks for.

These assert on the request built for Qdrant rather than on retrieval quality
(that is what `scripts/eval_final_500.py` measures, against a real corpus).
What can silently go wrong here is structural: a branch that never gets built,
a filter applied to one branch but not the other, or a threshold on the wrong
one — all of which degrade quietly to "dense-only, but slower".
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from qdrant_client.models import Fusion, FusionQuery, Modifier, SparseVector

import app.db.qdrant.client as qc
from app.core.retrieval.sparse import encode_query, term_id
from app.db.qdrant.client import DENSE_VECTOR, PREFETCH_LIMIT, SPARSE_VECTOR, QdrantStore

VEC = [0.1] * 8


class FakeClient:
    """Records every query_points call and returns canned points."""

    def __init__(self, fused=None, dense_probe=None):
        self.calls: list[dict] = []
        self._fused = fused if fused is not None else [SimpleNamespace(id="p1", score=0.9)]
        self._probe = dense_probe

    async def query_points(self, **kw):
        self.calls.append(kw)
        # The gate's probe is the one with limit=1 and with_payload=False.
        if kw.get("limit") == 1 and kw.get("with_payload") is False:
            pts = self._probe if self._probe is not None else [SimpleNamespace(id="d1")]
            return SimpleNamespace(points=pts)
        return SimpleNamespace(points=self._fused)


@pytest.fixture
def store(monkeypatch):
    def build(*, fused=None, dense_probe=None, gate=True):
        monkeypatch.setattr(qc.settings, "hybrid_require_dense_support", gate)
        s = QdrantStore()
        s._client = FakeClient(fused=fused, dense_probe=dense_probe)
        return s

    return build


def fusion_call(client: FakeClient) -> dict:
    return next(c for c in client.calls if "prefetch" in c)


class TestBothBranchesAreBuilt:
    async def test_a_query_with_text_issues_dense_and_sparse_prefetch(self, store):
        s = store()
        await s.search(VEC, kb_id="kb-1", query_text="giá xi măng PCB40")
        call = fusion_call(s._client)
        usings = [p.using for p in call["prefetch"]]
        assert usings == [DENSE_VECTOR, SPARSE_VECTOR]

    async def test_fusion_is_rrf(self, store):
        s = store()
        await s.search(VEC, kb_id="kb-1", query_text="giá xi măng PCB40")
        q = fusion_call(s._client)["query"]
        assert isinstance(q, FusionQuery) and q.fusion == Fusion.RRF

    async def test_prefetch_is_50_per_branch(self, store):
        """The benchmark's value. A chunk ranked ~30 by one branch and ~3 by
        the other must still reach the fused top-5 — that is the case BM25 was
        added to rescue."""
        s = store()
        await s.search(VEC, kb_id="kb-1", query_text="thép D12")
        assert PREFETCH_LIMIT == 50
        assert [p.limit for p in fusion_call(s._client)["prefetch"]] == [50, 50]

    async def test_the_sparse_branch_carries_the_encoded_query(self, store):
        s = store()
        await s.search(VEC, kb_id="kb-1", query_text="cáp điện CXV-150")
        sparse = fusion_call(s._client)["prefetch"][1]
        assert isinstance(sparse.query, SparseVector)
        assert term_id("cxv150") in sparse.query.indices
        assert set(sparse.query.values) == {1.0}

    async def test_top_k_governs_the_fused_output(self, store):
        s = store()
        await s.search(VEC, kb_id="kb-1", top_k=7, query_text="xi măng")
        assert fusion_call(s._client)["limit"] == 7


class TestThresholdPlacement:
    async def test_threshold_guards_the_dense_branch_only(self, store):
        """A cosine bar cannot be applied to BM25 (unbounded) or to RRF
        (reciprocal ranks). Putting it on the sparse branch would throw away
        exactly the chunks BM25 exists to surface — the ones dense scores ~0.45.
        """
        s = store()
        await s.search(VEC, kb_id="kb-1", score_threshold=0.5, query_text="xi măng PCB40")
        dense, sparse = fusion_call(s._client)["prefetch"]
        assert dense.score_threshold == 0.5
        assert sparse.score_threshold is None

    async def test_no_threshold_is_applied_to_the_fused_query(self, store):
        s = store()
        await s.search(VEC, kb_id="kb-1", score_threshold=0.5, query_text="xi măng PCB40")
        assert fusion_call(s._client).get("score_threshold") is None


class TestFiltersSurviveFusion:
    async def test_the_same_filter_goes_to_both_branches(self, store):
        """Region scoping (§10B) is applied as a Qdrant filter. If it reached
        only the dense branch, BM25 would happily return a Hà Nội chunk for a
        TP.HCM question — re-opening the P0 bug through the new branch."""
        s = store()
        await s.search(VEC, kb_id="kb-1", region="HCM", query_text="giá xi măng")
        dense, sparse = fusion_call(s._client)["prefetch"]
        assert dense.filter == sparse.filter
        assert dense.filter is not None

    async def test_region_filter_is_present_in_both(self, store):
        s = store()
        await s.search(VEC, kb_id="kb-1", region="HCM", query_text="giá xi măng")
        for branch in fusion_call(s._client)["prefetch"]:
            assert "HCM" in str(branch.filter)

    async def test_kb_scope_is_present_in_both(self, store):
        s = store()
        await s.search(VEC, kb_id=["kb-a", "kb-b"], query_text="xi măng")
        for branch in fusion_call(s._client)["prefetch"]:
            assert "kb-a" in str(branch.filter) and "kb-b" in str(branch.filter)


class TestDenseOnlyFallback:
    async def test_no_query_text_stays_dense_only(self, store):
        """Backward compatibility: a caller that never passed query_text gets
        exactly the pre-hybrid behaviour rather than a broken fusion."""
        s = store()
        await s.search(VEC, kb_id="kb-1")
        call = s._client.calls[0]
        assert "prefetch" not in call
        assert call["using"] == DENSE_VECTOR
        assert call["score_threshold"] == 0.5

    async def test_a_stopword_only_question_stays_dense_only(self, store):
        """Nothing for BM25 to match on — fusing against an empty branch would
        just halve every RRF score for no benefit."""
        s = store()
        assert encode_query("của và có cho tại") == ([], [])
        await s.search(VEC, kb_id="kb-1", query_text="của và có cho tại")
        assert all("prefetch" not in c for c in s._client.calls)


class TestOffTopicGate:
    async def test_sparse_only_hits_are_dropped_when_dense_found_nothing(self, store):
        """The hazard is concrete, not hypothetical: "Hồ Chí Minh" is both a
        person and a price region, so an off-topic question about the person is
        a strong lexical match against every TP.HCM price document. BM25 may
        reorder and extend what dense found; it may not answer alone."""
        s = store(dense_probe=[], fused=[SimpleNamespace(id="hcm-price-doc", score=0.9)])
        out = await s.search(
            VEC, kb_id="kb-1", query_text="Hồ Chí Minh sinh ngày nào?"
        )
        assert out == []

    async def test_results_pass_through_when_dense_has_support(self, store):
        s = store(dense_probe=[SimpleNamespace(id="d1")])
        out = await s.search(VEC, kb_id="kb-1", query_text="giá xi măng PCB40 ở TPHCM")
        assert [p.id for p in out] == ["p1"]

    async def test_the_probe_is_cheap(self, store):
        """limit=1, no payload — it only answers "did anything clear the bar"."""
        s = store()
        await s.search(VEC, kb_id="kb-1", query_text="giá xi măng")
        probe = next(c for c in s._client.calls if c.get("limit") == 1)
        assert probe["with_payload"] is False
        assert probe["score_threshold"] == 0.5
        assert probe["using"] == DENSE_VECTOR

    async def test_the_gate_can_be_turned_off_for_benchmark_parity(self, store):
        """With the gate off the retrieval is exactly the benchmark's: fusion,
        no extra probe, no gate."""
        s = store(gate=False, fused=[SimpleNamespace(id="p1", score=0.9)])
        out = await s.search(VEC, kb_id="kb-1", query_text="Hồ Chí Minh sinh ngày nào?")
        assert [p.id for p in out] == ["p1"]
        assert len(s._client.calls) == 1


class TestCollectionConfig:
    def test_sparse_params_enable_idf(self):
        """Without Modifier.IDF the sparse branch scores by raw term frequency,
        which ranks common words highest — the opposite of BM25."""
        assert qc._sparse_params().modifier == Modifier.IDF

    async def test_an_existing_collection_gets_the_idf_modifier_added(self):
        """Collections created before hybrid search have the sparse slot but no
        modifier. Booting must upgrade them in place."""
        updated: list[dict] = []

        class C:
            async def get_collections(self):
                return SimpleNamespace(collections=[SimpleNamespace(name="agentic_rag_chunks")])

            async def update_collection(self, **kw):
                updated.append(kw)

        s = QdrantStore()
        s._collection = "agentic_rag_chunks"
        s._client = C()
        await s.ensure_collection()
        cfg = updated[0]["sparse_vectors_config"]
        assert cfg[SPARSE_VECTOR].modifier == Modifier.IDF

    async def test_a_failed_modifier_update_does_not_block_boot(self):
        """An older server that rejects the update must not stop the app —
        dense retrieval still works."""

        class C:
            async def get_collections(self):
                return SimpleNamespace(collections=[SimpleNamespace(name="agentic_rag_chunks")])

            async def update_collection(self, **kw):
                raise RuntimeError("unsupported on this server version")

        s = QdrantStore()
        s._collection = "agentic_rag_chunks"
        s._client = C()
        await s.ensure_collection()  # must not raise


class TestScoreSemantics:
    """`score` changed meaning when retrieval became hybrid, and the UI renders
    it. An RRF score is ~0.033 at the top, so a chip that formats it as a
    percentage says "3% relevant" about the best result there is."""

    def test_hybrid_results_are_marked_rrf(self):
        from app.core.chat.sources import rag_source
        from app.core.retrieval.retriever import RetrievedChunk

        chunk = RetrievedChunk(
            chunk_id="c1",
            document_id="d",
            document_name="f.pdf",
            content="…",
            score=0.0328,
            page_num=1,
            chunk_type="table",
            score_kind="rrf",
        )
        assert rag_source(chunk).to_wire()["score_kind"] == "rrf"

    def test_tool_rows_are_marked_exact(self):
        from app.core.chat.sources import tool_source

        assert tool_source(row_id="1", region="HN").to_wire()["score_kind"] == "exact"

    def test_a_legacy_source_reads_back_as_cosine(self):
        """Conversations persisted before hybrid stored real cosine scores, so
        their percentage must keep rendering."""
        from app.core.chat.sources import AnswerSource

        legacy = {"chunk_id": "c9", "document_name": "old.pdf", "score": 0.72}
        assert AnswerSource.from_wire(legacy).score_kind == "cosine"

    def test_the_default_is_cosine_for_the_dense_only_path(self):
        from app.core.retrieval.retriever import RetrievedChunk

        c = RetrievedChunk("c", "d", "f", "x", 0.7, 1, "text")
        assert c.score_kind == "cosine"
