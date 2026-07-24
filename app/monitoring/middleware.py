"""Prometheus middleware — records HTTP request count + latency per endpoint."""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.monitoring.metrics import HTTP_REQUEST_COUNT, HTTP_REQUEST_LATENCY


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        endpoint = request.url.path
        method = request.method
        status = str(response.status_code)

        HTTP_REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code=status).inc()
        HTTP_REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(elapsed)

        return response
