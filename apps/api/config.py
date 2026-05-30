"""API settings, loaded from the environment (see .env.example)."""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Dev-only default for secret_key. Production refuses to boot with this value
# (see _guard_production_secret) so a real signing key must be supplied via env.
_DEV_SECRET_KEY = "dev-secret-change-in-production-32chars"
_MIN_SECRET_LEN = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://ledger:ledger@localhost:5432/ledgercopilot"
    redis_url: str = "redis://localhost:6379/0"

    active_prompt_alias: str = "dev"
    active_policy_alias: str = "dev"

    # CORS: the web app (Next.js) runs on a different origin in dev and calls the API
    # from the browser (client-side fetch in apps/web/src/lib/api.ts). Without these
    # headers the browser blocks every cross-origin request — login included.
    cors_allow_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    secret_key: str = _DEV_SECRET_KEY

    # Dual LLM / quarantine extraction.
    # When enabled: uses a stricter prompt alias, blocks system_override from DB,
    # uses a cheaper model (Haiku) for the quarantine extraction stage.
    dual_llm_enabled: bool = False
    quarantine_model: str = "claude-haiku-4-5-20251001"

    # Temporal / HITL workflow.
    # Set hitl_temporal_enabled=false to disable without removing the wiring.
    hitl_temporal_enabled: bool = True
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "hitl-queue"
    hitl_sla_hours: int = 24

    # Storage backend.
    # storage_backend="local" writes to storage_local_dir (dev default).
    # Future values: "gcs", "s3" — add backends in packages/storage/factory.py.
    storage_backend: str = "local"
    storage_local_dir: str = "/tmp/ledgercopilot/uploads"

    # Observability.
    # Set PROMETHEUS_MULTIPROC_DIR to a shared writable directory when running
    # multiple processes (API + arq worker) so the /metrics endpoint aggregates all.
    prometheus_multiproc_dir: str = ""

    @model_validator(mode="after")
    def _guard_production_secret(self) -> Settings:
        """Refuse to boot production with an insecure JWT signing key.

        secret_key signs and verifies every JWT (apps/api/auth.py). Starting
        production with the shared dev default — or a too-short key — would let
        anyone forge tokens, so fail fast instead of silently using it. Outside
        production the dev default is allowed for a one-command local setup.
        """
        if self.environment == "production":
            if self.secret_key == _DEV_SECRET_KEY:
                raise ValueError(
                    "SECRET_KEY is still the dev default while environment=production. "
                    "Set a strong, unique SECRET_KEY before deploying."
                )
            if len(self.secret_key) < _MIN_SECRET_LEN:
                raise ValueError(
                    f"SECRET_KEY must be at least {_MIN_SECRET_LEN} characters in "
                    f"production (got {len(self.secret_key)})."
                )
        return self


settings = Settings()
