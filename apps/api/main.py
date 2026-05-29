"""FastAPI application entrypoint.

Run with: ``uv run uvicorn apps.api.main:app --reload``.

At scaffold stage this exposes only a health check. Routers for cases, uploads,
prompts/policies and reviews land phase by phase.
"""

from __future__ import annotations

from fastapi import FastAPI

from apps.api.config import settings
from apps.api.database import async_session_factory
from apps.api.routers import auth, cases, dashboard, documents, intake, monitoring, prompts, reviews
from apps.api.seed import ensure_default_org

app = FastAPI(
    title="LedgerCopilot API",
    version="0.1.0",
    description="AI operations platform for financial document workflows.",
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(cases.router, prefix="/api/v1")
app.include_router(reviews.router, prefix="/api/v1")
app.include_router(prompts.router, prefix="/api/v1")
app.include_router(monitoring.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(intake.router, prefix="/api/v1")


@app.on_event("startup")
async def on_startup() -> None:
    async with async_session_factory() as session:
        await ensure_default_org(session)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "environment": settings.environment}
