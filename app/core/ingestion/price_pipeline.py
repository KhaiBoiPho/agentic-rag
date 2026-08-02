"""Price-document ingestion pipeline — for Sở Xây dựng price-announcement
PDFs (công văn + phụ lục) and vendor/manufacturer quote PDFs.

Runs two things from the same PDF:
  1. The normal chunk -> embed -> Qdrant flow (via ChunkDispatcher), so the
     legal/context text (điều kiện giá, phạm vi áp dụng) stays searchable
     for RAG — each chunk is tagged with region/source_type/price_period in
     its metadata so retrieval can filter to the right region/period.
  2. Structured table extraction (price_extractor.extract_price_rows) into
     the material_prices table, which is what the price-lookup tool queries
     for exact answers instead of relying on semantic search.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from app.core.chunking.base import (
    enforce_chunk_caps,
)
from app.core.chunking.dispatcher import ChunkDispatcher
from app.core.ingestion.price_extractor import classify_source_file, extract_price_rows
from app.core.llm.openrouter import OpenRouterClient
from app.db.postgres.repositories.document_repo import DocumentRepository
from app.db.postgres.repositories.material_price_repo import MaterialPriceRepository
from app.db.qdrant.client import QdrantStore

logger = logging.getLogger(__name__)


class PriceExtractionPipeline:
    def __init__(self) -> None:
        self._llm = OpenRouterClient()
        self._qdrant = QdrantStore()
        self._doc_repo = DocumentRepository()
        self._price_repo = MaterialPriceRepository()

    async def ingest_stream(
        self,
        job_id: str,
        kb_id: str,
        user_id: str,
        filename: str,
        content: bytes,
        config: dict,
    ) -> AsyncGenerator[dict, None]:
        region = config.get("region", "")
        price_period = config.get("price_period", "")

        source_type = classify_source_file(filename)

        doc = await self._doc_repo.create(kb_id=kb_id, user_id=user_id, filename=filename)
        doc_id = str(doc.id)

        # The API rejects a price upload without a region, so this only fires
        # for a job published some other way. The document row is created
        # first on purpose: bailing out before creating it (the original
        # behaviour) left the upload looking silently lost — a job id was
        # returned, then nothing ever appeared in the KB.
        if not region:
            msg = "Thiếu vùng giá (HN | DN | HCM) — không trích xuất được dữ liệu giá."
            await self._doc_repo.update_status(doc_id, "error", error=msg)
            yield {"stage": "error", "error": msg, "progress": 0.0, "done": True}
            return

        await self._doc_repo.update_status(doc_id, "processing")
        await self._doc_repo.set_metadata(
            doc_id, {"region": region, "source_type": source_type, "price_period": price_period}
        )

        yield {"stage": "parsing", "progress": 0.1, "done": False}

        # 1. Narrative chunks -> Qdrant (context for RAG)
        try:
            dispatcher = ChunkDispatcher(
                chunk_token_num=config.get("chunk_token_num", 512),
                overlap_percent=config.get("chunk_overlap_pct", 15),
                table_context_size=config.get("table_context_size", 128),
            )
            chunks = dispatcher.chunk(
                filename=filename, content=content, document_id=doc_id, kb_id=kb_id
            )
        except Exception as exc:
            await self._doc_repo.update_status(doc_id, "error", error=str(exc))
            yield {"stage": "error", "error": str(exc), "progress": 0.0, "done": True}
            return

        # Tables recovered by OCR, if any — a scanned PDF yields nothing to
        # pdfplumber, so without these its price rows would be lost entirely.
        ocr_tables = None
        if not chunks and filename.lower().endswith(".pdf"):
            yield {"stage": "ocr", "progress": 0.2, "done": False}
            try:
                from app.core.ingestion.ocr_fallback import ocr_pdf_to_document

                ocr = await ocr_pdf_to_document(
                    content,
                    filename,
                    doc_id,
                    kb_id,
                    chunk_token_num=config.get("chunk_token_num", 512),
                    overlap_percent=config.get("chunk_overlap_pct", 15),
                    table_context_size=config.get("table_context_size", 128),
                )
                chunks = ocr.chunks
                ocr_tables = ocr.tables or None
            except Exception as exc:
                logger.warning("OCR fallback failed doc_id=%s file=%s: %s", doc_id, filename, exc)

        for c in chunks:
            c.metadata.update(
                {"region": region, "source_type": source_type, "price_period": price_period}
            )

        chunks = enforce_chunk_caps(chunks, doc_id, logger)

        yield {"stage": "chunking", "progress": 0.25, "chunks_total": len(chunks), "done": False}

        from app.config import settings

        batch_size = settings.embed_batch_size
        embeddings: list[list[float]] = []
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            try:
                embeddings.extend(await self._llm.embed([c.full_content for c in batch]))
            except Exception as exc:
                await self._doc_repo.update_status(doc_id, "error", error=str(exc))
                yield {"stage": "error", "error": str(exc), "progress": 0.0, "done": True}
                return
            yield {
                "stage": "embedding",
                "progress": 0.25 + 0.35 * (min(i + batch_size, len(chunks)) / max(len(chunks), 1)),
                "chunks_done": min(i + batch_size, len(chunks)),
                "chunks_total": len(chunks),
                "done": False,
            }

        if chunks:
            try:
                await self._qdrant.upsert_chunks(chunks, embeddings)
            except Exception as exc:
                await self._doc_repo.update_status(doc_id, "error", error=str(exc))
                yield {"stage": "error", "error": str(exc), "progress": 0.0, "done": True}
                return

        # 2. Structured price rows -> Postgres
        yield {"stage": "extracting_prices", "progress": 0.7, "done": False}
        try:
            result = extract_price_rows(
                content,
                region=region,
                source_type=source_type,
                filename=filename,
                tables=ocr_tables,
                # OCR grids carry no cell geometry, so a table-wide merged
                # unit needs the textual fallback — see _fill_table_wide_unit.
                assume_column_merges=ocr_tables is not None,
            )
        except Exception as exc:
            await self._doc_repo.update_status(doc_id, "error", error=str(exc))
            yield {"stage": "error", "error": str(exc), "progress": 0.0, "done": True}
            return

        if price_period:
            for r in result.rows:
                r.price_period = price_period

        try:
            price_row_count = await self._price_repo.bulk_create(doc_id, kb_id, result.rows)
        except Exception as exc:
            await self._doc_repo.update_status(doc_id, "error", error=str(exc))
            yield {"stage": "error", "error": str(exc), "progress": 0.0, "done": True}
            return

        if result.warnings:
            logger.warning(
                "price extraction warnings doc_id=%s filename=%s count=%d sample=%s",
                doc_id,
                filename,
                len(result.warnings),
                result.warnings[:5],
            )
        await self._doc_repo.set_metadata(
            doc_id, {"price_row_count": price_row_count, "warning_count": len(result.warnings)}
        )

        await self._doc_repo.update_status(doc_id, "done", chunk_count=len(chunks))

        logger.info(
            "Price ingestion complete doc_id=%s chunks=%d price_rows=%d warnings=%d",
            doc_id,
            len(chunks),
            price_row_count,
            len(result.warnings),
        )
        yield {
            "stage": "done",
            "progress": 1.0,
            "chunks_done": len(chunks),
            "chunks_total": len(chunks),
            "price_rows": price_row_count,
            "warnings": len(result.warnings),
            "done": True,
        }
