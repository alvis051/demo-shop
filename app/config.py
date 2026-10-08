"""Settings for each environment, read from env vars."""

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Env = Literal["test", "daily", "pre", "prod"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Env = Field("test", alias="DEMO_SHOP_ENV")
    database_url: str = Field("postgresql+psycopg://shop:shop@127.0.0.1:5432/shop", alias="DATABASE_URL")
    session_secret: str = Field("", alias="SESSION_SECRET")
    admin_email: str = Field("admin@example.com", alias="ADMIN_EMAIL")
    admin_password: str = Field("admin-pass", alias="ADMIN_PASSWORD")
    version: str = Field("dev", alias="APP_VERSION")

    # Fault knobs. Off by default, and always off in prod.
    latency_ms: int = Field(0, ge=0, alias="DEMO_SHOP_LATENCY_MS")
    flaky_rate: float = Field(0.0, ge=0.0, le=1.0, alias="DEMO_SHOP_FLAKY_RATE")
    flaky_seed: int | None = Field(None, alias="DEMO_SHOP_FLAKY_SEED")
    bug: str = Field("", alias="DEMO_SHOP_BUG")

    @model_validator(mode="after")
    def _apply_env_rules(self) -> "Settings":
        if self.database_url.startswith("postgres://"):
            self.database_url = "postgresql://" + self.database_url[len("postgres://") :]
        if self.database_url.startswith("postgresql://"):
            self.database_url = self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        if not self.session_secret:
            if self.env != "test":
                raise ValueError(f"SESSION_SECRET is required when DEMO_SHOP_ENV={self.env}")
            self.session_secret = secrets.token_urlsafe(32)
        if self.env == "prod":
            self.latency_ms, self.flaky_rate, self.bug = 0, 0.0, ""
        return self

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @property
    def faults_allowed(self) -> bool:
        return not self.is_prod

    @property
    def seed_demo_users(self) -> bool:
        return not self.is_prod

    @property
    def secure_cookies(self) -> bool:
        return self.env != "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()
