"""gRPC DocumentService — streams ingestion progress back to client."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator

import grpc

from app.core.ingestion.pipeline import IngestionPipeline
from app.grpc_server.generated import document_pb2, document_pb2_grpc

logger = logging.getLogger(__name__)


class DocumentServicer(document_pb2_grpc.DocumentServiceServicer):
    def __init__(self) -> None:
        self._pipeline = IngestionPipeline()

    async def IngestDocument(
        self,
        request: document_pb2.IngestRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncGenerator[document_pb2.IngestProgressChunk, None]:
        job_id = str(uuid.uuid4())

        try:
            async for event in self._pipeline.ingest_stream(
                job_id=job_id,
                kb_id=request.kb_id,
                user_id=request.user_id,
                filename=request.filename,
                content=request.content,
                config={
                    "chunk_token_num": request.config.chunk_token_num or 512,
                    "chunk_overlap_pct": request.config.chunk_overlap_pct or 15,
                    "table_context_size": request.config.table_context_size or 128,
                    "delimiter": request.config.delimiter or "\n!?。；！？",
                },
            ):
                yield document_pb2.IngestProgressChunk(
                    job_id=job_id,
                    stage=event["stage"],
                    progress=event["progress"],
                    chunks_done=event.get("chunks_done", 0),
                    chunks_total=event.get("chunks_total", 0),
                    error=event.get("error", ""),
                    done=event.get("done", False),
                )

        except Exception as exc:
            logger.exception("IngestDocument error job_id=%s", job_id)
            yield document_pb2.IngestProgressChunk(
                job_id=job_id,
                stage="error",
                error=str(exc),
                done=True,
            )

    async def ListDocuments(
        self,
        request: document_pb2.DocumentListRequest,
        context: grpc.aio.ServicerContext,
    ) -> document_pb2.DocumentListResponse:
        from app.db.postgres.repositories.document_repo import DocumentRepository

        repo = DocumentRepository()
        docs, total = await repo.list_by_kb(
            kb_id=request.kb_id,
            user_id=request.user_id,
            limit=request.limit or 20,
            offset=request.offset or 0,
        )
        return document_pb2.DocumentListResponse(
            documents=[
                document_pb2.DocumentMeta(
                    id=str(d.id),
                    kb_id=str(d.kb_id),
                    filename=d.filename,
                    status=d.status,
                    chunk_count=d.chunk_count,
                    created_at=int(d.created_at.timestamp()),
                    updated_at=int(d.updated_at.timestamp()),
                )
                for d in docs
            ],
            total=total,
        )

    async def DeleteDocument(
        self,
        request: document_pb2.DeleteDocumentRequest,
        context: grpc.aio.ServicerContext,
    ) -> document_pb2.DeleteDocumentResponse:
        from app.db.postgres.repositories.document_repo import DocumentRepository
        from app.db.qdrant.client import QdrantStore

        repo = DocumentRepository()
        qdrant = QdrantStore()
        try:
            await qdrant.delete_by_document(request.document_id)
            await repo.delete(request.document_id, request.user_id)
            return document_pb2.DeleteDocumentResponse(success=True, message="Deleted")
        except Exception as exc:
            return document_pb2.DeleteDocumentResponse(success=False, message=str(exc))
