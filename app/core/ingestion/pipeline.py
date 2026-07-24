"""Document ingestion pipeline — parse → chunk → embed → store.

Yields progress events so gRPC servicer can stream them back to the client.
"""
from __future__ import annotations

import logging
from typing import AsyncGenerator

from app.core.chunking.base import MAX_EMBED_TOKENS, split_oversized_table_chunk
from app.core.chunking.dispatcher import ChunkDispatcher
from app.core.llm.openrouter import OpenRouterClient
from app.db.postgres.repositories.document_repo import DocumentRepository
from app.db.qdrant.client import QdrantStore
from app.monitoring.metrics import INGESTION_CHUNK_COUNT, INGESTION_DURATION

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(self) -> None:
        self._llm = OpenRouterClient()
        self._qdrant = QdrantStore()
        self._doc_repo = DocumentRepository()

    async def ingest_stream(
        self,
        job_id: str,
        kb_id: str,
        user_id: str,
        filename: str,
        content: bytes,
        config: dict,
    ) -> AsyncGenerator[dict, None]:
        import time
        t0 = time.perf_counter()

        chunk_token_num = config.get("chunk_token_num", 512)
        overlap_pct = config.get("chunk_overlap_pct", 15)
        table_ctx = config.get("table_context_size", 128)

        # 1. Register document in PostgreSQL
        doc = await self._doc_repo.create(kb_id=kb_id, user_id=user_id, filename=filename)
        doc_id = str(doc.id)
        await self._doc_repo.update_status(doc_id, "processing")

        yield {"stage": "parsing", "progress": 0.1, "done": False}

        # 2. Chunk
        try:
            dispatcher = ChunkDispatcher(
                chunk_token_num=chunk_token_num,
                overlap_percent=overlap_pct,
                table_context_size=table_ctx,
            )
            chunks = dispatcher.chunk(
                filename=filename,
                content=content,
                document_id=doc_id,
                kb_id=kb_id,
            )
        except Exception as exc:
            await self._doc_repo.update_status(doc_id, "error", error=str(exc))
            yield {"stage": "error", "error": str(exc), "progress": 0.0, "done": True}
            return

        if not chunks and filename.lower().endswith(".pdf"):
            yield {"stage": "ocr", "progress": 0.2, "done": False}
            try:
                from app.core.ingestion.ocr_fallback import ocr_pdf_to_chunks
                chunks = await ocr_pdf_to_chunks(
                    content, filename, doc_id, kb_id,
                    chunk_token_num=chunk_token_num, overlap_percent=overlap_pct,
                )
            except Exception as exc:
                logger.warning("OCR fallback failed doc_id=%s file=%s: %s", doc_id, filename, exc)

        oversized_count = sum(1 for c in chunks if c.token_count > MAX_EMBED_TOKENS)
        if oversized_count:
            expanded: list = []
            for c in chunks:
                expanded.extend(split_oversized_table_chunk(c))
            still_oversized = sum(1 for c in expanded if c.token_count > MAX_EMBED_TOKENS)
            if still_oversized:
                logger.warning(
                    "doc_id=%s: %d chunk(s) still exceed %d tokens after table-splitting "
                    "(non-table content or a single oversized cell) — dropping them",
                    doc_id, still_oversized, MAX_EMBED_TOKENS,
                )
                expanded = [c for c in expanded if c.token_count <= MAX_EMBED_TOKENS]
            logger.info(
                "doc_id=%s: split %d oversized table chunk(s) into %d smaller chunks",
                doc_id, oversized_count, len(expanded) - (len(chunks) - oversized_count),
            )
            chunks = expanded

        total = len(chunks)
        yield {"stage": "chunking", "progress": 0.3, "chunks_total": total, "done": False}

        # 3. Embed in batches
        from app.config import settings
        batch_size = settings.embed_batch_size
        embeddings: list[list[float]] = []

        for i in range(0, total, batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.full_content for c in batch]
            try:
                batch_embs = await self._llm.embed(texts)
                embeddings.extend(batch_embs)
            except Exception as exc:
                await self._doc_repo.update_status(doc_id, "error", error=str(exc))
                yield {"stage": "error", "error": str(exc), "progress": 0.0, "done": True}
                return

            done_count = min(i + batch_size, total)
            progress = 0.3 + 0.5 * (done_count / total)
            yield {
                "stage": "embedding",
                "progress": progress,
                "chunks_done": done_count,
                "chunks_total": total,
                "done": False,
            }

        # 4. Store in Qdrant
        yield {"stage": "indexing", "progress": 0.9, "chunks_total": total, "done": False}
        try:
            await self._qdrant.upsert_chunks(chunks, embeddings)
        except Exception as exc:
            await self._doc_repo.update_status(doc_id, "error", error=str(exc))
            yield {"stage": "error", "error": str(exc), "progress": 0.0, "done": True}
            return

        # 5. Update document status
        await self._doc_repo.update_status(doc_id, "done", chunk_count=total)

        elapsed = time.perf_counter() - t0
        INGESTION_CHUNK_COUNT.inc(total)
        INGESTION_DURATION.observe(elapsed)

        logger.info("Ingestion complete doc_id=%s chunks=%d elapsed=%.2fs", doc_id, total, elapsed)
        yield {"stage": "done", "progress": 1.0, "chunks_done": total, "chunks_total": total, "done": True}
