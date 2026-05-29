"""Document processing pipeline worker.

Run with: ``uv run arq workers.pipeline.WorkerSettings``.

The macro flow: document in → create case + hash/source/timestamps
→ OCR/parse → classify + extract (self-consistency k=3 on critical fields) →
validate → policy → reconcile → decide → persist an audit_event on EVERY
transition → feed metrics/cost/latency.

At scaffold stage this only wires the arq worker. Job functions land in Phase 1.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from apps.api.config import settings


async def process_document(ctx: dict[str, Any], case_id: str) -> None:
    """Placeholder pipeline job. Implemented in Phase 1.

    Each stage transition must persist an ``audit_event`` in the same DB
    transaction as the state change.
    """
    raise NotImplementedError("pipeline job lands in Phase 1")


class WorkerSettings:
    """arq worker configuration."""

    functions: ClassVar[list[Callable[..., Any]]] = [process_document]
    redis_settings = settings.redis_url
