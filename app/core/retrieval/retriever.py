"""RAG retriever — dense vector search via Qdrant."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.llm.openrouter import OpenRouterClient
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
    ) -> list[RetrievedChunk]:
        """`kb_id` accepts a list of KB ids (Project mode — search across
        every KB bundled into the project, ranked together by score) or a
        single id (normal single-KB chat)."""
        # Embed the query
        query_embs = await self._llm.embed([query])
        query_vec = query_embs[0]

        # Search Qdrant
        scored_points = await self._qdrant.search(
            query_vector=query_vec,
            kb_id=kb_id,
            top_k=top_k,
            score_threshold=score_threshold,
            metadata_filters=metadata_filters,
        )

        results: list[RetrievedChunk] = []
        for pt in scored_points:
            p = pt.payload or {}
            results.append(
                RetrievedChunk(
                    chunk_id=str(pt.id),
                    document_id=p.get("document_id", ""),
                    document_name=p.get("filename", ""),
                    content=p.get("full_content") or p.get("content", ""),
                    score=pt.score,
                    page_num=p.get("page_num", 0),
                    chunk_type=p.get("chunk_type", "text"),
                )
            )
        return results
