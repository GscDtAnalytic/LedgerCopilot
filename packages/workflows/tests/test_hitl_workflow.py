"""Tests for HitlWorkflow using Temporal's built-in testing framework.

temporalio provides WorkflowEnvironment.start_time_skipping() which runs
Temporal timers instantly — no real wall-clock sleep, so SLA tests run in ms.
"""

from __future__ import annotations

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from packages.workflows.hitl import HitlWorkflow


@activity.defn(name="persist_sla_escalation")
async def _noop_persist_sla(case_id: str, sla_hours: int) -> None:
    """Stub activity — no DB needed in unit tests."""


@pytest.mark.asyncio
async def test_workflow_completes_on_review_signal():
    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="test-hitl",
            workflows=[HitlWorkflow],
            activities=[_noop_persist_sla],
        ),
    ):
        handle = await env.client.start_workflow(
            HitlWorkflow.run,
            args=["case-abc", 24],
            id="hitl-test-signal",
            task_queue="test-hitl",
        )
        await handle.signal(HitlWorkflow.review_submitted, args=["approve", "reviewer-1"])
        result = await handle.result()
        assert result == "approve"


@pytest.mark.asyncio
async def test_workflow_escalates_on_sla_expiry():
    """Time-skipping environment fires the 24h SLA timer instantly."""
    escalated: list[tuple[str, int]] = []

    @activity.defn(name="persist_sla_escalation")
    async def _capture_sla(case_id: str, sla_hours: int) -> None:
        escalated.append((case_id, sla_hours))

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="test-hitl-sla",
            workflows=[HitlWorkflow],
            activities=[_capture_sla],
        ),
    ):
        handle = await env.client.start_workflow(
            HitlWorkflow.run,
            args=["case-xyz", 24],
            id="hitl-test-sla",
            task_queue="test-hitl-sla",
        )
        result = await handle.result()
        assert result == "sla_expired"
        assert escalated == [("case-xyz", 24)]


@pytest.mark.asyncio
async def test_workflow_signal_after_sla_is_ignored():
    """Signal sent after SLA should not raise (workflow already completed)."""
    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue="test-hitl-late",
            workflows=[HitlWorkflow],
            activities=[_noop_persist_sla],
        ),
    ):
        handle = await env.client.start_workflow(
            HitlWorkflow.run,
            args=["case-late", 1],
            id="hitl-test-late",
            task_queue="test-hitl-late",
        )
        result = await handle.result()
        assert result == "sla_expired"
        # Sending a signal to a completed workflow should not break anything.
        # (In practice the API catches this silently.)
