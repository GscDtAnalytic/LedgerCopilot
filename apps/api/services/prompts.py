"""Resolve the active prompt version from the DB for the pipeline.

The pipeline uses this at the I/O boundary to fetch the prompt aliased as
"production" (or "dev" in dev environments) before calling run_extraction.
Falls back to None — in which case the in-process registry in
packages/ai_gateway/registry.py is used — when the DB is unreachable or
has no row for the alias.

This is the bridge that makes POST /prompts/{id}/promote actually affect
what the worker runs. Without this call the registry stays in-process forever.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.prompt_version import PromptVersion

logger = logging.getLogger(__name__)


async def get_active_system_text(alias: str, session: AsyncSession) -> str | None:
    """Return the system_text for the active prompt with this alias, or None.

    None means the caller should fall back to the in-process registry.
    """
    try:
        row = await session.scalar(
            select(PromptVersion)
            .where(PromptVersion.alias == alias, PromptVersion.is_active.is_(True))
            .limit(1)
        )
        if row is not None:
            logger.debug("resolved prompt alias=%r → id=%s from DB", alias, row.id)
            return row.system_text
        return None
    except Exception:
        logger.exception(
            "failed to resolve prompt alias=%r from DB — using in-process registry", alias
        )
        return None
