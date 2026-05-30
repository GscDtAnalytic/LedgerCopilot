"""GET /api/v1/monitoring — cost, latency and throughput metrics (Phase 3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import CurrentUser, get_current_user
from apps.api.database import get_session
from apps.api.models.case import Case
from apps.api.models.model_run import ModelRun

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


class StageMetric(BaseModel):
    stage: str
    model: str
    total_runs: int
    avg_latency_ms: float
    p95_latency_ms: float
    total_cost_usd: float
    avg_input_tokens: float
    avg_output_tokens: float


class CaseThroughput(BaseModel):
    status: str
    count: int


class MonitoringResponse(BaseModel):
    stage_metrics: list[StageMetric]
    case_throughput: list[CaseThroughput]
    total_cost_usd: float
    total_model_runs: int


@router.get("", response_model=MonitoringResponse)
async def get_monitoring(
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> MonitoringResponse:
    """Aggregate cost, latency and throughput from model_runs and cases.

    Auth required (LLMOps metrics are operational data, not public). Aggregates are
    org-wide for now — per-org scoping needs an org_id link on model_runs (future).
    """
    # Stage-level aggregates
    stage_rows = await session.execute(
        select(
            ModelRun.stage,
            ModelRun.model,
            func.count(ModelRun.id).label("total_runs"),
            func.avg(ModelRun.latency_ms).label("avg_latency_ms"),
            func.percentile_cont(0.95).within_group(ModelRun.latency_ms).label("p95_latency_ms"),
            func.sum(ModelRun.cost_usd).label("total_cost_usd"),
            func.avg(ModelRun.input_tokens).label("avg_input_tokens"),
            func.avg(ModelRun.output_tokens).label("avg_output_tokens"),
        )
        .group_by(ModelRun.stage, ModelRun.model)
        .order_by(ModelRun.stage)
    )

    stage_metrics = [
        StageMetric(
            stage=r.stage,
            model=r.model,
            total_runs=r.total_runs,
            avg_latency_ms=round(r.avg_latency_ms or 0, 1),
            p95_latency_ms=round(r.p95_latency_ms or 0, 1),
            total_cost_usd=round(r.total_cost_usd or 0, 6),
            avg_input_tokens=round(r.avg_input_tokens or 0, 1),
            avg_output_tokens=round(r.avg_output_tokens or 0, 1),
        )
        for r in stage_rows
    ]

    # Case throughput by status
    throughput_rows = await session.execute(
        select(Case.status, func.count(Case.id).label("case_count"))
        .group_by(Case.status)
        .order_by(func.count(Case.id).desc())
    )
    case_throughput = [
        CaseThroughput(status=r.status, count=int(r.case_count)) for r in throughput_rows
    ]

    total_cost = sum(m.total_cost_usd for m in stage_metrics)
    total_runs = sum(m.total_runs for m in stage_metrics)

    return MonitoringResponse(
        stage_metrics=stage_metrics,
        case_throughput=case_throughput,
        total_cost_usd=round(total_cost, 6),
        total_model_runs=total_runs,
    )
