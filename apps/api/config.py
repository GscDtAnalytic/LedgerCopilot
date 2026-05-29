"""API settings, loaded from the environment (see .env.example)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://ledger:ledger@localhost:5432/ledgercopilot"
    redis_url: str = "redis://localhost:6379/0"

    active_prompt_alias: str = "dev"
    active_policy_alias: str = "dev"


settings = Settings()
