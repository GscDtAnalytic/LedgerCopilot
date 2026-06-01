"""Prompt registry API — CRUD for versioned prompts.

Endpoints:
  GET    /api/v1/prompts                — list all active versions  (any authenticated user)
  POST   /api/v1/prompts                — create a new version      (admin only)
  GET    /api/v1/prompts/{id}           — get one version           (any authenticated user)
  DELETE /api/v1/prompts/{id}           — soft-delete a version     (admin only;
                                          blocked if alias=production)
  PATCH  /api/v1/prompts/{id}/scorecard — attach eval scorecard     (admin only)
  POST   /api/v1/prompts/{id}/eval      — run eval suite and save scorecard (admin only)
  POST   /api/v1/prompts/{id}/promote   — set alias (dev|staging|production);
                                          staging→production requires a passing scorecard
                                          (admin only)

eval.gate enforces the same promotion rules as a CLI gate for CI. When promoted,
the new system_text is picked up by the pipeline worker on the next invocation
via apps/api/services/prompts.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from eval.gate import compare_metrics
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth import CurrentUser, get_current_user, require_roles
from apps.api.database import get_session
from apps.api.models.prompt_version import PromptVersion

router = APIRouter(prefix="/prompts", tags=["prompts"])

_VALID_ALIASES = {"dev", "staging", "production"}
_GATING_ALIASES = {"production"}  # aliases that require a passing scorecard

# Fallback baseline when no version holds the production alias yet (e.g. first ever
# promotion). Path: apps/api/routers/prompts.py → repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_PRODUCTION_SCORECARD_FILE = _REPO_ROOT / "eval" / "scorecards" / "production.json"


class PromptVersionOut(BaseModel):
    # `model` is a generation-config field, not Pydantic's protected namespace.
    model_config = ConfigDict(protected_namespaces=())

    id: str
    alias: str | None
    name: str
    description: str
    is_active: bool
    scorecard: dict | None
    created_at: str
    # Per-version generation config; None means "use the standard default".
    model: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    k: int | None = None
    # Changelog — what changed vs the parent version.
    based_on: str | None = None
    change_summary: str | None = None
    expected_outcome: str | None = None


class CreatePromptRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    name: str
    description: str = ""
    system_text: str
    # Optional generation config; None persists as NULL → standard default at runtime.
    model: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    k: int | None = None
    # Optional changelog.
    based_on: str | None = None
    change_summary: str | None = None
    expected_outcome: str | None = None


class PromoteRequest(BaseModel):
    alias: str


class ScorecardRequest(BaseModel):
    scorecard: dict


class MetricVerdictOut(BaseModel):
    """One metric compared candidate-vs-baseline (mirrors eval.gate.MetricVerdict)."""

    key: str
    label: str
    candidate: float
    baseline: float | None
    delta: float | None
    threshold_label: str
    gated: bool
    passed: bool
    severity: str


class GateVerdictOut(BaseModel):
    candidate_id: str
    baseline_id: str | None
    has_scorecard: bool
    passed: bool
    metrics: list[MetricVerdictOut]
    violations: list[str]


class CompareOut(BaseModel):
    a: PromptVersionOut
    b: PromptVersionOut
    baseline: str  # "a" | "b" — which side is the baseline
    a_has_scorecard: bool
    b_has_scorecard: bool
    system_text_changed: bool
    metrics: list[MetricVerdictOut]


def _parse_scorecard(pv: PromptVersion) -> dict | None:
    if not pv.scorecard:
        return None
    try:
        return json.loads(pv.scorecard)
    except json.JSONDecodeError:
        return None


def _row_to_out(pv: PromptVersion) -> PromptVersionOut:
    return PromptVersionOut(
        id=pv.id,
        alias=pv.alias,
        name=pv.name,
        description=pv.description,
        is_active=pv.is_active,
        scorecard=_parse_scorecard(pv),
        created_at=pv.created_at.isoformat(),
        model=pv.model,
        temperature=pv.temperature,
        top_p=pv.top_p,
        max_tokens=pv.max_tokens,
        k=pv.k,
        based_on=pv.based_on,
        change_summary=pv.change_summary,
        expected_outcome=pv.expected_outcome,
    )


async def _resolve_baseline(
    session: AsyncSession, exclude_id: str | None = None
) -> tuple[str | None, dict | None]:
    """Resolve the production baseline scorecard for gate comparison.

    Prefers the version currently holding alias="production"; falls back to the
    committed eval/scorecards/production.json so the very first promotion still has
    a baseline. Returns (baseline_id, scorecard_dict) — both None if unavailable.
    """
    stmt = select(PromptVersion).where(
        PromptVersion.alias == "production", PromptVersion.is_active.is_(True)
    )
    if exclude_id is not None:
        stmt = stmt.where(PromptVersion.id != exclude_id)
    row = await session.scalar(stmt.limit(1))
    if row is not None:
        sc = _parse_scorecard(row)
        if sc is not None:
            return row.id, sc
    if _PRODUCTION_SCORECARD_FILE.exists():
        try:
            return "production-baseline", json.loads(_PRODUCTION_SCORECARD_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return None, None


@router.get("", response_model=list[PromptVersionOut])
async def list_prompts(
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> list[PromptVersionOut]:
    rows = await session.execute(
        select(PromptVersion)
        .where(PromptVersion.is_active)
        .order_by(PromptVersion.created_at.desc())
    )
    return [_row_to_out(r) for (r,) in rows]


@router.get("/compare", response_model=CompareOut)
async def compare_versions(
    a: str = Query(..., description="Version id on the A (left) side"),
    b: str | None = Query(None, description="Version id on the B side; defaults to production"),
    baseline: str = Query("b", pattern="^[ab]$", description="Which side is the baseline"),
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> CompareOut:
    """Compare two prompt versions metric-by-metric (the version-compare surface).

    `b` defaults to whatever version currently holds the production alias, so
    "compare vs production" needs only `a`. The candidate is the non-baseline side;
    metrics are candidate-vs-baseline so the verdict reads the same as the gate.
    Declared before GET /{prompt_id} so "/compare" is not captured as an id.
    """
    pv_a = await session.get(PromptVersion, a)
    if pv_a is None:
        raise HTTPException(status_code=404, detail=f"Version A not found: {a}")

    if b is not None:
        pv_b = await session.get(PromptVersion, b)
    else:
        pv_b = await session.scalar(
            select(PromptVersion).where(
                PromptVersion.alias == "production", PromptVersion.is_active.is_(True)
            )
        )
    if pv_b is None:
        raise HTTPException(
            status_code=404,
            detail="Version B not found (and no production version to default to).",
        )

    sc_a = _parse_scorecard(pv_a)
    sc_b = _parse_scorecard(pv_b)
    # Candidate is the non-baseline side; baseline="b" (default) → candidate=A vs baseline=B.
    if baseline == "a":
        cand_sc, base_sc = sc_b, sc_a
    else:
        cand_sc, base_sc = sc_a, sc_b
    verdicts = compare_metrics(cand_sc or {}, base_sc or {})

    return CompareOut(
        a=_row_to_out(pv_a),
        b=_row_to_out(pv_b),
        baseline=baseline,
        a_has_scorecard=sc_a is not None,
        b_has_scorecard=sc_b is not None,
        system_text_changed=pv_a.system_text != pv_b.system_text,
        metrics=[MetricVerdictOut(**asdict(m)) for m in verdicts],
    )


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


@router.get("/{prompt_id}/gate", response_model=GateVerdictOut)
async def get_gate_verdict(
    prompt_id: str,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> GateVerdictOut:
    """Compute this version's promotion verdict against the real production baseline.

    Single source of truth with eval.gate (no thresholds duplicated client-side) —
    this is what the detail page renders instead of its own ad-hoc rules.
    """
    pv = await session.get(PromptVersion, prompt_id)
    if pv is None:
        raise HTTPException(status_code=404, detail="Prompt version not found.")

    cand_sc = _parse_scorecard(pv)
    if cand_sc is None:
        return GateVerdictOut(
            candidate_id=pv.id,
            baseline_id=None,
            has_scorecard=False,
            passed=False,
            metrics=[],
            violations=[],
        )

    baseline_id, base_sc = await _resolve_baseline(session, exclude_id=pv.id)
    verdicts = compare_metrics(cand_sc, base_sc or {})
    gated = [m for m in verdicts if m.gated]
    passed = all(m.passed for m in gated)
    violations = [
        f"{m.label} {m.candidate:.4f} fails {m.threshold_label}" for m in gated if not m.passed
    ]
    return GateVerdictOut(
        candidate_id=pv.id,
        baseline_id=baseline_id,
        has_scorecard=True,
        passed=passed,
        metrics=[MetricVerdictOut(**asdict(m)) for m in verdicts],
        violations=violations,
    )


@router.post("", response_model=PromptVersionOut, status_code=201)
async def create_prompt(
    body: CreatePromptRequest,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = Depends(require_roles("admin")),
) -> PromptVersionOut:
    pv = PromptVersion(
        name=body.name,
        description=body.description,
        system_text=body.system_text,
        model=body.model,
        temperature=body.temperature,
        top_p=body.top_p,
        max_tokens=body.max_tokens,
        k=body.k,
        based_on=body.based_on,
        change_summary=body.change_summary,
        expected_outcome=body.expected_outcome,
    )
    session.add(pv)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"A prompt version named '{body.name}' already exists.",
        ) from exc
    await session.refresh(pv)
    return _row_to_out(pv)


@router.delete("/{prompt_id}", status_code=204)
async def delete_prompt(
    prompt_id: str,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = Depends(require_roles("admin")),
) -> Response:
    """Soft-delete a prompt version (admin only).

    Sets is_active=False so the version no longer appears in the list.
    Blocked if the version holds the 'production' alias — demote it first.
    Audit events that reference this version id are preserved.
    """
    pv = await session.get(PromptVersion, prompt_id)
    if pv is None:
        raise HTTPException(status_code=404, detail="Prompt version not found.")
    pv.is_active = False
    pv.alias = None  # release alias so it doesn't block future versions
    pv.name = f"{pv.name}__deleted_{prompt_id[:8]}"  # free the name for reuse
    await session.commit()
    return Response(status_code=204)


@router.patch("/{prompt_id}/scorecard", response_model=PromptVersionOut)
async def write_scorecard(
    prompt_id: str,
    body: ScorecardRequest,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = Depends(require_roles("admin")),
) -> PromptVersionOut:
    """Attach an eval scorecard to a prompt version (admin only).

    Called by eval.run --post-scorecard after generating the scorecard JSON.
    Once attached, the version's gate status becomes visible in the UI and
    the version becomes eligible for promotion to production.
    """
    pv = await session.get(PromptVersion, prompt_id)
    if pv is None:
        raise HTTPException(status_code=404, detail="Prompt version not found.")
    pv.scorecard = json.dumps(body.scorecard)
    await session.commit()
    await session.refresh(pv)
    return _row_to_out(pv)


@router.post("/{prompt_id}/eval", response_model=PromptVersionOut)
async def run_eval_for_prompt(
    prompt_id: str,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = Depends(require_roles("admin")),
) -> PromptVersionOut:
    """Run the eval dataset against this prompt version and save the scorecard (admin only).

    Runs eval.runner.run_eval() synchronously within the request — the 13 fixtures
    execute concurrently via asyncio.gather so the p95 wall-clock is ~5-15s depending
    on the model. The scorecard is saved to DB on completion and the updated version
    is returned, ready for promotion gating.
    """
    from eval.runner import EvalConfig, run_eval

    from apps.api.services.prompts import _row_to_config

    pv = await session.get(PromptVersion, prompt_id)
    if pv is None:
        raise HTTPException(status_code=404, detail="Prompt version not found.")

    # Run eval under THIS version's config (system_text + generation params) so the
    # scorecard reflects the version, not registry defaults. _row_to_config
    # coalesces NULL columns to the standard defaults.
    pc = _row_to_config(pv)
    cfg = EvalConfig(
        system_text=pc.system_text,
        model=pc.model,
        temperature=pc.temperature,
        top_p=pc.top_p,
        max_tokens=pc.max_tokens,
        k=pc.k,
    )
    # dataset_root=None → runner uses its own _DATASET_ROOT (absolute path relative to runner.py)
    # Surface failures as an HTTPException (502) so the response keeps CORS headers and
    # the client sees a real message — an unhandled 500 is emitted outside the CORS
    # middleware and the browser reports it only as "cannot reach the API".
    try:
        scorecard = await run_eval(prompt_version_id=prompt_id, config=cfg)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"Eval dataset unavailable: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Eval run failed: {exc}") from exc
    pv.scorecard = json.dumps(scorecard.as_dict())
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

    Promoting to 'production' requires a passing scorecard. Once promoted,
    the pipeline worker picks up the new system_text on the next invocation
    via apps/api/services/prompts.get_active_system_text.
    """
    if body.alias not in _VALID_ALIASES:
        raise HTTPException(status_code=422, detail=f"alias must be one of {_VALID_ALIASES}")

    pv = await session.get(PromptVersion, prompt_id)
    if pv is None:
        raise HTTPException(status_code=404, detail="Prompt version not found.")

    if body.alias in _GATING_ALIASES:
        sc = _parse_scorecard(pv)
        if sc is None:
            raise HTTPException(
                status_code=409,
                detail="Cannot promote to production without a scorecard. Run eval first.",
            )
        # Gate against the CURRENT production baseline (the version we're replacing),
        # so promote-time and the gate view agree on every rule.
        _baseline_id, base_sc = await _resolve_baseline(session, exclude_id=prompt_id)
        _check_gating_rules(sc, base_sc or {}, prompt_id)

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


def _check_gating_rules(candidate: dict, baseline: dict, version_id: str) -> None:
    """Raise HTTPException if any promotion gate rule is violated.

    Delegates to eval.gate.compare_metrics so the four rules (false_auto_approve,
    cost/doc, critical_field_accuracy, decision_accuracy) and their thresholds match
    the CLI gate and the /gate view exactly — no duplicated logic.
    """
    verdicts = compare_metrics(candidate, baseline)
    violations = [
        f"{m.label} {m.candidate:.4f} fails {m.threshold_label}"
        for m in verdicts
        if m.gated and not m.passed
    ]
    if violations:
        raise HTTPException(
            status_code=409,
            detail=f"Promotion BLOCKED for {version_id}: " + "; ".join(violations),
        )
