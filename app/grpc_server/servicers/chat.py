"""gRPC ChatService — bridges OpenRouter SSE stream → gRPC server-stream."""

from __future__ import annotations

import logging
import uuid

import grpc

from app.core.llm.openrouter import OpenRouterClient
from app.core.retrieval.retriever import Retriever
from app.grpc_server.generated import chat_pb2, chat_pb2_grpc

logger = logging.getLogger(__name__)


class ChatServicer(chat_pb2_grpc.ChatServiceServicer):
    def __init__(self) -> None:
        self._llm = OpenRouterClient()
        self._retriever = Retriever()

    async def StreamChat(
        self,
        request: chat_pb2.ChatRequest,
        context: grpc.aio.ServicerContext,
    ):
        chunk_id = str(uuid.uuid4())
        sources_proto: list[chat_pb2.RagSource] = []

        try:
            # 1. RAG retrieval
            if request.config.use_rag and request.kb_id:
                chunks = await self._retriever.search(
                    query=request.message,
                    kb_id=request.kb_id,
                    top_k=request.config.top_k or 5,
                    score_threshold=request.config.score_threshold or 0.3,
                )
                sources_proto = [
                    chat_pb2.RagSource(
                        chunk_id=c.chunk_id,
                        document_id=c.document_id,
                        document_name=c.document_name,
                        content=c.content,
                        score=c.score,
                        page_num=c.page_num,
                    )
                    for c in chunks
                ]
                context_text = "\n\n".join(
                    f"[Source {i + 1}]: {c.content}" for i, c in enumerate(chunks)
                )
            else:
                context_text = ""

            # 2. Build messages
            system_prompt = (
                "You are a helpful AI assistant. Answer based on the provided context "
                "when available. Be concise and accurate."
            )
            user_message = request.message
            if context_text:
                user_message = f"Context:\n{context_text}\n\nQuestion: {request.message}"

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]

            # 3. Stream tokens from OpenRouter → gRPC
            async for token in self._llm.stream_chat(
                messages=messages,
                model=request.config.model or None,
                temperature=request.config.temperature or 0.7,
                max_tokens=request.config.max_tokens or 2048,
            ):
                yield chat_pb2.ChatStreamChunk(
                    delta=token,
                    chunk_id=chunk_id,
                    type=chat_pb2.TOKEN,
                    done=False,
                )

            # 4. Final chunk with sources
            yield chat_pb2.ChatStreamChunk(
                chunk_id=chunk_id,
                type=chat_pb2.DONE,
                sources=sources_proto,
                done=True,
            )

        except Exception as exc:
            logger.exception("StreamChat error")
            yield chat_pb2.ChatStreamChunk(
                chunk_id=chunk_id,
                type=chat_pb2.ERROR,
                error=str(exc),
                done=True,
            )

    async def GetHistory(
        self,
        request: chat_pb2.ChatHistoryRequest,
        context: grpc.aio.ServicerContext,
    ) -> chat_pb2.ChatHistoryResponse:
        # TODO: fetch from PostgreSQL conversation table
        return chat_pb2.ChatHistoryResponse(messages=[], total=0)
