import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api import (
    auth,
    deposits,
    health,
    merchant,
    metrics,
    payments,
    statements,
    transfers,
    wallet,
    ws,
)
from app.api.errors import register_error_handlers
from app.cache import create_redis
from app.config import Settings, get_settings
from app.db.session import create_engine, create_session_factory
from app.integrations.storage import S3Storage
from app.messaging.kafka import consume_forever
from app.observability import RequestContextMiddleware, configure_logging
from app.realtime import Hub


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    configure_logging(settings.log_level)
    engine = create_engine(settings.database_url)
    redis = create_redis(settings.redis_url)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.redis = redis
    app.state.hub = hub = Hub()
    app.state.storage = storage = S3Storage(settings)
    await storage.ensure_bucket()
    consumer = None
    if settings.kafka_enabled:
        consumer = asyncio.create_task(
            consume_forever(settings.kafka_bootstrap_servers, hub.dispatch)
        )
    try:
        yield
    finally:
        if consumer is not None:
            consumer.cancel()
            with suppress(asyncio.CancelledError):
                await consumer
        await redis.aclose()
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """A factory instead of a module-level app, so each test can build one with its own settings."""
    app = FastAPI(title="Monetka", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings or get_settings()
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    for router in (
        health.router,
        auth.router,
        wallet.router,
        transfers.router,
        payments.router,
        merchant.router,
        deposits.router,
        ws.router,
        statements.router,
    ):
        app.include_router(router, prefix="/api/v1")
    app.include_router(metrics.router)
    return app


app = create_app()
