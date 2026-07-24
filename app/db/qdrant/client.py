"""Qdrant vector store — upsert chunks + hybrid search (dense + sparse BM25)."""
from __future__ import annotations

import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    NamedVector,
    PointStruct,
    ScoredPoint,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)

from app.config import settings
from app.core.chunking.models import Chunk, ChunkType


DENSE_VECTOR = "dense"
SPARSE_VECTOR = "sparse"


class QdrantStore:
    def __init__(self) -> None:
        self._client = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            api_key=settings.qdrant_api_key or None,
            check_compatibility=False,
        )
        self._collection = settings.qdrant_collection_name

    async def _ensure_connected(self) -> None:
        """Re-create client if needed (called before every operation)."""
        try:
            await self._client.get_collections()
        except Exception:
            self._client = AsyncQdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
                api_key=settings.qdrant_api_key or None,
                check_compatibility=False,
            )

    async def ensure_collection(self) -> None:
        existing = [c.name for c in (await self._client.get_collections()).collections]
        if self._collection in existing:
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
                SPARSE_VECTOR: SparseVectorParams(
                    index=SparseIndexParams(on_disk=False)
                ),
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
            points.append(
                PointStruct(
                    id=point_id,
                    vector={DENSE_VECTOR: emb},
                    payload=payload,
                )
            )

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
    ) -> list[ScoredPoint]:
        """metadata_filters matches against the nested `metadata` payload dict
        (e.g. {"region": "DN", "source_type": "official_annex"}) — used to
        scope RAG context to a price region/period without touching the
        structured material_prices table.

        `kb_id` accepts a list too — used when the chat is scoped to a
        Project (several KBs bundled together) instead of a single KB, so
        retrieval matches any of them rather than exactly one."""
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

        results = await self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            using=DENSE_VECTOR,
            query_filter=Filter(must=must_conditions),
            limit=top_k,
            score_threshold=score_threshold,
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
