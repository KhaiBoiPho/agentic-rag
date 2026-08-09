"""Qdrant vector store — upsert chunks + hybrid search (dense + BM25 sparse).

Hybrid, for real. Until recently this docstring claimed hybrid search while
`upsert_chunks` wrote only a dense vector and `search` queried only the dense
index; the sparse slot was declared in the collection and never filled. See
app/core/retrieval/sparse.py for what BM25 buys on this corpus (+67 of 500
questions at Recall@5) and how Okapi is split between index time and Qdrant's
IDF modifier.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    IsEmptyCondition,
    MatchAny,
    MatchValue,
    Modifier,
    PayloadField,
    PointStruct,
    Prefetch,
    ScoredPoint,
    SparseIndexParams,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from app.config import settings
from app.core.chunking.models import Chunk
from app.core.retrieval.sparse import encode_document, encode_query

DENSE_VECTOR = "dense"
SPARSE_VECTOR = "sparse"

# Candidates pulled from EACH branch before fusion. 50 is the benchmark's
# value; the point of a wide prefetch is that a chunk ranked ~30 by one branch
# and ~3 by the other still reaches the fused top-5, which is precisely the
# case BM25 was added to rescue.
PREFETCH_LIMIT = 50


def _sparse_params() -> SparseVectorParams:
    """Modifier.IDF is what makes the stored weights BM25 rather than raw term
    frequency — Qdrant multiplies each term by its collection-wide IDF at query
    time. Without it the sparse branch silently degrades to a TF dot product,
    which ranks common words highest: the exact opposite of what BM25 is for."""
    return SparseVectorParams(index=SparseIndexParams(on_disk=False), modifier=Modifier.IDF)


class QdrantStore:
    def __init__(self) -> None:
        self._client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            https=settings.qdrant_https,
            api_key=settings.qdrant_api_key or None,
            check_compatibility=False,
        )
        self._collection = settings.qdrant_collection_name
        # See `search`. Off reproduces the benchmark's retrieval exactly
        # (fusion with no gate); on adds the off-topic guard that the dense
        # threshold used to provide on its own.
        self._require_dense_support = settings.hybrid_require_dense_support

    async def _ensure_connected(self) -> None:
        """Re-create client if needed (called before every operation)."""
        try:
            await self._client.get_collections()
        except Exception:
            self._client = AsyncQdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
                https=settings.qdrant_https,
                api_key=settings.qdrant_api_key or None,
                check_compatibility=False,
            )

    async def ensure_collection(self) -> None:
        existing = [c.name for c in (await self._client.get_collections()).collections]
        if self._collection in existing:
            # A collection created before hybrid search has the sparse slot but
            # no IDF modifier. Setting it is an in-place params update — no
            # re-index, no data loss — and without it every sparse query would
            # score by raw term frequency. Best-effort: an older Qdrant that
            # rejects the update must not stop the app from booting, and dense
            # retrieval keeps working either way.
            try:
                await self._client.update_collection(
                    collection_name=self._collection,
                    sparse_vectors_config={SPARSE_VECTOR: _sparse_params()},
                )
            except Exception:  # pragma: no cover — depends on server version
                pass
            return
        await self._client.create_collection(
            collection_name=self._collection,
            vectors_config={
                DENSE_VECTOR: VectorParams(
                    size=settings.embed_dim,
                    distance=Distance.COSINE,
                ),
            },
            sparse_vectors_config={
                SPARSE_VECTOR: _sparse_params(),
            },
        )

    async def upsert_chunks(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
        batch_size: int = 200,
    ) -> None:
        points = []
        for chunk, emb in zip(chunks, embeddings):
            point_id = str(uuid.uuid4())
            payload: dict[str, Any] = {
                "document_id": chunk.document_id,
                "kb_id": chunk.kb_id,
                "filename": chunk.filename,
                "chunk_type": chunk.chunk_type.value,
                "content": chunk.content,
                "context_above": chunk.context_above,
                "context_below": chunk.context_below,
                "full_content": chunk.full_content,
                "page_num": chunk.page_num,
                "token_count": chunk.token_count,
                "metadata": chunk.metadata,
            }
            # The BM25 vector is built from `full_content` — the same string
            # that gets embedded — so the two branches see identical text and a
            # chunk cannot be findable by one and invisible to the other.
            indices, values = encode_document(chunk.full_content, settings.bm25_avg_doc_len)
            vectors: dict[str, Any] = {DENSE_VECTOR: emb}
            if indices:
                vectors[SPARSE_VECTOR] = SparseVector(indices=indices, values=values)
            points.append(PointStruct(id=point_id, vector=vectors, payload=payload))

        # Large documents (e.g. a 699-page price annex) can produce
        # thousands of points — one giant upsert() call for all of them at
        # once routinely hit httpx.WriteTimeout in practice. Batching keeps
        # each request small and lets progress survive a single batch
        # timing out (only that batch needs a retry/investigation, not the
        # whole document).
        for i in range(0, len(points), batch_size):
            await self._client.upsert(
                collection_name=self._collection,
                points=points[i : i + batch_size],
                wait=True,
            )

    async def search(
        self,
        query_vector: list[float],
        kb_id: str | list[str],
        top_k: int = 5,
        score_threshold: float = 0.5,  # see app/api/v1/chat.py::ChatRequest.score_threshold for why
        chunk_types: list[str] | None = None,
        metadata_filters: dict[str, str] | None = None,
        region: str | None = None,
        query_text: str = "",
    ) -> list[ScoredPoint]:
        """Hybrid retrieval: dense + BM25, fused with RRF (k=60), top-k out.

        `query_text` is the raw question, needed for the BM25 branch. Omitting
        it falls back to dense-only — the pre-hybrid behaviour — so no caller
        breaks, but every caller inside this repo passes it.

        metadata_filters matches against the nested `metadata` payload dict
        (e.g. {"region": "DN", "source_type": "official_annex"}) — used to
        scope RAG context to a price region/period without touching the
        structured material_prices table. The same filter is applied to BOTH
        branches, so region scoping (§10B) survives fusion intact.

        `kb_id` accepts a list too — used when the chat is scoped to a
        Project (several KBs bundled together) instead of a single KB, so
        retrieval matches any of them rather than exactly one.

        ─── On `score_threshold` and why it only guards the dense branch ───
        The threshold is a cosine bar. RRF scores are reciprocal ranks, and
        BM25 scores are unbounded, so neither is on that scale — applying 0.5
        to a fused score would either pass everything or drop everything.

        It stays on the DENSE prefetch, where it keeps the exact meaning it was
        chosen for: 0.3 let a question about Hồ Chí Minh's birthday surface
        construction-price PDFs at 31-33% and present them as citations, so 0.5
        is the "this chunk is actually about the query" bar.

        The BM25 branch is deliberately unthresholded — a chunk BM25 ranks
        first is often one dense scores ~0.45, and rejecting those would throw
        away the entire +67-question gain. What replaces the missing guard is
        `require_dense_support` below.
        """
        kb_condition = (
            FieldCondition(key="kb_id", match=MatchAny(any=kb_id))
            if isinstance(kb_id, list)
            else FieldCondition(key="kb_id", match=MatchValue(value=kb_id))
        )
        must_conditions = [kb_condition]
        if chunk_types:
            must_conditions.append(
                FieldCondition(key="chunk_type", match=MatchValue(value=chunk_types[0]))
            )
        for key, value in (metadata_filters or {}).items():
            must_conditions.append(
                FieldCondition(key=f"metadata.{key}", match=MatchValue(value=value))
            )
        # Region scoping that keeps region-agnostic chunks: match this region OR
        # chunks with no region tag at all (e.g. companion .md files uploaded via
        # the normal flow, or non-price knowledge chunks). A plain equality
        # filter would silently drop those, tanking recall for a region whose
        # data partly lives in untagged chunks — and worse, returning zero
        # sources so the answer looks un-grounded ("Plain chat — no RAG") even
        # when it isn't.
        if region:
            must_conditions.append(
                Filter(
                    should=[
                        FieldCondition(key="metadata.region", match=MatchValue(value=region)),
                        IsEmptyCondition(is_empty=PayloadField(key="metadata.region")),
                    ]
                )
            )

        query_filter = Filter(must=must_conditions)
        sparse_indices, sparse_values = encode_query(query_text) if query_text else ([], [])

        # No usable lexical signal (no query text, or a question made entirely
        # of stopwords) — there is nothing for BM25 to match on, so run the
        # dense query alone rather than fusing against an empty branch.
        if not sparse_indices:
            results = await self._client.query_points(
                collection_name=self._collection,
                query=query_vector,
                using=DENSE_VECTOR,
                query_filter=query_filter,
                limit=top_k,
                score_threshold=score_threshold,
                with_payload=True,
            )
            return results.points

        dense_branch = Prefetch(
            query=query_vector,
            using=DENSE_VECTOR,
            filter=query_filter,
            limit=PREFETCH_LIMIT,
            score_threshold=score_threshold,
        )
        sparse_branch = Prefetch(
            query=SparseVector(indices=sparse_indices, values=sparse_values),
            using=SPARSE_VECTOR,
            filter=query_filter,
            limit=PREFETCH_LIMIT,
        )

        if self._require_dense_support:
            # THE OFF-TOPIC GUARD, restated for hybrid.
            #
            # BM25 cannot tell "relevant" from "shares rare words with". In this
            # corpus that is a live hazard, not a hypothetical: "Hồ Chí Minh" is
            # both a person and a price region, so an off-topic question about
            # the person is a strong lexical match against every TP.HCM price
            # document. Unthresholded, the sparse branch would hand those back
            # as citations — reintroducing the exact failure the 0.5 dense bar
            # was raised to stop.
            #
            # The rule: BM25 may REORDER and EXTEND what dense found, but may
            # not answer on its own. If no chunk clears the dense bar, the
            # corpus has nothing on this question and the honest result is
            # nothing. Costs one extra round trip, issued concurrently below.
            #
            # This never fires on a genuine domain question — those always have
            # some chunk above the bar — so the measured +67 is unaffected.
            dense_probe, fused = await asyncio.gather(
                self._client.query_points(
                    collection_name=self._collection,
                    query=query_vector,
                    using=DENSE_VECTOR,
                    query_filter=query_filter,
                    limit=1,
                    score_threshold=score_threshold,
                    with_payload=False,
                ),
                self._client.query_points(
                    collection_name=self._collection,
                    prefetch=[dense_branch, sparse_branch],
                    query=FusionQuery(fusion=Fusion.RRF),
                    limit=top_k,
                    with_payload=True,
                ),
            )
            return fused.points if dense_probe.points else []

        results = await self._client.query_points(
            collection_name=self._collection,
            prefetch=[dense_branch, sparse_branch],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )
        return results.points

    async def delete_by_document(self, document_id: str) -> None:
        await self._client.delete(
            collection_name=self._collection,
            points_selector=Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
            ),
        )

    async def delete_by_kb(self, kb_id: str) -> None:
        """Every vector belonging to a knowledge base.

        Postgres cascades do not reach Qdrant. `KnowledgeBase.documents` has
        `cascade="all, delete-orphan"`, so deleting a KB removes its Document
        rows — and used to leave every one of their vectors behind. A
        production KB deletion left 4.060 orphaned points that way.

        Orphans are not inert. Retrieval filters on `kb_id`, which the stale
        payloads still carry, so they keep surfacing as citations for a
        knowledge base the user believes they deleted. Deleting by the same
        `kb_id` the filter matches on is what closes that.
        """
        await self._client.delete(
            collection_name=self._collection,
            points_selector=Filter(
                must=[FieldCondition(key="kb_id", match=MatchValue(value=kb_id))]
            ),
        )
