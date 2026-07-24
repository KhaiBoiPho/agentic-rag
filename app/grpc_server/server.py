"""gRPC server — runs alongside FastAPI on a separate port."""

from __future__ import annotations

import logging

import grpc
from grpc_reflection.v1alpha import reflection

from app.grpc_server.generated import (
    chat_pb2,
    chat_pb2_grpc,
    document_pb2,
    document_pb2_grpc,
    research_pb2,
    research_pb2_grpc,
)
from app.grpc_server.servicers.chat import ChatServicer
from app.grpc_server.servicers.document import DocumentServicer
from app.grpc_server.servicers.research import ResearchServicer
from app.monitoring.metrics import GRPC_REQUEST_COUNT

logger = logging.getLogger(__name__)


class MetricsInterceptor(grpc.aio.ServerInterceptor):
    async def intercept_service(self, continuation, handler_call_details):
        method = handler_call_details.method
        try:
            handler = await continuation(handler_call_details)
            GRPC_REQUEST_COUNT.labels(method=method, status="ok").inc()
            return handler
        except Exception:
            GRPC_REQUEST_COUNT.labels(method=method, status="error").inc()
            raise


async def create_grpc_server(host: str, port: int) -> grpc.aio.Server:
    server = grpc.aio.server(
        interceptors=[MetricsInterceptor()],
        options=[
            ("grpc.max_send_message_length", 100 * 1024 * 1024),
            ("grpc.max_receive_message_length", 100 * 1024 * 1024),
            ("grpc.keepalive_time_ms", 30_000),
            ("grpc.keepalive_timeout_ms", 10_000),
        ],
    )

    chat_pb2_grpc.add_ChatServiceServicer_to_server(ChatServicer(), server)
    document_pb2_grpc.add_DocumentServiceServicer_to_server(DocumentServicer(), server)
    research_pb2_grpc.add_ResearchServiceServicer_to_server(ResearchServicer(), server)

    # Enable reflection for grpcurl / grpc-gateway
    service_names = (
        chat_pb2.DESCRIPTOR.services_by_name["ChatService"].full_name,
        document_pb2.DESCRIPTOR.services_by_name["DocumentService"].full_name,
        research_pb2.DESCRIPTOR.services_by_name["ResearchService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)

    server.add_insecure_port(f"{host}:{port}")
    logger.info(f"gRPC server listening on {host}:{port}")
    return server


async def serve(host: str = "0.0.0.0", port: int = 50051) -> None:
    server = await create_grpc_server(host, port)
    await server.start()
    await server.wait_for_termination()
