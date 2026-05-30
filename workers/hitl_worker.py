"""Temporal worker for the HITL task queue.

Run alongside the arq pipeline worker:
  uv run python -m workers.hitl_worker

This worker handles only the HITL lifecycle workflows.  The deterministic
pipeline (S1-S7) remains on arq; Temporal is used exclusively for the
long-running, interruptible HITL waiting phase.

Dev setup:
  Start the Temporal dev server via docker-compose (see infra/docker-compose.dev.yml).
  The worker connects to localhost:7233 by default (override via TEMPORAL_ADDRESS env var).
"""

from __future__ import annotations

import asyncio
import logging

from apps.api.config import settings
from packages.workflows.hitl import HitlWorkflow
from temporalio.client import Client
from temporalio.worker import Worker

from workers.hitl_activities import persist_sla_escalation

logger = logging.getLogger(__name__)


async def _run() -> None:
    logger.info(
        "hitl_worker.connecting temporal_address=%s task_queue=%s",
        settings.temporal_address,
        settings.temporal_task_queue,
    )
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
    )
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[HitlWorkflow],
        activities=[persist_sla_escalation],
    )
    logger.info("hitl_worker.started")
    await worker.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run())
