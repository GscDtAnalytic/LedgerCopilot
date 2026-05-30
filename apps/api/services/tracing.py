"""Persist gateway traces to the model_runs table (I/O boundary).

The ai_gateway package is I/O-free; it returns a ModelTrace. This module
writes it to the DB. Called best-effort: a failed write is logged and the
failure counter is incremented so monitoring can alert on trace loss.
The pipeline is never blocked by a tracing outage.
"""

from __future__ import annotations

import logging

from packages.ai_gateway.tracer import ModelTrace
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.model_run import ModelRun

logger = logging.getLogger(__name__)

# Monotonic counter of trace persist failures. Readable by health checks or
# Prometheus text exposition. Never reset at runtime.
trace_failure_count: int = 0


async def persist_trace(session: AsyncSession, trace: ModelTrace) -> None:
    """Write a ModelTrace to model_runs. Caller must commit the session."""
    global trace_failure_count
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
            prompt_redacted=trace.prompt_redacted or None,
            completion_redacted=trace.completion_redacted or None,
        )
        session.add(run)
    except Exception:
        trace_failure_count += 1
        logger.error(
            "tracing.persist_failed trace_id=%s failures_total=%d",
            trace.trace_id,
            trace_failure_count,
            exc_info=True,
        )
