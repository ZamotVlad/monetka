from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.cache import create_redis
from app.config import Settings, get_settings
from app.db.session import create_engine, create_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = create_engine(settings.database_url)
    redis = create_redis(settings.redis_url)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.redis = redis
    try:
        yield
    finally:
        await redis.aclose()
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """A factory instead of a module-level app, so each test can build one with its own settings."""
    app = FastAPI(title="Monetka", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings or get_settings()
    app.include_router(health.router, prefix="/api/v1")
    return app


app = create_app()
