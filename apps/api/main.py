"""FastAPI application entrypoint.

Run with: ``uv run uvicorn apps.api.main:app --reload``.

At scaffold stage this exposes only a health check. Routers for cases, uploads,
prompts/policies and reviews land phase by phase.
"""

from __future__ import annotations

from fastapi import FastAPI

from apps.api.config import settings

app = FastAPI(
    title="LedgerCopilot API",
    version="0.1.0",
    description="AI operations platform for financial document workflows.",
)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "environment": settings.environment}
