"""Configuration.

Every external dependency is optional. Atlas must run, and underwrite deals
correctly, with no database URL, no API keys and no AI provider configured.
Secrets are read from the environment and never leave the backend.
"""

from __future__ import annotations

import functools
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: str = "development"
    log_level: str = "INFO"

    # --- Database -----------------------------------------------------------
    # PostgreSQL (Supabase) in production. Falls back to a local SQLite file so
    # the app is runnable with zero setup.
    atlas_database_url: str = "sqlite:///./atlas.db"
    database_echo: bool = False

    # --- Auth ---------------------------------------------------------------
    # Supabase signs its JWTs with this secret. Without it, the API runs in
    # development auth mode, which is refused outright in production.
    supabase_jwt_secret: Optional[str] = None
    supabase_url: Optional[str] = None
    supabase_jwt_audience: str = "authenticated"
    # Development-only identity used when no JWT secret is configured.
    dev_user_id: str = "00000000-0000-0000-0000-000000000001"
    dev_user_email: str = "dev@atlas.local"

    # --- Data providers -----------------------------------------------------
    rentcast_api_key: Optional[str] = None
    rentcast_base_url: str = "https://api.rentcast.io/v1"
    attom_api_key: Optional[str] = None

    # --- AI -----------------------------------------------------------------
    # "null" is a real, supported provider: it produces deterministic,
    # rule-based output so the AI surfaces work with no key configured.
    atlas_ai_provider: str = "null"
    atlas_ai_model: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    ai_request_timeout_seconds: int = 60

    # --- CORS ---------------------------------------------------------------
    cors_origins: str = "http://localhost:3000"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod")

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def auth_configured(self) -> bool:
        return bool(self.supabase_jwt_secret)

    @property
    def uses_sqlite(self) -> bool:
        return self.atlas_database_url.startswith("sqlite")


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()
