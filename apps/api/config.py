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

    secret_key: str = "dev-secret-change-in-production-32chars"

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


settings = Settings()
