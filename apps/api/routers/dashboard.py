"""GET /api/v1/dashboard — executive-level aggregate metrics (Phase 4).

Org-scoped when a valid JWT is present; unscoped for backward compat.
Metrics: case throughput, decision breakdown, confidence avg, cost summary.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import CurrentUser, get_optional_user
from apps.api.database import get_session
from apps.api.models.case import Case
from apps.api.models.extraction import ExtractionResult
from apps.api.models.model_run import ModelRun

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class DecisionBreakdown(BaseModel):
    decision: str | None
    count: int
    pct: float


class StatusBreakdown(BaseModel):
    status: str
    count: int


class DashboardResponse(BaseModel):
    total_cases: int
    cases_this_week: int
    pending_review: int
    avg_confidence: float | None
    total_cost_usd: float
    avg_cost_per_doc_usd: float
    decision_breakdown: list[DecisionBreakdown]
    status_breakdown: list[StatusBreakdown]


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    session: AsyncSession = Depends(get_session),
    user: CurrentUser | None = Depends(get_optional_user),
) -> DashboardResponse:
    org_filter = Case.organization_id == user.org_id if user else True

    total = (
        await session.scalar(
            select(func.count(Case.id)).where(org_filter)  # type: ignore[arg-type]
        )
        or 0
    )

    week_ago = datetime.now(UTC) - timedelta(days=7)
    cases_this_week = (
        await session.scalar(
            select(func.count(Case.id)).where(
                org_filter,  # type: ignore[arg-type]
                Case.created_at >= week_ago,
            )
        )
        or 0
    )

    pending_review = (
        await session.scalar(
            select(func.count(Case.id)).where(
                org_filter,  # type: ignore[arg-type]
                Case.status == "in_human_review",
            )
        )
        or 0
    )

    # Decision breakdown
    decision_rows = await session.execute(
        select(Case.decision, func.count(Case.id).label("cnt"))
        .where(org_filter)  # type: ignore[arg-type]
        .group_by(Case.decision)
        .order_by(func.count(Case.id).desc())
    )
    total_with_decision = total or 1
    decision_breakdown = [
        DecisionBreakdown(
            decision=r.decision,
            count=r.cnt,
            pct=round(r.cnt / total_with_decision * 100, 1),
        )
        for r in decision_rows
    ]

    # Status breakdown
    status_rows = await session.execute(
        select(Case.status, func.count(Case.id).label("cnt"))
        .where(org_filter)  # type: ignore[arg-type]
        .group_by(Case.status)
        .order_by(func.count(Case.id).desc())
    )
    status_breakdown = [StatusBreakdown(status=r.status, count=r.cnt) for r in status_rows]

    # Average confidence from latest extraction per case
    avg_conf = await session.scalar(select(func.avg(ExtractionResult.overall_confidence)))

    # Cost from model runs
    total_cost = await session.scalar(select(func.sum(ModelRun.cost_usd))) or 0.0
    avg_cost = (total_cost / total) if total > 0 else 0.0

    return DashboardResponse(
        total_cases=total,
        cases_this_week=cases_this_week,
        pending_review=pending_review,
        avg_confidence=round(float(avg_conf), 3) if avg_conf is not None else None,
        total_cost_usd=round(float(total_cost), 6),
        avg_cost_per_doc_usd=round(avg_cost, 6),
        decision_breakdown=decision_breakdown,
        status_breakdown=status_breakdown,
    )
