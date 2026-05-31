"""Core evaluation logic — runs fixtures through the extraction + decision pipeline.

Used by eval.run (CLI) and eval.gate (comparison). Kept separate so both
can import it without duplicating logic.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from packages.agents.extraction import (
    DEFAULT_K,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    run_extraction,
)
from packages.domain.decisions import decide
from packages.domain.entities import FieldValue
from packages.policy.engine import run_policy
from packages.validation.engine import ValidationContext, run_validations

_DATASET_ROOT = Path(__file__).parent / "dataset"

CRITICAL_FIELDS = ["supplier_name", "tax_id_cnpj", "total_amount", "document_number"]


@dataclass(frozen=True)
class EvalConfig:
    """Generation config a candidate version is evaluated under.

    Eval must run with the *version's* config, not registry defaults — otherwise a
    version's scorecard does not reflect the version and comparing two versions
    compares noise. Defaults reproduce the historic behaviour (registry prompt,
    temperature=1.0, max_tokens=512, k=3) so the CLI is unchanged when no config
    is supplied.
    """

    system_text: str | None = None
    model: str | None = None
    temperature: float = DEFAULT_TEMPERATURE
    top_p: float | None = None
    max_tokens: int = DEFAULT_MAX_TOKENS
    k: int = DEFAULT_K


# Fields the pipeline actually controls (SC k=3 + overall_confidence weighting).
# Gate uses these, not CRITICAL_FIELDS.
_DOMAIN_CRITICAL = ["total_amount", "tax_id_cnpj", "document_number"]


@dataclass
class FixtureResult:
    fixture_id: str
    slice_name: str
    expected_decision: str
    actual_decision: str
    field_accuracy: dict[str, bool]
    overall_confidence: float
    latency_ms: float
    cost_usd: float
    model: str
    prompt_version_id: str
    is_false_auto_approve: bool  # auto_approved when it should not be
    supplier_name_matched: bool


@dataclass
class Scorecard:
    prompt_version_id: str
    total_fixtures: int
    slices: dict[str, int] = field(default_factory=dict)
    # Field-level accuracy (fraction of fixtures where field exactly matched expected)
    field_accuracy: dict[str, float] = field(default_factory=dict)
    # Overall metrics
    exact_field_accuracy: float = 0.0
    missing_critical_fields_rate: float = 0.0
    false_auto_approve_rate: float = 0.0
    supplier_name_accuracy: float = 0.0  # informational only — not a gate rule
    critical_field_accuracy: float = 0.0  # mean accuracy for domain-critical fields (gate rule)
    decision_accuracy: float = 0.0
    avg_cost_per_doc: float = 0.0
    p95_latency_ms: float = 0.0
    # Baseline for gate comparison (set externally)
    baseline_false_auto_approve_rate: float = 0.0

    def as_dict(self) -> dict:
        return {
            "prompt_version_id": self.prompt_version_id,
            "total_fixtures": self.total_fixtures,
            "slices": self.slices,
            "field_accuracy": self.field_accuracy,
            "exact_field_accuracy": round(self.exact_field_accuracy, 4),
            "missing_critical_fields_rate": round(self.missing_critical_fields_rate, 4),
            "false_auto_approve_rate": round(self.false_auto_approve_rate, 4),
            "supplier_name_accuracy": round(self.supplier_name_accuracy, 4),
            "critical_field_accuracy": round(self.critical_field_accuracy, 4),
            "decision_accuracy": round(self.decision_accuracy, 4),
            "avg_cost_per_doc": round(self.avg_cost_per_doc, 6),
            "p95_latency_ms": round(self.p95_latency_ms, 1),
            "baseline_false_auto_approve_rate": round(self.baseline_false_auto_approve_rate, 4),
        }


def _load_fixtures(dataset_root: Path) -> list[dict]:
    fixtures = []
    import contextlib

    for json_file in sorted(dataset_root.rglob("*.json")):
        with contextlib.suppress(Exception):
            fixtures.append(json.loads(json_file.read_text()))
    return fixtures


def _field_matches(extracted: FieldValue | None, expected: object) -> bool:
    if expected is None:
        return extracted is None or extracted.value is None
    if extracted is None or extracted.value is None:
        return False
    # Numeric: allow 1% tolerance
    if isinstance(expected, float | int):
        try:
            return abs(float(extracted.value) - float(expected)) / (float(expected) + 1e-9) < 0.01
        except (ValueError, TypeError):
            return False
    return str(extracted.value).strip().lower() == str(expected).strip().lower()


async def _run_fixture(fixture: dict, config: EvalConfig) -> FixtureResult:
    """Run extraction + validation + policy on one fixture and compare to expected."""
    start = time.monotonic()
    doc_text = fixture["document_text"]
    expected = fixture["expected"]
    fixture_id = fixture["id"]
    slice_name = fixture["slice"]

    # Run extraction under the candidate version's config (injection_suspected
    # propagated for accurate eval of the adversarial slice).
    fields, trace, _, injection_suspected = await run_extraction(
        case_id=fixture_id,
        trace_id=fixture_id,
        document_text=doc_text,
        system_override=config.system_text,
        model=config.model,
        temperature=config.temperature,
        top_p=config.top_p,
        max_tokens=config.max_tokens,
        k=config.k,
    )

    latency_ms = (time.monotonic() - start) * 1000

    # Validate — inject valid cost-center codes from the fixture's hints (if any),
    # so the cost_center_invalid slice can exercise the blocking rule.
    valid_ccs = expected.get("valid_cost_centers")
    val_ctx = ValidationContext(
        valid_cost_centers=frozenset(valid_ccs) if valid_ccs is not None else None
    )
    _rules, has_block = run_validations(fields, val_ctx)

    # Policy (no supplier registry or PO in eval; use expected hints if available)
    supplier_registered = bool(expected.get("supplier_registered", False))
    po_total = expected.get("po_total", None)
    amount_limit = expected.get("amount_limit", 5000.0)
    justification_present = bool(expected.get("justification_present", False))
    _, risk_score, requires_human = run_policy(
        fields=fields,
        has_blocking_failure=has_block,
        supplier_registered=supplier_registered,
        po_total=po_total,
        amount_limit=amount_limit,
        justification_present=justification_present,
    )

    confidence = fields.overall_confidence()

    # Decision — uses the same function as the pipeline worker.
    # This ensures the scorecard measures what production actually runs.
    decision_enum, _reason, _branches, _just = decide(
        fields, has_block, risk_score, requires_human, injection_suspected
    )
    actual_decision = decision_enum.value

    # Field accuracy
    field_acc = {}
    for fname in CRITICAL_FIELDS:
        extracted_fv: FieldValue | None = getattr(fields, fname, None)
        field_acc[fname] = _field_matches(extracted_fv, expected.get(fname))

    expected_decision = expected.get("expected_decision", "human_review")
    is_false_aa = actual_decision == "auto_approve" and expected_decision != "auto_approve"
    sn_match = _field_matches(fields.supplier_name, expected.get("supplier_name"))

    return FixtureResult(
        fixture_id=fixture_id,
        slice_name=slice_name,
        expected_decision=expected_decision,
        actual_decision=actual_decision,
        field_accuracy=field_acc,
        overall_confidence=confidence,
        latency_ms=latency_ms,
        cost_usd=trace.cost_usd,
        model=trace.model,
        prompt_version_id=trace.prompt_version_id,
        is_false_auto_approve=is_false_aa,
        supplier_name_matched=sn_match,
    )


async def run_eval(
    dataset_root: Path | None = None,
    prompt_version_id: str = "dev",
    config: EvalConfig | None = None,
) -> Scorecard:
    """Run all fixtures and compute a Scorecard.

    `config` carries the candidate version's generation config so the scorecard is
    faithful to that version. When None, the historic registry/default
    behaviour is used.
    """
    root = dataset_root or _DATASET_ROOT
    cfg = config or EvalConfig()
    fixtures = _load_fixtures(root)
    if not fixtures:
        raise FileNotFoundError(f"No fixture JSON files found under {root}")

    results = await asyncio.gather(*[_run_fixture(f, cfg) for f in fixtures])

    n = len(results)
    slices: dict[str, int] = {}
    for r in results:
        slices[r.slice_name] = slices.get(r.slice_name, 0) + 1

    # Per-field accuracy
    field_acc_totals: dict[str, int] = dict.fromkeys(CRITICAL_FIELDS, 0)
    for r in results:
        for fname, ok in r.field_accuracy.items():
            if ok:
                field_acc_totals[fname] += 1
    field_accuracy = {f: field_acc_totals[f] / n for f in CRITICAL_FIELDS}

    exact_acc = sum(all(r.field_accuracy.values()) for r in results) / n
    missing_critical = (
        sum(1 for r in results if not any(r.field_accuracy[f] for f in CRITICAL_FIELDS)) / n
    )
    false_aa_rate = sum(r.is_false_auto_approve for r in results) / n
    sn_acc = sum(r.supplier_name_matched for r in results) / n
    critical_field_acc = sum(field_accuracy[f] for f in _DOMAIN_CRITICAL) / len(_DOMAIN_CRITICAL)
    decision_acc = sum(r.actual_decision == r.expected_decision for r in results) / n
    avg_cost = sum(r.cost_usd for r in results) / n

    latencies = sorted(r.latency_ms for r in results)
    p95_idx = int(0.95 * len(latencies))
    p95_lat = latencies[min(p95_idx, len(latencies) - 1)]

    pv_id = results[0].prompt_version_id if results else prompt_version_id

    return Scorecard(
        prompt_version_id=pv_id,
        total_fixtures=n,
        slices=slices,
        field_accuracy=field_accuracy,
        exact_field_accuracy=exact_acc,
        missing_critical_fields_rate=missing_critical,
        false_auto_approve_rate=false_aa_rate,
        supplier_name_accuracy=sn_acc,
        critical_field_accuracy=critical_field_acc,
        decision_accuracy=decision_acc,
        avg_cost_per_doc=avg_cost,
        p95_latency_ms=p95_lat,
    )
