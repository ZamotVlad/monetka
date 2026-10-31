"""Metrics for Prometheus and JSON logs that carry the request id."""

import json
import logging
import time
import uuid
from contextvars import ContextVar
from typing import Any

from prometheus_client import Counter, Gauge, Histogram
from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id: ContextVar[str] = ContextVar("request_id", default="-")

HTTP_REQUESTS = Counter(
    "monetka_http_requests_total", "HTTP requests", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "monetka_http_request_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
IDEMPOTENT_REPLAYS = Counter("monetka_idempotent_replays_total", "Retries answered from storage")
RATE_LIMITED = Counter("monetka_rate_limited_total", "Requests refused by the rate limiter")
WEBHOOKS = Counter("monetka_webhooks_total", "Provider webhooks by outcome", ["result"])
WEBSOCKETS = Gauge("monetka_websocket_connections", "Open WebSocket connections")
OUTBOX_PUBLISHED = Counter("monetka_outbox_published_total", "Events shipped to Kafka")
OUTBOX_BACKLOG = Gauge("monetka_outbox_backlog", "Events waiting in the outbox")
PAYMENTS_EXPIRED = Counter("monetka_payments_expired_total", "Payments closed by deadline")
BOOKS_BALANCED = Gauge("monetka_books_balanced", "1 if the last reconciliation passed")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id.get(),
        }
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


# Cheap browser-side protection: no MIME sniffing, no framing (clickjacking), no full URLs
# leaking to other sites in the Referer header
SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"same-origin"),
]


class RequestContextMiddleware:
    """Tags each request with an id and records its metrics.

    Plain ASGI rather than BaseHTTPMiddleware: no extra task per request, and the
    request id context variable is visible to the endpoint's own logs.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope["headers"]).get(b"x-request-id", b"").decode()
        current = incoming if 0 < len(incoming) <= 64 else uuid.uuid4().hex
        token = request_id.set(current)
        status = 500
        started = time.perf_counter()

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [
                    *message["headers"],
                    (b"x-request-id", current.encode()),
                    *SECURITY_HEADERS,
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            # The route template, not the raw path: /payments/{id}, not one label per payment.
            # Newer FastAPI keeps included routes without their prefix and puts the full
            # template in its own context, so look there first.
            context = scope.get("fastapi", {}).get("effective_route_context")
            route = scope.get("route")
            label = getattr(context, "path", None) or getattr(route, "path", "unmatched")
            HTTP_REQUESTS.labels(scope["method"], label, str(status)).inc()
            HTTP_LATENCY.labels(scope["method"], label).observe(time.perf_counter() - started)
            request_id.reset(token)
