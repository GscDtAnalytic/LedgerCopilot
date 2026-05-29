"""Persist gateway traces to the model_runs table (I/O boundary).

The ai_gateway package is I/O-free; it returns a ModelTrace. This module
writes it to the DB. Called best-effort: a failed write is logged and swallowed
so the pipeline is never blocked by a tracing outage.
"""

from __future__ import annotations

import logging

from packages.ai_gateway.tracer import ModelTrace
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.model_run import ModelRun

logger = logging.getLogger(__name__)


async def persist_trace(session: AsyncSession, trace: ModelTrace) -> None:
    """Write a ModelTrace to model_runs. Caller must commit the session."""
    try:
        run = ModelRun(
            case_id=trace.case_id if trace.case_id else None,
            trace_id=trace.trace_id,
            prompt_version_id=trace.prompt_version_id,
            model=trace.model,
            stage=trace.stage,
            input_tokens=trace.input_tokens,
            output_tokens=trace.output_tokens,
            latency_ms=trace.latency_ms,
            cost_usd=trace.cost_usd,
        )
        session.add(run)
    except Exception:
        logger.exception("failed to persist model trace trace_id=%s", trace.trace_id)
