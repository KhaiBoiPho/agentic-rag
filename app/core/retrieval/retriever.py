"""RAG retriever — dense vector search via Qdrant."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.llm.openrouter import OpenRouterClient
from app.core.retrieval.sparse import encode_query
from app.db.qdrant.client import QdrantStore


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    document_name: str
    content: str
    score: float
    page_num: int
    chunk_type: str
    # Domain metadata carried on price chunks (see price_pipeline.py) — needed
    # so the chat layer can tell the LLM which region a price chunk is for,
    # otherwise it can present e.g. a Đà Nẵng price as if it were the Cần Thơ
    # price the user asked about.
    region: str = ""
    price_period: str = ""
    # What `score` MEANS. Hybrid retrieval fuses two rankings with RRF, and an
    # RRF score is a sum of reciprocal ranks (~0,033 for a top hit) — it is not
    # a similarity and rendering it as "3%" is nonsense. Consumers use this to
    # decide whether the number is presentable, rather than guessing from its
    # magnitude. "cosine" only occurs on the dense-only fallback.
    score_kind: str = "cosine"  # "cosine" | "rrf"


class Retriever:
    def __init__(self) -> None:
        self._llm = OpenRouterClient()
        self._qdrant = QdrantStore()

    async def search(
        self,
        query: str,
        kb_id: str | list[str],
        top_k: int = 5,
        score_threshold: float = 0.5,  # see app/api/v1/chat.py::ChatRequest.score_threshold for why
        metadata_filters: dict[str, str] | None = None,
        region: str | None = None,
    ) -> list[RetrievedChunk]:
        """`kb_id` accepts a list of KB ids (Project mode — search across
        every KB bundled into the project, ranked together by score) or a
        single id (normal single-KB chat). `region` scopes to a price region
        while still keeping region-agnostic chunks (see QdrantStore.search).

        Retrieval is HYBRID: the same `query` is both embedded for the dense
        branch and tokenized for BM25, and the two rankings are fused with RRF.
        `score` on the returned chunks is therefore an RRF score, not a cosine
        — comparable within one result set, not across queries, and not
        against the 0.5 threshold (which now guards the dense branch inside
        QdrantStore.search)."""
        # Embed the query
        query_embs = await self._llm.embed([query])
        query_vec = query_embs[0]

        # Mirrors QdrantStore.search's own fallback rule: with no lexical
        # tokens there is no sparse branch, so no fusion, so the score really
        # is a cosine.
        score_kind = "rrf" if encode_query(query)[0] else "cosine"

        # Search Qdrant — dense + BM25, fused
        scored_points = await self._qdrant.search(
            query_vector=query_vec,
            kb_id=kb_id,
            top_k=top_k,
            score_threshold=score_threshold,
            metadata_filters=metadata_filters,
            region=region,
            query_text=query,
        )

        results: list[RetrievedChunk] = []
        for pt in scored_points:
            p = pt.payload or {}
            meta = p.get("metadata") or {}
            results.append(
                RetrievedChunk(
                    chunk_id=str(pt.id),
                    document_id=p.get("document_id", ""),
                    document_name=p.get("filename", ""),
                    content=p.get("full_content") or p.get("content", ""),
                    score=pt.score,
                    page_num=p.get("page_num", 0),
                    chunk_type=p.get("chunk_type", "text"),
                    region=meta.get("region", ""),
                    price_period=meta.get("price_period", ""),
                    score_kind=score_kind,
                )
            )
        return results
