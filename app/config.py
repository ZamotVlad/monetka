from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings read from environment variables and an optional .env file."""

    # Unknown keys in .env are a typo more often than not, so they fail loudly
    model_config = SettingsConfigDict(env_file=".env", extra="forbid")

    environment: Literal["local", "test", "production"] = "local"
    database_url: str = "postgresql+asyncpg://monetka:monetka@localhost:5432/monetka"
    redis_url: str = "redis://localhost:6379/0"
    probe_timeout_seconds: float = 2.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
