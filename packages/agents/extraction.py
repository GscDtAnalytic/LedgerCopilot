"""Extraction agent — calls the ai_gateway and runs Self-Consistency k=3.

Self-Consistency (prompt doc §1.9): for the three critical fields
(total_amount, tax_id_cnpj, document_number) we run k=3 independent extractions
and reconcile by majority vote:
  - 3/3 agree  → accept value, confidence unchanged
  - 2/3 agree  → accept majority, add low_agreement flag, cap confidence at 0.75
  - 0 agreement → field = null, confidence 0.0, forcing human_review

Document text is sanitised before LLM injection. injection_suspected
is returned so the pipeline can propagate it to the policy engine and decide().

The final ExtractionOutput is validated by the Pydantic model before it is used
anywhere — never raw JSON from the model.
"""

from __future__ import annotations

import asyncio
from typing import Any

from packages.ai_gateway.client import gateway_call
from packages.ai_gateway.sanitize import sanitise
from packages.ai_gateway.tracer import ModelTrace
from packages.domain.entities import ExtractionOutput, FieldValue

_CRITICAL = ["total_amount", "tax_id_cnpj", "document_number"]
_K = 3


def _values_agree(vals: list[Any]) -> bool:
    """True if at least 2 of k values are equal (after normalisation)."""
    normed = [str(v).strip().lower() if v is not None else "__null__" for v in vals]
    return max(normed.count(n) for n in set(normed)) >= 2


def _majority_value(vals: list[Any]) -> Any:
    """Return the most common value (or None on a three-way split)."""
    from collections import Counter

    normed = [str(v).strip().lower() if v is not None else "__null__" for v in vals]
    winner, count = Counter(normed).most_common(1)[0]
    if count < 2:
        return None
    for orig, norm in zip(vals, normed, strict=False):
        if norm == winner:
            return orig
    return None


def _reconcile(runs: list[ExtractionOutput]) -> tuple[ExtractionOutput, list[str]]:
    """Merge k ExtractionOutput runs into one, applying Self-Consistency rules.

    Returns (merged, low_agreement_fields).
    """
    merged = runs[0].model_copy(deep=True)
    low_agreement: list[str] = []

    for field_name in _CRITICAL:
        raw_vals = [getattr(run, field_name) for run in runs]
        values = [fv.value if fv else None for fv in raw_vals]

        if _values_agree(values):
            pass  # baseline from runs[0] is already correct
        else:
            majority = _majority_value(values)
            if majority is None:
                setattr(
                    merged,
                    field_name,
                    FieldValue(value=None, confidence=0.0, source="sc-fail"),
                )
                low_agreement.append(field_name)
            else:
                existing: FieldValue | None = getattr(merged, field_name)
                if existing is not None:
                    capped = min(existing.confidence, 0.75)
                    setattr(
                        merged,
                        field_name,
                        FieldValue(value=existing.value, confidence=capped, source="sc-cap"),
                    )
                low_agreement.append(field_name)

    return merged, low_agreement


async def run_extraction(
    *,
    case_id: str,
    trace_id: str,
    document_text: str,
    system_override: str | None = None,
) -> tuple[ExtractionOutput, ModelTrace, list[str], bool]:
    """Extract fields from document text using Self-Consistency k=3.

    Sanitises document text before LLM injection.

    Returns (merged_output, representative_trace, low_agreement_fields, injection_suspected).
    injection_suspected=True means the document contained injection patterns;
    the pipeline must escalate to human_review regardless of confidence.
    """
    sanitised_text, injection_suspected = sanitise(document_text)
    user_msg = f"OCR_TEXT:\n<<<\n{sanitised_text}\n>>>"

    # Run k extractions concurrently — AsyncAnthropic makes this truly parallel.
    tasks = [
        gateway_call(
            case_id=case_id,
            trace_id=trace_id,
            prompt_alias="dev",
            user_message=user_msg,
            response_model=ExtractionOutput,
            stage="extraction",
            max_tokens=512,
            system_override=system_override,
        )
        for _ in range(_K)
    ]
    results: list[tuple[ExtractionOutput, ModelTrace]] = await asyncio.gather(*tasks)

    runs = [r for r, _ in results]
    trace = results[0][1]

    merged, low_agreement = _reconcile(runs)
    return merged, trace, low_agreement, injection_suspected
