"""Document processing pipeline worker.

Run with: ``uv run arq workers.pipeline.WorkerSettings``

Macro flow:
  1. RECEIVED → CLASSIFIED  (classify document type from filename/content)
  2. CLASSIFIED → EXTRACTED  (ai_gateway + Self-Consistency k=3; doc sanitised first)
  3. EXTRACTED → VALIDATED   (deterministic rules, no LLM)
  4. VALIDATED → RECONCILED  (simple totals check — Phase 2 placeholder)
  5. RECONCILED → POLICY_EVALUATED  (versioned policy engine)
  6. POLICY_EVALUATED → DECIDED     (Tree-of-Thoughts; uses domain.decisions.decide)
  7. DECIDED → AUTO_APPROVED | IN_HUMAN_REVIEW | REJECTED

Resumable pipeline:
  Each stage only runs when case.status == its precondition. If the pipeline is
  re-invoked on a case that already passed a stage (e.g. after an edit sets status
  back to VALIDATED), it skips the earlier stages and resumes from the right point,
  loading intermediate results from the DB as needed.

INVARIANT: Every state transition calls `_transition()` which writes the
AuditEvent in the SAME transaction as the Case.status update.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

from apps.api.config import settings
from apps.api.database import async_session_factory
from apps.api.models import AuditEvent, Case, Document, ExtractionResult, ValidationResult
from apps.api.services.prompts import get_active_system_text
from apps.api.services.tracing import persist_trace
from packages.agents.extraction import run_extraction
from packages.domain.decisions import decide
from packages.domain.entities import ExtractionOutput
from packages.domain.enums import ActorType, Decision, DocumentType
from packages.domain.state_machine import CaseStatus, assert_transition
from packages.policy.engine import run_policy
from packages.validation.engine import run_validations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_POLICY_VERSION_ID = "dev-1.0"


# ─── Atomic transition helper ─────────────────────────────────────────────────


async def _transition(
    session: AsyncSession,
    case: Case,
    target: CaseStatus,
    actor_type: ActorType,
    payload: dict[str, Any],
    *,
    actor_id: str = "pipeline",
    prompt_version_id: str | None = None,
    policy_version_id: str | None = None,
    model_name: str | None = None,
) -> None:
    """Validate + apply a state transition, writing audit_event atomically.

    policy_version_id is now passed explicitly — previously it was
    derived from prompt_version_id which caused it to be null on POLICY_EVALUATED.
    """
    assert_transition(CaseStatus(case.status), target)

    audit = AuditEvent(
        case_id=case.id,
        organization_id=case.organization_id,
        actor_type=actor_type,
        actor_id=actor_id,
        from_status=case.status,
        to_status=target,
        prompt_version_id=prompt_version_id,
        policy_version_id=policy_version_id,
        model_name=model_name,
        trace_id=case.trace_id,
        payload=payload,
    )
    case.status = target
    session.add(audit)
    await session.flush()


# ─── Stage helpers ────────────────────────────────────────────────────────────


def _classify_document_type(filename: str, content: bytes) -> str:
    """Deterministic classification from filename/magic bytes (no LLM)."""
    name = filename.lower()
    if "boleto" in name or "slip" in name:
        return DocumentType.BOLETO
    if "comprovante" in name or "receipt" in name:
        return DocumentType.RECEIPT
    return DocumentType.INVOICE


def _doc_to_text(content: bytes) -> str:
    try:
        return content.decode("utf-8", errors="replace")
    except Exception:
        return ""


# ─── Main pipeline job ────────────────────────────────────────────────────────


async def process_document(ctx: dict[str, Any], case_id: str) -> None:
    """Full pipeline for one case. Called by arq.

    Resumable: each stage checks case.status before running. A case already past
    a stage (e.g. VALIDATED after a human edit) will skip earlier stages and load
    intermediate data from the DB instead.
    """
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
        doc_text = _doc_to_text(content)

        # Resolve the active production prompt from DB.
        # Falls back to None → ai_gateway uses its in-process registry.
        system_override = await get_active_system_text("production", session)

        # ── S1: CLASSIFY ──────────────────────────────────────────────────────
        if CaseStatus(case.status) == CaseStatus.RECEIVED:
            doc_type = _classify_document_type(doc.original_filename, content)
            case.document_type = doc_type
            await _transition(
                session, case, CaseStatus.CLASSIFIED, ActorType.SYSTEM,
                {"document_type": doc_type},
            )
            await session.commit()

        # ── S2: EXTRACT ───────────────────────────────────────────────────────
        # Local state — populated either by running extraction or loaded from DB.
        fields: ExtractionOutput | None = None
        ext_trace = None
        low_agreement: list[str] = []
        injection_suspected = False

        if CaseStatus(case.status) == CaseStatus.CLASSIFIED:
            fields, ext_trace, low_agreement, injection_suspected = await run_extraction(
                case_id=case.id,
                trace_id=case.trace_id,
                document_text=doc_text,
                system_override=system_override,
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
            await persist_trace(session, ext_trace)
            await _transition(
                session, case, CaseStatus.EXTRACTED, ActorType.AGENT,
                {
                    "overall_confidence": overall_conf,
                    "prompt_version_id": ext_trace.prompt_version_id,
                    "model": ext_trace.model,
                    "low_agreement_fields": low_agreement,
                    "injection_suspected": injection_suspected,
                    "critical_fields_extracted": sum(
                        1 for f in fields.critical_fields() if f and f.value is not None
                    ),
                },
                prompt_version_id=ext_trace.prompt_version_id,
                model_name=ext_trace.model,
            )
            await session.commit()

        # Resume path: load extraction from DB if stage was already done.
        if fields is None:
            ext_row = await session.scalar(
                select(ExtractionResult)
                .where(ExtractionResult.case_id == case_id)
                .order_by(ExtractionResult.created_at.desc())
                .limit(1)
            )
            if ext_row is not None:
                fields = ExtractionOutput.model_validate(ext_row.fields_json)
                # injection_suspected is not persisted; conservative default is False
                # (human editors are trusted, and the sanitiser ran on the original text).

        if fields is None:
            logger.error("no extraction result for case %s — aborting", case_id)
            return

        # ── S3: VALIDATE ──────────────────────────────────────────────────────
        has_block = False

        if CaseStatus(case.status) == CaseStatus.EXTRACTED:
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

        # Resume path: load has_block from DB if validation already ran.
        if CaseStatus(case.status) != CaseStatus.EXTRACTED:
            val_row = await session.scalar(
                select(ValidationResult)
                .where(ValidationResult.case_id == case_id)
                .order_by(ValidationResult.created_at.desc())
                .limit(1)
            )
            if val_row is not None:
                has_block = val_row.has_blocking_failure

        # ── S4: RECONCILE ─────────────────────────────────────────────────────
        if CaseStatus(case.status) == CaseStatus.VALIDATED:
            recon_matched = (
                fields.total_amount is not None
                and fields.total_amount.value is not None
                and not has_block
            )
            await _transition(
                session, case, CaseStatus.RECONCILED, ActorType.SYSTEM,
                {
                    "matched": recon_matched,
                    "deltas": [],
                    "note": "phase2_simple_reconciliation",
                },
            )
            await session.commit()

        # ── S5: POLICY ────────────────────────────────────────────────────────
        policy_decisions: list[Any] = []
        risk_score = 0.0
        requires_human = False

        if CaseStatus(case.status) == CaseStatus.RECONCILED:
            policy_decisions, risk_score, requires_human = run_policy(
                fields=fields,
                has_blocking_failure=has_block,
                supplier_registered=False,
                po_total=None,
            )
            # Injection suspicion is an additional escalation signal.
            if injection_suspected:
                requires_human = True
                risk_score = min(1.0, risk_score + 0.5)

            case.risk_score = risk_score
            await _transition(
                session, case, CaseStatus.POLICY_EVALUATED, ActorType.SYSTEM,
                {
                    "risk_score": risk_score,
                    "requires_human": requires_human,
                    "injection_suspected": injection_suspected,
                    "policy_version_id": _POLICY_VERSION_ID,
                    "policies": [
                        {"id": d.policy_id, "verdict": d.verdict, "req_human": d.requires_human}
                        for d in policy_decisions
                    ],
                },
                # policy_version_id passed explicitly ( — was deriving from
                # prompt_version_id which left the column null on this transition).
                policy_version_id=_POLICY_VERSION_ID,
            )
            await session.commit()

        # ── S6: DECIDE ────────────────────────────────────────────────────────
        if CaseStatus(case.status) == CaseStatus.POLICY_EVALUATED:
            # Use the shared domain function.
            decision, reason_code, branches, justification = decide(
                fields, has_block, risk_score, requires_human, injection_suspected
            )
            case.decision = decision
            case.reason_code = reason_code
            case.justification = justification
            prompt_vid = ext_trace.prompt_version_id if ext_trace else None
            await _transition(
                session, case, CaseStatus.DECIDED, ActorType.AGENT,
                {
                    "decision_branches": branches.model_dump(),
                    "reason_code": reason_code,
                    "prompt_version_id": prompt_vid,
                },
                prompt_version_id=prompt_vid,
            )
            await session.commit()

        # ── S7: TERMINAL ──────────────────────────────────────────────────────
        if CaseStatus(case.status) == CaseStatus.DECIDED:
            terminal_map = {
                Decision.AUTO_APPROVE: CaseStatus.AUTO_APPROVED,
                Decision.HUMAN_REVIEW: CaseStatus.IN_HUMAN_REVIEW,
                Decision.REJECT: CaseStatus.REJECTED,
            }
            terminal_status = terminal_map[Decision(case.decision or "human_review")]
            await _transition(
                session, case, terminal_status, ActorType.AGENT,
                {"justification": case.justification},
            )
            await session.commit()

    logger.info("pipeline.done case_id=%s decision=%s", case_id, case.decision)


class WorkerSettings:
    """arq worker configuration."""

    functions: ClassVar[list[Callable[..., Any]]] = [process_document]
    redis_settings = settings.redis_url
