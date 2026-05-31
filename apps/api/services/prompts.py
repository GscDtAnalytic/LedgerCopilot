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
from dataclasses import dataclass

from packages.agents.extraction import DEFAULT_K, DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.prompt_version import PromptVersion

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PromptConfig:
    """Resolved generation config for the active prompt version.

    Built from a DB PromptVersion row, coalescing NULL columns to the standard
    defaults so a version that only sets system_text behaves exactly as before
   . `model=None` means "use the ai_gateway default model".
    """

    id: str
    system_text: str
    model: str | None
    temperature: float
    top_p: float | None
    max_tokens: int
    k: int


def _row_to_config(row: PromptVersion) -> PromptConfig:
    return PromptConfig(
        id=row.id,
        system_text=row.system_text,
        model=row.model,  # None → ai_gateway default
        temperature=row.temperature if row.temperature is not None else DEFAULT_TEMPERATURE,
        top_p=row.top_p,  # None → provider default
        max_tokens=row.max_tokens if row.max_tokens is not None else DEFAULT_MAX_TOKENS,
        k=row.k if row.k is not None else DEFAULT_K,
    )


async def get_active_prompt_config(alias: str, session: AsyncSession) -> PromptConfig | None:
    """Return the full generation config for the active prompt with this alias, or None.

    None means the caller should fall back to the in-process registry defaults.
    """
    try:
        row = await session.scalar(
            select(PromptVersion)
            .where(PromptVersion.alias == alias, PromptVersion.is_active.is_(True))
            .limit(1)
        )
        if row is not None:
            logger.debug("resolved prompt alias=%r → id=%s from DB", alias, row.id)
            return _row_to_config(row)
        return None
    except Exception:
        logger.exception(
            "failed to resolve prompt alias=%r from DB — using in-process registry", alias
        )
        return None


async def get_active_system_text(alias: str, session: AsyncSession) -> str | None:
    """Return the system_text for the active prompt with this alias, or None.

    Thin wrapper over get_active_prompt_config kept for callers that only need text.
    None means the caller should fall back to the in-process registry.
    """
    config = await get_active_prompt_config(alias, session)
    return config.system_text if config is not None else None
