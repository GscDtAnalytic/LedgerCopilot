"""Document processing pipeline worker.

Run with: ``uv run arq workers.pipeline.WorkerSettings``

Macro flow:
  1. RECEIVED → CLASSIFIED  (classify document type from filename/content)
  2. CLASSIFIED → EXTRACTED  (ai_gateway + Self-Consistency k=3; doc sanitised first)
  3. EXTRACTED → VALIDATED   (deterministic rules, no LLM)
  4. VALIDATED → RECONCILED  (totals check, dedup, blocklist)
  5. RECONCILED → POLICY_EVALUATED  (versioned policy engine)
  6. POLICY_EVALUATED → DECIDED     (Tree-of-Thoughts; uses domain.decisions.decide)
  7. DECIDED → AUTO_APPROVED | IN_HUMAN_REVIEW | REJECTED

Resumable: each stage only runs when case.status == its precondition. If the
pipeline is re-invoked on a case that already passed a stage (e.g. after an edit
sets status back to EXTRACTED), it skips earlier stages and resumes from the right
point, loading intermediate results from the DB as needed.

INVARIANT: Every state transition calls `_transition()` which writes the
AuditEvent in the SAME transaction as the Case.status update.
"""

from __future__ import annotations

import logging
import time
import traceback
from collections.abc import Callable
from typing import Any, ClassVar

from apps.api.config import settings
from apps.api.database import async_session_factory
from apps.api.models import (
    AuditEvent,
    Case,
    DeadLetter,
    Document,
    ExtractionResult,
    PolicyDecision,
    ReconciliationResult,
    ValidationResult,
)
from apps.api.services.prompts import get_active_prompt_config
from apps.api.services.reference import (
    active_cost_center_codes,
    lookup_payment_total,
    lookup_po_total,
    lookup_supplier,
)
from apps.api.services.tracing import persist_trace
from arq import cron
from arq.connections import RedisSettings
from packages.agents.extraction import (
    DEFAULT_K,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    run_extraction,
)
from packages.agents.intake import run_intake
from packages.agents.review_assistant import ReviewSignals, build_explanation
from packages.domain.business_key import compute_business_key
from packages.domain.decisions import decide
from packages.domain.entities import ExtractionOutput, FieldValue
from packages.domain.enums import ActorType, Decision
from packages.domain.state_machine import CaseStatus, assert_transition
from packages.ocr.engine import OcrResult, extract_text
from packages.policy.engine import run_policy
from packages.reconciliation.engine import ReconciliationContext, ReconciliationOutput, reconcile
from packages.storage.factory import get_storage
from packages.validation.engine import ValidationContext, run_validations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from workers.bucket_scan import scan_bucket

logger = logging.getLogger(__name__)

_POLICY_VERSION_ID = "dev-1.0"
_MAX_TRIES = 3  # kept in sync with WorkerSettings.max_tries below


async def _write_dead_letter(case_id: str, error: Exception, retry_count: int) -> None:
    """Persist DeadLetter + audit_event when all retries are exhausted.

    Runs in its own session so a failure here doesn't mask the original error.
    The audit_event uses actor_type=system with the error details in the payload.
    """
    try:
        async with async_session_factory() as session:
            case = await session.get(Case, case_id)
            if case is None:
                return

            tb = traceback.format_exc()
            dl = DeadLetter(
                case_id=case_id,
                organization_id=case.organization_id,
                error_type=type(error).__name__,
                error_message=str(error)[:2000],
                retry_count=retry_count,
            )
            session.add(dl)

            audit = AuditEvent(
                case_id=case_id,
                organization_id=case.organization_id,
                actor_type=ActorType.SYSTEM,
                actor_id="pipeline",
                from_status=case.status,
                to_status=case.status,  # status does not change — case is stuck
                trace_id=case.trace_id,
                payload={
                    "event": "pipeline_dead_letter",
                    "error_type": type(error).__name__,
                    "error_message": str(error)[:500],
                    "traceback": tb[:2000],
                    "retry_count": retry_count,
                },
            )
            session.add(audit)
            await session.commit()

        logger.error(
            "pipeline.dead_letter case_id=%s retries=%d error=%s",
            case_id,
            retry_count,
            error,
        )
    except Exception:
        logger.exception("pipeline.dead_letter write failed for case_id=%s", case_id)


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

    policy_version_id is passed explicitly — deriving it from prompt_version_id
    caused it to be null on POLICY_EVALUATED transitions.
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


