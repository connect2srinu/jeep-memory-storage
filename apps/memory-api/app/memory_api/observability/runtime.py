from __future__ import annotations

import json
import logging
import time
from collections import Counter
from contextvars import ContextVar
from threading import Lock
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

correlation_id_context: ContextVar[str] = ContextVar("correlation_id", default="unknown")


class RuntimeMetrics:
    def __init__(self) -> None:
        self._counters: Counter[tuple[str, str]] = Counter()
        self._lock = Lock()

    def record(self, path: str, status: int) -> None:
        with self._lock:
            self._counters[(path, str(status))] += 1

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {f"{path}|{status}": count for (path, status), count in self._counters.items()}


class CorrelationAndMetricsMiddleware:
    def __init__(self, app: ASGIApp, metrics: RuntimeMetrics) -> None:
        self.app = app
        self.metrics = metrics
        self.logger = logging.getLogger("memory_api.runtime")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        correlation_id = headers.get(b"x-correlation-id", b"").decode().strip() or str(uuid4())
        token = correlation_id_context.set(correlation_id)
        started = time.perf_counter()
        status = 500

        async def send_with_headers(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-correlation-id", correlation_id.encode()))
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        finally:
            path = str(scope.get("path", "unknown"))
            self.metrics.record(path, status)
            self.logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "correlation_id": correlation_id,
                        "method": scope.get("method"),
                        "path": path,
                        "status": status,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    },
                    sort_keys=True,
                )
            )
            correlation_id_context.reset(token)
