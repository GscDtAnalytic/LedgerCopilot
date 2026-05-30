"""HITL Temporal workflow.

Implements durable orchestration for human review with SLA enforcement:
  1. Workflow starts when the pipeline routes a case to IN_HUMAN_REVIEW.
  2. It sleeps (durably — survives crashes/restarts) until:
     a. A reviewer submits a decision → review_submitted Signal arrives, workflow completes.
     b. SLA timer fires → persist_sla_escalation activity runs, workflow completes as "sla_expired".

Why Temporal here:
- arq handles short deterministic tasks (pipeline S1-S7) well.
- Temporal handles application workflows that must pause for minutes/hours/days — exactly
  the HITL wait. The durable execution model means the SLA timer survives worker restarts.

This module is intentionally pure Python:
  - No direct I/O (DB, network) — those live in workers/hitl_activities.py.
  - Activity calls use string names so the workflow does not import from workers/ or apps/.
  -  pure packages do not import from apps/.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from temporalio import workflow

logger = logging.getLogger(__name__)

# Name used to register the escalation activity in workers/hitl_activities.py.
_ACTIVITY_PERSIST_SLA_ESCALATION = "persist_sla_escalation"


@workflow.defn
class HitlWorkflow:
    """Durable HITL workflow: pause → review signal OR SLA expiry.

    Workflow ID convention: "hitl-{case_id}" — stable per case.
    WorkflowIDReusePolicy.ALLOW_DUPLICATE lets it restart after a completed run
    (e.g., case edited → re-enters IN_HUMAN_REVIEW for a second review round).

    Signals:
      review_submitted(action, reviewer_id) — sent by the review API endpoint.

    Activities (string-referenced, implemented in workers/hitl_activities.py):
      persist_sla_escalation(case_id, sla_hours) — writes audit_event on SLA expiry.
    """

    def __init__(self) -> None:
        self._review_action: str | None = None
        self._reviewer_id: str | None = None

    @workflow.signal
    def review_submitted(self, action: str, reviewer_id: str) -> None:
        """Receive the human decision.

        Called by apps/api/temporal_client.signal_hitl_workflow() after the
        review endpoint commits the DB changes. Signal handler is synchronous
        (sets instance vars) — DB writes are NOT done here (already done in the API).
        """
        self._review_action = action
        self._reviewer_id = reviewer_id
        workflow.logger.info(
            "review_submitted signal received action=%s reviewer=%s",
            action,
            reviewer_id,
        )

    @workflow.run
    async def run(self, case_id: str, sla_hours: int = 24) -> str:
        """Wait for review signal or SLA expiry. Returns the action taken.

        Returns:
          action string (e.g. "approve", "reject", "edit") on normal review.
          "sla_expired" when the SLA timer fires before a reviewer acts.
        """
        sla = timedelta(hours=sla_hours)

        try:
            await workflow.wait_condition(
                lambda: self._review_action is not None,
                timeout=sla,
            )
            result = self._review_action or "unknown"
            workflow.logger.info(
                "hitl_workflow completed case_id=%s action=%s reviewer=%s",
                case_id,
                result,
                self._reviewer_id,
            )
            return result

        except TimeoutError:
            workflow.logger.warning(
                "hitl_sla_expired case_id=%s sla_hours=%d",
                case_id,
                sla_hours,
            )
            await workflow.execute_activity(
                _ACTIVITY_PERSIST_SLA_ESCALATION,
                args=[case_id, sla_hours],
                start_to_close_timeout=timedelta(seconds=30),
            )
            return "sla_expired"
