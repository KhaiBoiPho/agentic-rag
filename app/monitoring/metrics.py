"""Prometheus metrics — application-level counters, histograms, gauges."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, make_asgi_app

# ─── HTTP ────────────────────────────────────────────────────────────────────
HTTP_REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)
HTTP_REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ─── gRPC ────────────────────────────────────────────────────────────────────
GRPC_REQUEST_COUNT = Counter(
    "grpc_requests_total",
    "Total gRPC requests",
    ["method", "status"],
)
GRPC_REQUEST_LATENCY = Histogram(
    "grpc_request_duration_seconds",
    "gRPC request latency",
    ["method"],
    buckets=[0.01, 0.1, 0.5, 1.0, 5.0, 30.0],
)

# ─── LLM ─────────────────────────────────────────────────────────────────────
LLM_REQUEST_LATENCY = Histogram(
    "llm_request_duration_seconds",
    "LLM request latency",
    ["model"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)
LLM_TOKEN_COUNT = Counter(
    "llm_tokens_total",
    "Total LLM tokens",
    ["model", "direction"],  # direction: input | output
)

# ─── Ingestion ───────────────────────────────────────────────────────────────
INGESTION_CHUNK_COUNT = Counter(
    "ingestion_chunks_total",
    "Total chunks indexed",
)
INGESTION_DURATION = Histogram(
    "ingestion_duration_seconds",
    "Document ingestion duration",
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)

# ─── Queue ───────────────────────────────────────────────────────────────────
QUEUE_DEPTH = Gauge(
    "rabbitmq_queue_depth",
    "Estimated RabbitMQ queue depth",
    ["queue"],
)

# ─── Active connections ───────────────────────────────────────────────────────
ACTIVE_GRPC_STREAMS = Gauge(
    "active_grpc_streams",
    "Currently active gRPC streams",
)


def init_metrics(app) -> None:
    """Mount Prometheus metrics endpoint at /metrics."""
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)
