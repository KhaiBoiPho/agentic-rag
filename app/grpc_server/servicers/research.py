"""gRPC ResearchService — streams 6-node LangGraph deep research progress."""

from __future__ import annotations

import logging

import grpc

from app.core.research.graph import DeepResearchGraph
from app.grpc_server.generated import research_pb2, research_pb2_grpc

logger = logging.getLogger(__name__)


class ResearchServicer(research_pb2_grpc.ResearchServiceServicer):
    def __init__(self) -> None:
        self._graph = DeepResearchGraph()

    async def DeepResearch(
        self,
        request: research_pb2.ResearchRequest,
        context: grpc.aio.ServicerContext,
    ):
        config = {
            "max_iterations": request.config.max_iterations or 3,
            "max_search_results": request.config.max_search_results or 10,
            "quality_threshold": request.config.quality_threshold or 0.75,
        }
        try:
            async for event in self._graph.stream(
                query=request.query,
                user_id=request.user_id,
                config=config,
            ):
                sources = [
                    research_pb2.SearchResult(
                        url=s.get("url", ""),
                        title=s.get("title", ""),
                        snippet=s.get("snippet", ""),
                    )
                    for s in event.get("sources", [])
                ]
                yield research_pb2.ResearchStreamChunk(
                    node=event["node"],
                    status=_status_map(event["status"]),
                    content=event.get("content", ""),
                    progress=event.get("progress", 0.0),
                    sources=sources,
                    error=event.get("error", ""),
                    done=event.get("done", False),
                    iteration=event.get("iteration", 0),
                )

        except Exception as exc:
            logger.exception("DeepResearch error")
            yield research_pb2.ResearchStreamChunk(
                node="error",
                status=research_pb2.FAILED,
                error=str(exc),
                done=True,
            )

    async def GetHistory(
        self,
        request: research_pb2.ResearchHistoryRequest,
        context: grpc.aio.ServicerContext,
    ) -> research_pb2.ResearchHistoryResponse:
        return research_pb2.ResearchHistoryResponse(records=[], total=0)


def _status_map(s: str) -> int:
    return {
        "started": research_pb2.STARTED,
        "running": research_pb2.RUNNING,
        "completed": research_pb2.COMPLETED,
        "failed": research_pb2.FAILED,
    }.get(s, research_pb2.RUNNING)
