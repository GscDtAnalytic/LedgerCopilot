"""Prompt registry API — CRUD for versioned prompts.

Endpoints:
  GET  /api/v1/prompts           — list all active prompt versions  (any authenticated user)
  POST /api/v1/prompts           — create a new version             (admin only)
  GET  /api/v1/prompts/{id}      — get one version                  (any authenticated user)
  POST /api/v1/prompts/{id}/promote — set alias (dev|staging|production)
                                      staging→production requires passing scorecard
                                     

The staging→production gate enforces  at the API level. eval.gate
enforces the same rules as a CLI gate for CI usage. When promoted, the new system_text
is picked up by the pipeline worker on the next invocation via apps/api/services/prompts
.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import CurrentUser, get_current_user, require_roles
from apps.api.database import get_session
from apps.api.models.prompt_version import PromptVersion

router = APIRouter(prefix="/prompts", tags=["prompts"])

_VALID_ALIASES = {"dev", "staging", "production"}
_GATING_ALIASES = {"production"}  # aliases that require a passing scorecard


class PromptVersionOut(BaseModel):
    id: str
    alias: str | None
    name: str
    description: str
    is_active: bool
    scorecard: dict | None
    created_at: str


class CreatePromptRequest(BaseModel):
    name: str
    description: str = ""
    system_text: str


class PromoteRequest(BaseModel):
    alias: str


def _row_to_out(pv: PromptVersion) -> PromptVersionOut:
    sc: dict | None = None
    if pv.scorecard:
        try:
            sc = json.loads(pv.scorecard)
        except json.JSONDecodeError:
            sc = None
    return PromptVersionOut(
        id=pv.id,
        alias=pv.alias,
        name=pv.name,
        description=pv.description,
        is_active=pv.is_active,
        scorecard=sc,
        created_at=pv.created_at.isoformat(),
    )


@router.get("", response_model=list[PromptVersionOut])
async def list_prompts(
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> list[PromptVersionOut]:
    rows = await session.execute(
        select(PromptVersion).where(PromptVersion.is_active).order_by(PromptVersion.created_at.desc())
    )
    return [_row_to_out(r) for (r,) in rows]


@router.get("/{prompt_id}", response_model=PromptVersionOut)
async def get_prompt_version(
    prompt_id: str,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> PromptVersionOut:
    pv = await session.get(PromptVersion, prompt_id)
    if pv is None:
        raise HTTPException(status_code=404, detail="Prompt version not found.")
    return _row_to_out(pv)


@router.post("", response_model=PromptVersionOut, status_code=201)
async def create_prompt(
    body: CreatePromptRequest,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = Depends(require_roles("admin")),
) -> PromptVersionOut:
    pv = PromptVersion(name=body.name, description=body.description, system_text=body.system_text)
    session.add(pv)
    await session.commit()
    await session.refresh(pv)
    return _row_to_out(pv)


@router.post("/{prompt_id}/promote", response_model=PromptVersionOut)
async def promote_prompt(
    prompt_id: str,
    body: PromoteRequest,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = Depends(require_roles("admin")),
) -> PromptVersionOut:
    """Assign an alias to a prompt version (admin only).

    Promoting to 'production' requires a passing scorecard.
    Once promoted, the pipeline worker picks up the new system_text on the next
    invocation via apps/api/services/prompts.get_active_system_text.
    """
    if body.alias not in _VALID_ALIASES:
        raise HTTPException(status_code=422, detail=f"alias must be one of {_VALID_ALIASES}")

    pv = await session.get(PromptVersion, prompt_id)
    if pv is None:
        raise HTTPException(status_code=404, detail="Prompt version not found.")

    if body.alias in _GATING_ALIASES:
        if not pv.scorecard:
            raise HTTPException(
                status_code=409,
                detail="Cannot promote to production without a scorecard. Run eval first.",
            )
        sc = json.loads(pv.scorecard)
        _check_gating_rules(sc, prompt_id)

    # Clear the alias from any other version that holds it.
    await session.execute(
        update(PromptVersion)
        .where(PromptVersion.alias == body.alias, PromptVersion.id != prompt_id)
        .values(alias=None)
    )
    pv.alias = body.alias
    await session.commit()
    await session.refresh(pv)
    return _row_to_out(pv)


def _check_gating_rules(scorecard: dict, version_id: str) -> None:
    """Raise HTTPException if any promotion rule from  is violated."""
    from eval.gate import (
        MAX_FALSE_AUTO_APPROVE_DELTA,
        MIN_SUPPLIER_NAME_ACCURACY,
    )

    far = scorecard.get("false_auto_approve_rate", 0.0)
    sna = scorecard.get("supplier_name_accuracy", 1.0)
    baseline_far = scorecard.get("baseline_false_auto_approve_rate", 0.0)

    violations = []
    allowed_far = baseline_far + MAX_FALSE_AUTO_APPROVE_DELTA
    if far > allowed_far:
        delta = MAX_FALSE_AUTO_APPROVE_DELTA
        violations.append(
            f"false_auto_approve_rate {far:.3f} > baseline {baseline_far:.3f} + {delta:.2f}"
        )
    if sna < MIN_SUPPLIER_NAME_ACCURACY:
        violations.append(f"supplier_name_accuracy {sna:.3f} < {MIN_SUPPLIER_NAME_ACCURACY}")

    if violations:
        raise HTTPException(
            status_code=409,
            detail=f"Promotion BLOCKED for {version_id}: " + "; ".join(violations),
        )