def _apply_ocr_cap(fields: ExtractionOutput, ocr_conf: float) -> ExtractionOutput:
    """Cap all field confidences by OCR quality (wiki: confiança por campo = min(ocr, modelo)).

    When the OCR engine is uncertain, the downstream LLM cannot produce better
    field confidence than the quality of the text it received.
    """

    def _cap(fv: FieldValue | None) -> FieldValue | None:
        if fv is None:
            return None
        return FieldValue(value=fv.value, confidence=min(fv.confidence, ocr_conf), source=fv.source)

    return ExtractionOutput(
        supplier_name=_cap(fields.supplier_name),
        tax_id_cnpj=_cap(fields.tax_id_cnpj),
        total_amount=_cap(fields.total_amount),
        currency=_cap(fields.currency),
        issue_date=_cap(fields.issue_date),
        due_date=_cap(fields.due_date),
        document_number=_cap(fields.document_number),
    )


# ─── Main pipeline job ────────────────────────────────────────────────────────


async def process_document(ctx: dict[str, Any], case_id: str) -> None:
    """Full pipeline for one case. Called by arq.

    Resumable: each stage checks case.status before running. A case already past
    a stage (e.g. VALIDATED after a human edit) will skip earlier stages and load
    intermediate data from the DB instead.

    DLQ: on the final retry attempt (job_try == _MAX_TRIES) an unhandled exception
    is written to dead_letters + audit_event and NOT re-raised so arq marks the job
    complete. Earlier failures are re-raised so arq retries.
    """
    job_try: int = ctx.get("job_try", 1)
    logger.info("pipeline.start case_id=%s try=%d/%d", case_id, job_try, _MAX_TRIES)
    try:
        await _run_pipeline(ctx, case_id)
    except Exception as exc:
        if job_try >= _MAX_TRIES:
            await _write_dead_letter(case_id, exc, retry_count=job_try)
            # Do not re-raise: arq marks job as done; case sits in dead_letters.
        else:
            logger.warning(
                "pipeline.retry case_id=%s try=%d/%d error=%s",
                case_id,
                job_try,
                _MAX_TRIES,
                exc,
            )
            raise


