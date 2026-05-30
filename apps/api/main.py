"""FastAPI application entrypoint.

Run with: ``uv run uvicorn apps.api.main:app --reload``.

At scaffold stage this exposes only a health check. Routers for cases, uploads,
prompts/policies and reviews land phase by phase.
"""

from __future__ import annotations

import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.config import settings
from apps.api.database import async_session_factory
from apps.api.redis_pool import close_redis_pool, init_redis_pool
from apps.api.routers import (
    auth,
    cases,
    dashboard,
    documents,
    intake,
    metrics_endpoint,
    monitoring,
    prompts,
    reviews,
)
from apps.api.seed import ensure_default_org

app = FastAPI(
    title="LedgerCopilot API",
    version="0.1.0",
    description="AI operations platform for financial document workflows.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(cases.router, prefix="/api/v1")
app.include_router(reviews.router, prefix="/api/v1")
app.include_router(prompts.router, prefix="/api/v1")
app.include_router(monitoring.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(intake.router, prefix="/api/v1")
app.include_router(metrics_endpoint.router)  # /metrics — no prefix, Prometheus standard path


@app.on_event("startup")
async def on_startup() -> None:
    async with async_session_factory() as session:
        await ensure_default_org(session)
    with contextlib.suppress(Exception):
        await init_redis_pool()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await close_redis_pool()


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "environment": settings.environment}
