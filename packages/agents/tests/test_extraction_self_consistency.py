"""Self-Consistency reconciliation across configurable k.

k is now per-version configurable. The reconcile step must not destroy data when
k=1 (a single sample has no agreement signal to vote on); regression guard for the
bug where k=1 nulled every critical field. k>=2 voting behaviour is unchanged.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from packages.agents.extraction import run_extraction
from packages.ai_gateway.tracer import ModelTrace
from packages.domain.entities import ExtractionOutput, FieldValue


def _fields() -> ExtractionOutput:
    return ExtractionOutput(
        supplier_name=FieldValue(value="ACME Ltda", confidence=0.9, source="ocr"),
        tax_id_cnpj=FieldValue(value="12.345.678/0001-99", confidence=0.95, source="ocr"),
        total_amount=FieldValue(value=1000.0, confidence=0.88, source="ocr"),
        document_number=FieldValue(value="NF-001", confidence=0.85, source="ocr"),
    )


@pytest.mark.asyncio
async def test_k1_standard_mode_keeps_critical_fields():
    calls: list[dict] = []

    async def fake_gateway(**kwargs: Any):
        calls.append(kwargs)
        trace = ModelTrace(
            case_id="c1", trace_id="t1", prompt_version_id="v", model="stub", stage="extraction"
        )
        return _fields(), trace

    with patch("packages.agents.extraction.gateway_call", side_effect=fake_gateway):
        merged, _trace, low_agreement, _inj = await run_extraction(
            case_id="c1", trace_id="t1", document_text="x", k=1
        )

    assert len(calls) == 1, "k=1 must make a single call"
    # The single sample is accepted as-is — critical fields are NOT nulled.
    assert merged.total_amount is not None and merged.total_amount.value == 1000.0
    assert merged.tax_id_cnpj is not None and merged.tax_id_cnpj.value == "12.345.678/0001-99"
    assert merged.document_number is not None and merged.document_number.value == "NF-001"
    assert low_agreement == []


@pytest.mark.asyncio
async def test_k3_unanimous_agreement_unchanged():
    async def fake_gateway(**kwargs: Any):
        trace = ModelTrace(
            case_id="c1", trace_id="t1", prompt_version_id="v", model="stub", stage="extraction"
        )
        return _fields(), trace

    with patch("packages.agents.extraction.gateway_call", side_effect=fake_gateway):
        merged, _trace, low_agreement, _inj = await run_extraction(
            case_id="c1", trace_id="t1", document_text="x", k=3
        )

    assert merged.total_amount is not None and merged.total_amount.value == 1000.0
    assert low_agreement == []
