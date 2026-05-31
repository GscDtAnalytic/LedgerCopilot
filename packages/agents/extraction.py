"""Extraction agent — calls the ai_gateway and runs Self-Consistency k=3.

For the three critical fields (total_amount, tax_id_cnpj, document_number) we
run k=3 independent extractions and reconcile by majority vote:
  - 3/3 agree  → accept value, confidence unchanged
  - 2/3 agree  → accept majority, add low_agreement flag, cap confidence at 0.75
  - 0 agreement → field = null, confidence 0.0, forcing human_review

Document text is sanitised before LLM injection. injection_suspected is returned
so the pipeline can propagate it to the policy engine and decide().

The final ExtractionOutput is always validated by the Pydantic model — never
raw JSON from the model.

Dual LLM / Quarantine mode
---------------------------
When quarantine_mode=True:
  - prompt_alias: "quarantine" (ultra-restrictive; explicit sandbox framing)
  - system_override from DB: BLOCKED — quarantine prompt is immutable
  - k: 1 (deterministic; quarantine goal is isolation, not diversity sampling)
  - temperature: 0.0
  - model: quarantine_model arg (cheaper model, e.g. Haiku)

Trust boundary:
  UNTRUSTED:  raw document text → quarantine LLM call
  BOUNDARY:   Pydantic-validated ExtractionOutput (this function's return value)
  TRUSTED:    policy, reconcile, decide (pure Python — never see raw text)
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
_K_QUARANTINE = 1  # k=1 in quarantine mode; determinism > diversity

# Standard-mode generation defaults. A DB prompt version may override these
# (apps/api/services/prompts.get_active_prompt_config); when its columns are NULL
# these defaults apply, preserving today's behaviour.
DEFAULT_TEMPERATURE = 1.0  # temperature=1.0 gives Self-Consistency diversity across k runs
DEFAULT_MAX_TOKENS = 512
DEFAULT_K = _K  # Self-Consistency fan-out (public alias of _K for config defaults)


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

    # Self-Consistency needs >=2 samples to vote. With a single run (k=1: quarantine
    # mode, or a version tuned to k=1) there is no agreement signal to apply, so accept
    # the run as-is rather than nulling every critical field for lack of a second vote.
    if len(runs) < 2:
        return merged, low_agreement

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
    model: str | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    top_p: float | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    k: int = _K,
    quarantine_mode: bool = False,
    quarantine_model: str | None = None,
) -> tuple[ExtractionOutput, ModelTrace, list[str], bool]:
    """Extract fields from document text.

    Standard mode (quarantine_mode=False):
      SC fan-out of k runs, prompt_alias="dev", system_override honoured. The
      generation config (model/temperature/top_p/max_tokens/k) comes from the active
      DB prompt version — defaults preserve the historic k=3, temperature=1.0,
      max_tokens=512 behaviour when the version leaves those columns NULL.

    Quarantine mode (quarantine_mode=True):
      SC k=1, temperature=0.0, prompt_alias="quarantine", system_override BLOCKED.
      The quarantine LLM uses a dedicated prompt that explicitly forbids following
      document instructions and cannot be weakened via the DB prompt admin; its
      config is fixed and ignores the per-version overrides above.
      quarantine_model overrides the model (e.g. Haiku — cheaper, sufficient for extraction).

    Returns:
      (merged_output, representative_trace, low_agreement_fields, injection_suspected)
    """
    sanitised_text, injection_suspected = sanitise(document_text)
    user_msg = f"OCR_TEXT:\n<<<\n{sanitised_text}\n>>>"

    if quarantine_mode:
        # Quarantine: single deterministic call; system_override blocked so the
        # immutable quarantine prompt cannot be weakened via the DB admin panel.
        tasks = [
            gateway_call(
                case_id=case_id,
                trace_id=trace_id,
                prompt_alias="quarantine",
                user_message=user_msg,
                response_model=ExtractionOutput,
                stage="extraction-quarantine",
                max_tokens=512,
                temperature=0.0,
                system_override=None,  # BLOCKED — quarantine prompt is immutable
                model=quarantine_model,
            )
        ]
    else:
        # Standard: k runs (default 3) at the version's temperature for Self-Consistency
        # diversity. AsyncAnthropic makes these truly parallel.
        tasks = [
            gateway_call(
                case_id=case_id,
                trace_id=trace_id,
                prompt_alias="dev",
                user_message=user_msg,
                response_model=ExtractionOutput,
                stage="extraction",
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                system_override=system_override,
            )
            for _ in range(max(1, k))
        ]

    results: list[tuple[ExtractionOutput, ModelTrace]] = await asyncio.gather(*tasks)

    runs = [r for r, _ in results]
    trace = results[0][1]

    merged, low_agreement = _reconcile(runs)
    return merged, trace, low_agreement, injection_suspected
