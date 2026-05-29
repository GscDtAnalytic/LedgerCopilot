"""Document processing pipeline worker.

Run with: ``uv run arq workers.pipeline.WorkerSettings``

Macro flow:
  1. RECEIVED → CLASSIFIED  (classify document type from filename/content)
  2. CLASSIFIED → EXTRACTED  (ai_gateway + Self-Consistency k=3, stub fallback)
  3. EXTRACTED → VALIDATED   (deterministic rules, no LLM)
  4. VALIDATED → RECONCILED  (Phase 2: simple totals check)
  5. RECONCILED → POLICY_EVALUATED  (Phase 2: versioned policy engine)
  6. POLICY_EVALUATED → DECIDED     (Tree-of-Thoughts decision logic)
  7. DECIDED → AUTO_APPROVED | IN_HUMAN_REVIEW | REJECTED

INVARIANT: Every state transition calls `_transition()` which writes the
AuditEvent in the SAME transaction as the Case.status update. There is no
mutation without an event.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

from apps.api.config import settings
from apps.api.database import async_session_factory
from apps.api.models import AuditEvent, Case, Document, ExtractionResult, ValidationResult
from apps.api.services.tracing import persist_trace
from packages.agents.extraction import run_extraction
from packages.domain.entities import DecisionBranches, ExtractionOutput
from packages.domain.enums import ActorType, Decision, DocumentType
from packages.domain.state_machine import CaseStatus, assert_transition
from packages.policy.engine import run_policy
from packages.validation.engine import run_validations
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_POLICY_VERSION_ID = "dev-1.0"


# ---------------------------------------------------------------------------
# Atomic transition helper
# ---------------------------------------------------------------------------


async def _transition(
    session: AsyncSession,
    case: Case,
    target: CaseStatus,
    actor_type: ActorType,
    payload: dict[str, Any],
    *,
    actor_id: str = "pipeline",
    prompt_version_id: str | None = None,
    model_name: str | None = None,
) -> None:
    """Validate + apply a state transition, writing audit_event atomically."""
    assert_transition(CaseStatus(case.status), target)

    audit = AuditEvent(
        case_id=case.id,
        organization_id=case.organization_id,
        actor_type=actor_type,
        actor_id=actor_id,
        from_status=case.status,
        to_status=target,
        prompt_version_id=prompt_version_id,
        policy_version_id=_POLICY_VERSION_ID if prompt_version_id else None,
        model_name=model_name,
        trace_id=case.trace_id,
        payload=payload,
    )
    case.status = target
    session.add(audit)
    # Caller commits; we only flush here to keep the batch together.
    await session.flush()


# ---------------------------------------------------------------------------
# Stage implementations
# ---------------------------------------------------------------------------


def _classify_document_type(filename: str, content: bytes) -> str:
    """Deterministic classification from filename/magic bytes (no LLM)."""
    name = filename.lower()
    if "boleto" in name or "slip" in name:
        return DocumentType.BOLETO
    if "comprovante" in name or "receipt" in name:
        return DocumentType.RECEIPT
    # Default: treat as invoice — the majority of the corpus
    return DocumentType.INVOICE


def _doc_to_text(content: bytes) -> str:
    """Best-effort bytes → text for the extraction prompt."""
    try:
        return content.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _decide(
    fields: ExtractionOutput,
    has_blocking_failure: bool,
    risk_score: float,
    requires_human: bool,
) -> tuple[Decision, str, DecisionBranches, str]:
    """Tree-of-Thoughts decision (prompt doc §1.8).

    Evaluate three candidate branches, score each, pick the survivor.
    Returns (decision, reason_code, branches, justification).
    """
    confidence = fields.overall_confidence()

    # Branch scores: 0 = disqualified
    auto_score = 0.0
    review_score = 0.5  # default safe choice
    reject_score = 0.0

    # auto_approve criteria: all critical fields confident, no block, no policy flag
    if not has_blocking_failure and not requires_human and confidence >= 0.85:
        auto_score = confidence

    # reject criteria: hard duplicates, fraud signals — Phase 1 only flags none
    # (dedup is handled at upload; fraud signals come in Phase 2)
    reject_score = 0.0

    # Escalate if no branch clearly wins
    review_score = max(review_score, 1.0 - auto_score - reject_score)

    branches = DecisionBranches(
        auto_approve=round(auto_score, 3),
        human_review=round(review_score, 3),
        reject=round(reject_score, 3),
    )

    if auto_score > review_score and auto_score > reject_score:
        decision = Decision.AUTO_APPROVE
        reason_code = "clean_match"
        justification = (
            f"All critical fields extracted with confidence {confidence:.0%} "
            "and no blocking validation failures."
        )
    elif reject_score > review_score:
        decision = Decision.REJECT
        reason_code = "blocked"
        justification = "Hard rejection criteria met."
    else:
        decision = Decision.HUMAN_REVIEW
        reasons = []
        if has_blocking_failure:
            reasons.append("blocking_validation_failure")
        if requires_human:
            reasons.append("policy_requires_review")
        if confidence < 0.85:
            reasons.append(f"low_confidence({confidence:.0%})")
        reason_code = "+".join(reasons) or "insufficient_evidence"
        justification = (
            f"Escalated for human review: {reason_code}. "
            "Confidence or validation results do not meet auto-approve threshold."
        )

    return decision, reason_code, branches, justification


# ---------------------------------------------------------------------------
# Main pipeline job
# ---------------------------------------------------------------------------


async def process_document(ctx: dict[str, Any], case_id: str) -> None:
    """Full pipeline for one case. Called by arq."""
    logger.info("pipeline.start case_id=%s", case_id)

    async with async_session_factory() as session:
        case = await session.get(Case, case_id)
        if case is None:
            logger.error("case not found: %s", case_id)
            return

        doc = await session.get(Document, case.document_id)
        if doc is None:
            logger.error("document not found for case: %s", case_id)
            return

        content = Path(doc.storage_path).read_bytes()

        # ── S1: CLASSIFY ────────────────────────────────────────────────────
        doc_type = _classify_document_type(doc.original_filename, content)
        case.document_type = doc_type
        await _transition(
            session, case, CaseStatus.CLASSIFIED, ActorType.SYSTEM,
            {"document_type": doc_type},
        )
        await session.commit()

        # ── S2: EXTRACT (ai_gateway + Self-Consistency k=3) ──────────────────
        doc_text = _doc_to_text(content)
        fields, ext_trace, low_agreement = await run_extraction(
            case_id=case.id,
            trace_id=case.trace_id,
            document_text=doc_text,
        )
        overall_conf = fields.overall_confidence()

        extraction = ExtractionResult(
            case_id=case.id,
            fields_json=fields.model_dump(),
            prompt_version_id=ext_trace.prompt_version_id,
            model_name=ext_trace.model,
            overall_confidence=overall_conf,
        )
        session.add(extraction)
        await persist_trace(session, ext_trace)  # best-effort; swallowed on error
        await _transition(
            session, case, CaseStatus.EXTRACTED, ActorType.AGENT,
            {
                "overall_confidence": overall_conf,
                "prompt_version_id": ext_trace.prompt_version_id,
                "model": ext_trace.model,
                "low_agreement_fields": low_agreement,
                "critical_fields_extracted": sum(
                    1 for f in fields.critical_fields() if f and f.value is not None
                ),
            },
            prompt_version_id=ext_trace.prompt_version_id,
            model_name=ext_trace.model,
        )
        await session.commit()

        # ── S3: VALIDATE (deterministic) ────────────────────────────────────
        rules, has_block = run_validations(fields)
        validation = ValidationResult(
            case_id=case.id,
            rules_json=[r.model_dump() for r in rules],
            has_blocking_failure=has_block,
        )
        session.add(validation)
        await _transition(
            session, case, CaseStatus.VALIDATED, ActorType.SYSTEM,
            {
                "rules_run": len(rules),
                "passed": sum(1 for r in rules if r.passed),
                "has_blocking_failure": has_block,
            },
        )
        await session.commit()

        # ── S4: RECONCILE (Phase 2: simple total consistency check) ──────────
        total_fv = fields.total_amount
        recon_matched = total_fv is not None and total_fv.value is not None and not has_block
        await _transition(
            session, case, CaseStatus.RECONCILED, ActorType.SYSTEM,
            {
                "matched": recon_matched,
                "deltas": [],
                "note": "phase2_simple_reconciliation",
            },
        )
        await session.commit()

        # ── S5: POLICY (Phase 2: versioned policy engine) ────────────────────
        policy_decisions, risk_score, requires_human = run_policy(
            fields=fields,
            has_blocking_failure=has_block,
            supplier_registered=False,  # Phase 3: real supplier registry lookup
            po_total=None,              # Phase 3: real PO retrieval
        )
        case.risk_score = risk_score
        await _transition(
            session, case, CaseStatus.POLICY_EVALUATED, ActorType.SYSTEM,
            {
                "risk_score": risk_score,
                "requires_human": requires_human,
                "policy_version_id": _POLICY_VERSION_ID,
                "policies": [
                    {"id": d.policy_id, "verdict": d.verdict, "requires_human": d.requires_human}
                    for d in policy_decisions
                ],
            },
        )
        await session.commit()

        # ── S6: DECIDE (Tree-of-Thoughts) ────────────────────────────────────
        decision, reason_code, branches, justification = _decide(
            fields, has_block, risk_score, requires_human
        )
        case.decision = decision
        case.reason_code = reason_code
        case.justification = justification
        await _transition(
            session, case, CaseStatus.DECIDED, ActorType.AGENT,
            {
                "decision_branches": branches.model_dump(),
                "reason_code": reason_code,
                "prompt_version_id": ext_trace.prompt_version_id,
            },
            prompt_version_id=ext_trace.prompt_version_id,
        )
        await session.commit()

        # ── S7: TERMINAL TRANSITION ──────────────────────────────────────────
        terminal_map = {
            Decision.AUTO_APPROVE: CaseStatus.AUTO_APPROVED,
            Decision.HUMAN_REVIEW: CaseStatus.IN_HUMAN_REVIEW,
            Decision.REJECT: CaseStatus.REJECTED,
        }
        terminal_status = terminal_map[Decision(decision)]
        await _transition(
            session, case, terminal_status, ActorType.AGENT,
            {"justification": justification},
        )
        await session.commit()

    logger.info("pipeline.done case_id=%s decision=%s", case_id, decision)


class WorkerSettings:
    """arq worker configuration."""

    functions: ClassVar[list[Callable[..., Any]]] = [process_document]
    redis_settings = settings.redis_url
