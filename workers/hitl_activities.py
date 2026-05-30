"""Temporal HITL activities — I/O boundary for the HitlWorkflow.

Activities are the I/O boundary in Temporal workflows.  The HitlWorkflow
(packages/workflows/hitl.py) calls these by string name; the worker registers
the real implementations here.

Allowed here: DB access, logging, Prometheus counters.
Not here: workflow control-flow logic (that lives in packages/workflows/hitl.py).
"""

from __future__ import annotations

import logging

from temporalio import activity

logger = logging.getLogger(__name__)


@activity.defn(name="persist_sla_escalation")
async def persist_sla_escalation(case_id: str, sla_hours: int) -> None:
    """Write an audit_event when the HITL SLA timer expires.

    Does NOT change case.status — the case remains in IN_HUMAN_REVIEW so
    a reviewer can still act.  The audit trail records the missed SLA for
    compliance and alerting dashboards (Grafana / Prometheus).

    In production this would also trigger a notification (email, Slack).
    """
    from apps.api.database import async_session_factory
    from apps.api.models import AuditEvent, Case
    from packages.domain.enums import ActorType

    async with async_session_factory() as session:
        case = await session.get(Case, case_id)
        if case is None:
            logger.error("persist_sla_escalation: case_id=%s not found", case_id)
            return

        audit = AuditEvent(
            case_id=case_id,
            organization_id=case.organization_id,
            actor_type=ActorType.SYSTEM,
            actor_id="hitl_workflow",
            from_status=case.status,
            to_status=case.status,
            trace_id=case.trace_id,
            payload={
                "event": "hitl_sla_expired",
                "sla_hours": sla_hours,
                "message": (
                    f"Case waited {sla_hours}h without human review. "
                    "Case remains in IN_HUMAN_REVIEW — escalation required."
                ),
            },
        )
        session.add(audit)
        await session.commit()

    logger.warning(
        "hitl.sla_expired case_id=%s org=%s sla_hours=%d",
        case_id,
        case.organization_id if case else "unknown",
        sla_hours,
    )

    # Prometheus: track SLA misses for the Grafana dashboard.
    try:
        from packages.observability.metrics import hitl_sla_expirations_total

        hitl_sla_expirations_total.inc()
    except Exception:
        pass