async def _run_pipeline(ctx: dict[str, Any], case_id: str) -> None:
    """Inner pipeline logic, extracted so process_document can wrap it cleanly."""
    logger.info("pipeline.start case_id=%s", case_id)

    # Prometheus: import best-effort so missing dep never breaks the pipeline.
    try:
        from packages.observability.metrics import (
            cases_decided_total,
            cases_received_total,
            injection_suspected_total,
            pipeline_stage_duration_ms,
        )

        _obs = True
    except Exception:
        _obs = False

    async with async_session_factory() as session:
        case = await session.get(Case, case_id)
        if case is None:
            logger.error("case not found: %s", case_id)
            return

        doc = await session.get(Document, case.document_id)
        if doc is None:
            logger.error("document not found for case: %s", case_id)
            return

        # Read raw bytes via storage backend (local dev; GCS/S3 in prod).
        storage = get_storage(
            settings.storage_backend,
            settings.storage_local_dir,
            settings.storage_gcs_bucket,
            settings.storage_gcs_prefix,
        )
        content = storage.get(doc.storage_path)

        # Extract text with OCR if needed; annotate Document with provenance.
        ocr_result: OcrResult = extract_text(content, doc.content_type)
        doc_text = ocr_result.text
        if doc.ocr_source is None:
            doc.ocr_source = ocr_result.source
            doc.ocr_confidence = ocr_result.confidence
            await session.commit()
        for w in ocr_result.warnings:
            logger.warning("ocr warning case_id=%s: %s", case_id, w)

        # Resolve the active prompt + generation config from DB (falls back to
        # in-process registry). Priority: production → staging → dev → registry.
        # This lets a staging version be tested live before production is promoted,
        # and makes per-version model/temperature/top_p/max_tokens/k take effect.
        prompt_config = (
            await get_active_prompt_config("production", session)
            or await get_active_prompt_config("staging", session)
            or await get_active_prompt_config("dev", session)
        )
        system_override = prompt_config.system_text if prompt_config is not None else None

        # ── S1: CLASSIFY (Intake agent — type + language + parse + quality) ────
        if CaseStatus(case.status) == CaseStatus.RECEIVED:
            if _obs:
                cases_received_total.labels(org_id=case.organization_id).inc()
            _t1 = time.monotonic()
            intake = run_intake(
                filename=doc.original_filename,
                content=content,
                content_type=doc.content_type,
                text=doc_text,
                ocr_confidence=ocr_result.confidence,
                ocr_is_low_quality=ocr_result.is_low_quality,
            )
            case.document_type = intake.document_type
            await _transition(
                session,
                case,
                CaseStatus.CLASSIFIED,
                ActorType.SYSTEM,
                {
                    "document_type": intake.document_type,
                    "language": intake.language,
                    "parse_strategy": intake.parse_strategy,
                    "out_of_scope_reason": intake.out_of_scope_reason,
                },
            )
            await session.commit()
            if _obs:
                pipeline_stage_duration_ms.labels(stage="classify").observe(
                    (time.monotonic() - _t1) * 1000
                )

        # ── S2: EXTRACT ───────────────────────────────────────────────────────
        # Local state — populated either by running extraction or loaded from DB.
        fields: ExtractionOutput | None = None
        ext_trace = None
        low_agreement: list[str] = []
        injection_suspected = False

        if CaseStatus(case.status) == CaseStatus.CLASSIFIED:
            _t2 = time.monotonic()
            fields, ext_trace, low_agreement, injection_suspected = await run_extraction(
                case_id=case.id,
                trace_id=case.trace_id,
                document_text=doc_text,
                # Standard mode: system_override + generation config from the active
                # DB version (coalesced defaults when None → unchanged behaviour).
                # Quarantine mode: system_override and these overrides are ignored
                # inside run_extraction (the quarantine prompt/config is immutable).
                system_override=system_override,
                model=prompt_config.model if prompt_config is not None else None,
                temperature=(
                    prompt_config.temperature if prompt_config is not None else DEFAULT_TEMPERATURE
                ),
                top_p=prompt_config.top_p if prompt_config is not None else None,
                max_tokens=(
                    prompt_config.max_tokens if prompt_config is not None else DEFAULT_MAX_TOKENS
                ),
                k=prompt_config.k if prompt_config is not None else DEFAULT_K,
                quarantine_mode=settings.dual_llm_enabled,
                quarantine_model=settings.quarantine_model if settings.dual_llm_enabled else None,
            )

            # Cap field confidences by OCR quality when OCR was used.
            # Wiki: "confiança por campo derivada do OCR + modelo" — the LLM cannot
            # produce better confidence than the quality of the text it received.
            if ocr_result.is_low_quality:
                fields = _apply_ocr_cap(fields, ocr_result.confidence)
                if "ocr_quality" not in low_agreement:
                    low_agreement.append("ocr_quality")

            overall_conf = fields.overall_confidence()

            extraction = ExtractionResult(
                case_id=case.id,
                fields_json=fields.model_dump(),
                prompt_version_id=ext_trace.prompt_version_id,
                model_name=ext_trace.model,
                overall_confidence=overall_conf,
                injection_suspected=injection_suspected,
            )
            session.add(extraction)
            await persist_trace(session, ext_trace)
            await _transition(
                session,
                case,
                CaseStatus.EXTRACTED,
                ActorType.AGENT,
                {
                    "overall_confidence": overall_conf,
                    "prompt_version_id": ext_trace.prompt_version_id,
                    "model": ext_trace.model,
                    "low_agreement_fields": low_agreement,
                    "injection_suspected": injection_suspected,
                    "ocr_source": ocr_result.source,
                    "ocr_confidence": ocr_result.confidence,
                    "dual_llm_mode": settings.dual_llm_enabled,
                    "critical_fields_extracted": sum(
                        1 for f in fields.critical_fields() if f and f.value is not None
                    ),
                },
                prompt_version_id=ext_trace.prompt_version_id,
                model_name=ext_trace.model,
            )
            await session.commit()
            if _obs:
                pipeline_stage_duration_ms.labels(stage="extract").observe(
                    (time.monotonic() - _t2) * 1000
                )
                if injection_suspected:
                    injection_suspected_total.inc()

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
                # Reload the persisted injection signal (LC migration c4d5e6f7a8b9) so a
                # resumed run does not silently lose it — context propagation across
                # stages.
                injection_suspected = ext_row.injection_suspected

        if fields is None:
            logger.error("no extraction result for case %s — aborting", case_id)
            return

        # Compute business key once after extraction and save to case.
        # Idempotent: if already set (resume path), keep existing value.
        if not case.business_key:
            bk = compute_business_key(fields)
            if bk:
                case.business_key = bk
                await session.commit()

        # ── S3: VALIDATE ──────────────────────────────────────────────────────
        has_block = False
        failed_block_rules: list[str] = []  # for the Review Assistant explanation

        if CaseStatus(case.status) == CaseStatus.EXTRACTED:
            _t3 = time.monotonic()
            # Inject the org's active cost-center codes so "cost_center inválido" can
            # Actual blocking decided by policy (reference data fetched at the I/O boundary).
            valid_ccs = await active_cost_center_codes(session, case.organization_id)
            val_ctx = ValidationContext(valid_cost_centers=valid_ccs or None)
            rules, has_block = run_validations(fields, val_ctx)
            failed_block_rules = [r.rule for r in rules if r.severity == "block" and not r.passed]
            validation = ValidationResult(
                case_id=case.id,
                rules_json=[r.model_dump() for r in rules],
                has_blocking_failure=has_block,
            )
            session.add(validation)
            await _transition(
                session,
                case,
                CaseStatus.VALIDATED,
                ActorType.SYSTEM,
                {
                    "rules_run": len(rules),
                    "passed": sum(1 for r in rules if r.passed),
                    "has_blocking_failure": has_block,
                },
            )
            await session.commit()
            if _obs:
                pipeline_stage_duration_ms.labels(stage="validate").observe(
                    (time.monotonic() - _t3) * 1000
                )

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
                failed_block_rules = [
                    r["rule"]
                    for r in (val_row.rules_json or [])
                    if r.get("severity") == "block" and not r.get("passed")
                ]

        # ── S4: RECONCILE ─────────────────────────────────────────────────────
        # Local state populated here and reloaded on the resume path.
        recon_out: ReconciliationOutput | None = None
        duplicate_case_id: str | None = None  # for the Review Assistant explanation

        if CaseStatus(case.status) == CaseStatus.VALIDATED:
            _t4 = time.monotonic()
            # Business-key dedup check: look for a non-rejected,
            # non-initial case in the same org with the same business key.
            # States excluded: received/classified (brand new, may still fail);
            # rejected (explicitly dismissed — a re-submission is valid).
            business_key_seen = False
            if case.business_key:
                excluded_statuses = frozenset({"received", "classified", "rejected"})
                dup = await session.scalar(
                    select(Case).where(
                        Case.organization_id == case.organization_id,
                        Case.business_key == case.business_key,
                        Case.id != case.id,
                        Case.status.not_in(excluded_statuses),
                    )
                )
                business_key_seen = dup is not None
                duplicate_case_id = dup.id if dup is not None else None

            # Context injected at the I/O boundary: PO/payment totals,
            # supplier blocklist from the reference tables, and business_key_seen.
            cnpj_val = fields.tax_id_cnpj.value if fields.tax_id_cnpj else None
            docnum_val = fields.document_number.value if fields.document_number else None
            supplier_info = await lookup_supplier(
                session, case.organization_id, str(cnpj_val) if cnpj_val else None
            )
            po_total = await lookup_po_total(
                session, case.organization_id, str(cnpj_val) if cnpj_val else None
            )
            payment_total = await lookup_payment_total(
                session, case.organization_id, str(docnum_val) if docnum_val else None
            )
            recon_ctx = ReconciliationContext(
                po_total=po_total,
                payment_total=payment_total,
                business_key_seen=business_key_seen,
                supplier_blocklisted=supplier_info.blocklisted,
            )
            recon_out = reconcile(fields, recon_ctx)

            recon_record = ReconciliationResult(
                case_id=case.id,
                matched=recon_out.matched,
                deltas_json=[d.model_dump() for d in recon_out.deltas],
                risk_delta=recon_out.risk_delta,
                reject_reason=recon_out.reject_reason,
            )
            session.add(recon_record)
            await _transition(
                session,
                case,
                CaseStatus.RECONCILED,
                ActorType.SYSTEM,
                {
                    "matched": recon_out.matched,
                    "deltas": [d.model_dump() for d in recon_out.deltas],
                    "risk_delta": recon_out.risk_delta,
                    "reject_reason": recon_out.reject_reason,
                },
            )
            await session.commit()
            if _obs:
                pipeline_stage_duration_ms.labels(stage="reconcile").observe(
                    (time.monotonic() - _t4) * 1000
                )

        # Resume path: load reconciliation result if S4 was already done.
        if recon_out is None and CaseStatus(case.status) != CaseStatus.VALIDATED:
            recon_row = await session.scalar(
                select(ReconciliationResult)
                .where(ReconciliationResult.case_id == case_id)
                .order_by(ReconciliationResult.created_at.desc())
                .limit(1)
            )
            if recon_row is not None:
                recon_out = ReconciliationOutput(
                    matched=recon_row.matched,
                    deltas=[],
                    risk_delta=recon_row.risk_delta,
                    reject_reason=recon_row.reject_reason,
                )

        # ── S5: POLICY ────────────────────────────────────────────────────────
        policy_decisions: list[Any] = []
        risk_score = 0.0
        requires_human = False

        if CaseStatus(case.status) == CaseStatus.RECONCILED:
            _t5 = time.monotonic()
            # Re-fetch reference data here so the policy stage is correct on the resume
            # path too (e.g. after a human edit re-enters at VALIDATED, locals from the
            # reconcile block above are not in scope).
            p_cnpj = fields.tax_id_cnpj.value if fields.tax_id_cnpj else None
            p_supplier = await lookup_supplier(
                session, case.organization_id, str(p_cnpj) if p_cnpj else None
            )
            p_po_total = await lookup_po_total(
                session, case.organization_id, str(p_cnpj) if p_cnpj else None
            )
            policy_decisions, risk_score, requires_human = run_policy(
                fields=fields,
                has_blocking_failure=has_block,
                supplier_registered=p_supplier.registered,
                po_total=p_po_total,
            )
            # Add reconciliation risk on top of policy risk.
            if recon_out:
                risk_score = min(1.0, risk_score + recon_out.risk_delta)
                # Soft mismatch (value delta, not a hard reject) also escalates to review.
                if not recon_out.matched and not recon_out.reject_reason:
                    requires_human = True

            # Injection suspicion is an additional escalation signal.
            if injection_suspected:
                requires_human = True
                risk_score = min(1.0, risk_score + 0.5)

            case.risk_score = risk_score
            await _transition(
                session,
                case,
                CaseStatus.POLICY_EVALUATED,
                ActorType.SYSTEM,
                {
                    "risk_score": risk_score,
                    "requires_human": requires_human,
                    "injection_suspected": injection_suspected,
                    "policy_version_id": _POLICY_VERSION_ID,
                    "recon_reject_reason": recon_out.reject_reason if recon_out else None,
                    "requires_dual_approval": any(
                        getattr(d, "requires_dual_approval", False) for d in policy_decisions
                    ),
                    "policies": [
                        {"id": d.policy_id, "verdict": d.verdict, "req_human": d.requires_human}
                        for d in policy_decisions
                    ],
                },
                # policy_version_id passed explicitly — was previously derived from
                # prompt_version_id, which left the column null on POLICY_EVALUATED transitions.
                policy_version_id=_POLICY_VERSION_ID,
            )
            # Materialise each policy result as a queryable row.
            for pd in policy_decisions:
                session.add(
                    PolicyDecision(
                        case_id=case_id,
                        policy_id=pd.policy_id,
                        verdict=pd.verdict,
                        requires_human=pd.requires_human,
                        risk_delta=pd.risk_delta,
                        reason=pd.reason,
                        policy_version_id=_POLICY_VERSION_ID,
                        requires_dual_approval=getattr(pd, "requires_dual_approval", False),
                    )
                )
            await session.commit()
            if _obs:
                pipeline_stage_duration_ms.labels(stage="policy").observe(
                    (time.monotonic() - _t5) * 1000
                )

        # ── S6: DECIDE ────────────────────────────────────────────────────────
        if CaseStatus(case.status) == CaseStatus.POLICY_EVALUATED:
            recon_reject_reason = recon_out.reject_reason if recon_out else None
            # Use the shared domain function (eval/runner.py uses the same path to stay consistent).
            decision, reason_code, branches, _decide_just = decide(
                fields,
                has_block,
                risk_score,
                requires_human,
                injection_suspected,
                recon_reject_reason=recon_reject_reason,
            )
            # Review Assistant (Agent 6): build the analyst-facing explanation from
            # the structured signals the deterministic engines produced. Deterministic,
            # so the justification is faithful to what actually drove the decision.
            signals = ReviewSignals(
                decision=decision,
                confidence=fields.overall_confidence(),
                has_blocking_failure=has_block,
                failed_block_rules=failed_block_rules,
                injection_suspected=injection_suspected,
                supplier_unknown=any(
                    getattr(d, "policy_id", None) == "p-supplier-unknown" for d in policy_decisions
                ),
                missing_purchase_order=any(
                    getattr(d, "policy_id", None) == "p-amount-delta-missing"
                    for d in policy_decisions
                ),
                value_mismatch=bool(
                    recon_out
                    and not recon_out.matched
                    and not recon_out.reject_reason
                    and recon_out.deltas
                ),
                value_delta_pct=(
                    recon_out.deltas[0].delta_pct if recon_out and recon_out.deltas else None
                ),
                duplicate_of=(
                    duplicate_case_id if recon_reject_reason == "duplicate_invoice" else None
                ),
                supplier_blocklisted=recon_reject_reason == "supplier_blocklisted",
            )
            explanation = build_explanation(signals)

            case.decision = decision
            # Prefer the granular reason tags from the Review Assistant when it has
            # something more specific than decide()'s coarse code (e.g. on review).
            case.reason_code = "+".join(explanation.reasons) or reason_code
            case.justification = explanation.summary
            prompt_vid = ext_trace.prompt_version_id if ext_trace else None
            await _transition(
                session,
                case,
                CaseStatus.DECIDED,
                ActorType.AGENT,
                {
                    "decision_branches": branches.model_dump(),
                    "reason_code": case.reason_code,
                    "decide_reason_code": reason_code,
                    "evidence_refs": explanation.evidence_refs,
                    "justification": explanation.summary,
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
                session,
                case,
                terminal_status,
                ActorType.AGENT,
                {"justification": case.justification},
            )
            await session.commit()
            if _obs:
                cases_decided_total.labels(
                    decision=terminal_status.value, org_id=case.organization_id
                ).inc()

            # Start durable Temporal HITL workflow when case needs human review.
            # Temporal tracks the wait durably and fires the SLA timer; the arq pipeline
            # is done at this point — it does not re-run until the reviewer edits the case.
            if terminal_status == CaseStatus.IN_HUMAN_REVIEW:
                try:
                    from apps.api.temporal_client import start_hitl_workflow

                    await start_hitl_workflow(case_id)
                    if _obs:
                        from packages.observability.metrics import hitl_workflows_started_total

                        hitl_workflows_started_total.inc()
                except Exception as exc:
                    # Temporal unavailable — log warning; case is correctly in
                    # IN_HUMAN_REVIEW in DB. The review endpoint still works without Temporal.
                    logger.warning(
                        "pipeline.hitl_workflow_start_failed case_id=%s error=%s",
                        case_id,
                        exc,
                    )

    logger.info("pipeline.done case_id=%s decision=%s", case_id, case.decision)


class WorkerSettings:
    """arq worker configuration.

    max_tries=3 means arq calls process_document up to 3 times on failure.
    On the 3rd failure process_document catches the exception and writes to dead_letters
    instead of re-raising, so arq marks the job as complete.

    cron_jobs: scan_bucket runs every 5 minutes to ingest files dropped into storage
    out-of-band via the "bucket" channel.
    """

    functions: ClassVar[list[Callable[..., Any]]] = [process_document]
    # arq needs a RedisSettings object, not a DSN string (matches apps/api/redis_pool.py).
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_tries = _MAX_TRIES
    cron_jobs: ClassVar[list[Any]] = [cron(scan_bucket, minute=set(range(0, 60, 5)))]
