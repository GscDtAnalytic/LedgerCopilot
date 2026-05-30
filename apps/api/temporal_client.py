"""Temporal client singleton for the FastAPI + arq processes.

Follows the same lazy-init pattern as apps/api/redis_pool.py: module-level
singleton initialised on first use, shared across all coroutines in the process.

Callers:
  workers/pipeline.py  — start_hitl_workflow() after IN_HUMAN_REVIEW decision
  apps/api/routers/reviews.py — signal_hitl_workflow() after review commit

Both callers wrap the calls in try/except so the critical DB path is never
blocked by Temporal being unavailable (degradation: HITL still works, but SLA
enforcement is disabled until Temporal recovers).
"""

from __future__ import annotations

import logging

from apps.api.config import settings

logger = logging.getLogger(__name__)

_client = None


async def _get_client():
    """Lazy-init the Temporal client (cached after first successful connect)."""
    global _client
    if _client is None:
        from temporalio.client import Client

        _client = await Client.connect(
            settings.temporal_address,
            namespace=settings.temporal_namespace,
        )
        logger.info(
            "temporal_client.connected address=%s namespace=%s",
            settings.temporal_address,
            settings.temporal_namespace,
        )
    return _client


async def start_hitl_workflow(case_id: str, sla_hours: int | None = None) -> str | None:
    """Start HitlWorkflow for a case in IN_HUMAN_REVIEW.

    WorkflowIDReusePolicy.ALLOW_DUPLICATE lets the workflow restart if the case
    is edited and re-enters IN_HUMAN_REVIEW for a second review round.

    Returns the workflow run_id on success, None on error (caller should log).
    """
    if not settings.hitl_temporal_enabled:
        return None

    effective_sla = sla_hours if sla_hours is not None else settings.hitl_sla_hours

    from packages.workflows.hitl import HitlWorkflow
    from temporalio.common import WorkflowIDConflictPolicy

    client = await _get_client()
    handle = await client.start_workflow(
        HitlWorkflow.run,
        args=[case_id, effective_sla],
        id=f"hitl-{case_id}",
        task_queue=settings.temporal_task_queue,
        id_conflict_policy=WorkflowIDConflictPolicy.TERMINATE_EXISTING,
    )
    logger.info(
        "hitl_workflow.started case_id=%s run_id=%s sla_hours=%d",
        case_id,
        handle.result_run_id,
        effective_sla,
    )
    return handle.result_run_id


async def signal_hitl_workflow(
    case_id: str,
    action: str,
    reviewer_id: str,
) -> None:
    """Send review_submitted signal to the running HitlWorkflow.

    Called AFTER the review endpoint commits the DB changes — Temporal is
    additive; correctness is guaranteed by the DB write.

    Silently no-ops if the workflow does not exist (e.g., it already completed
    or Temporal was unavailable when the pipeline ran).
    """
    if not settings.hitl_temporal_enabled:
        return

    from packages.workflows.hitl import HitlWorkflow

    client = await _get_client()
    try:
        handle = client.get_workflow_handle_for(HitlWorkflow, workflow_id=f"hitl-{case_id}")
        await handle.signal(HitlWorkflow.review_submitted, args=[action, reviewer_id])
        logger.info(
            "hitl_workflow.signalled case_id=%s action=%s reviewer=%s",
            case_id,
            action,
            reviewer_id,
        )
    except Exception as exc:
        # Workflow may have already completed or never started — not an error.
        logger.debug(
            "hitl_workflow.signal_skipped case_id=%s reason=%s",
            case_id,
            exc,
        )
