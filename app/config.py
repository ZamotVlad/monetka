from functools import lru_cache
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "local-dev-jwt-secret-change-me-in-production"
DEV_PSP_SECRET = "local-dev-psp-secret-change-me-in-production"


class Settings(BaseSettings):
    # extra="forbid" turns a typo in .env into a startup error instead of a silent default
    model_config = SettingsConfigDict(env_file=".env", extra="forbid")

    environment: Literal["local", "test", "production"] = "local"
    database_url: str = "postgresql+asyncpg://monetka:monetka@localhost:5432/monetka"
    redis_url: str = "redis://localhost:6379/0"
    probe_timeout_seconds: float = 2.0

    jwt_secret: str = DEV_JWT_SECRET
    jwt_ttl_minutes: int = 60
    bcrypt_rounds: int = 12

    public_url: str = "http://localhost:8000"
    psp_checkout_url: str = "http://localhost:8001/checkout"
    # Where the provider sends webhooks; inside Docker that is the api service, not localhost
    psp_callback_url: str = "http://localhost:8000/api/v1/webhooks/psp"
    psp_secret: str = DEV_PSP_SECRET
    webhook_tolerance_seconds: int = 300

    payment_request_ttl_hours: int = 24
    hold_ttl_days: int = 7

    auth_rate_limit_per_minute: int = 10
    money_rate_limit_per_minute: int = 60

    @model_validator(mode="after")
    def _no_dev_secrets_in_production(self) -> Self:
        if self.environment == "production" and (
            self.jwt_secret == DEV_JWT_SECRET or self.psp_secret == DEV_PSP_SECRET
        ):
            raise ValueError("Set real secrets before running in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
