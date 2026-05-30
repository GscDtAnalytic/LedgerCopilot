"""Tests for the Dual LLM / quarantine extraction mode.

Validates the security invariants without needing an ANTHROPIC_API_KEY:
  1. Quarantine mode uses the "quarantine" prompt alias, never "dev".
  2. system_override from DB is blocked in quarantine mode (never forwarded).
  3. k=1 in quarantine mode (single call, deterministic).
  4. Standard mode still uses k=3 + temperature=1.0.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from packages.agents.extraction import run_extraction
from packages.domain.entities import ExtractionOutput, FieldValue


def _make_fields(**overrides: Any) -> ExtractionOutput:
    defaults = {
        "supplier_name": FieldValue(value="ACME Ltda", confidence=0.9, source="ocr"),
        "tax_id_cnpj": FieldValue(value="12.345.678/0001-99", confidence=0.95, source="ocr"),
        "total_amount": FieldValue(value=1000.0, confidence=0.88, source="ocr"),
        "currency": FieldValue(value="BRL", confidence=0.99, source="ocr"),
        "document_number": FieldValue(value="NF-001", confidence=0.85, source="ocr"),
    }
    return ExtractionOutput(**{**defaults, **overrides})


@pytest.mark.asyncio
async def test_quarantine_mode_uses_quarantine_alias():
    """When quarantine_mode=True, gateway_call must receive prompt_alias='quarantine'."""
    calls: list[dict] = []

    async def fake_gateway(**kwargs: Any):
        calls.append(kwargs)
        from packages.ai_gateway.tracer import ModelTrace

        trace = ModelTrace(
            case_id="c1",
            trace_id="t1",
            prompt_version_id="quarantine-extraction-v1",
            model="stub",
            stage="extraction-quarantine",
        )
        trace.finish(0, 0, 0)
        return _make_fields(), trace

    with patch("packages.agents.extraction.gateway_call", side_effect=fake_gateway):
        await run_extraction(
            case_id="c1",
            trace_id="t1",
            document_text="Nota Fiscal 12.345.678/0001-99 Total: R$ 1.000,00",
            system_override="DB override — should be blocked",
            quarantine_mode=True,
        )

    assert len(calls) == 1, "quarantine mode must use k=1"
    assert calls[0]["prompt_alias"] == "quarantine"


@pytest.mark.asyncio
async def test_quarantine_mode_blocks_system_override():
    """system_override must be None (blocked) in quarantine mode."""
    calls: list[dict] = []

    async def fake_gateway(**kwargs: Any):
        calls.append(kwargs)
        from packages.ai_gateway.tracer import ModelTrace

        trace = ModelTrace(
            case_id="c2",
            trace_id="t2",
            prompt_version_id="quarantine-extraction-v1",
            model="stub",
            stage="extraction-quarantine",
        )
        trace.finish(0, 0, 0)
        return _make_fields(), trace

    with patch("packages.agents.extraction.gateway_call", side_effect=fake_gateway):
        await run_extraction(
            case_id="c2",
            trace_id="t2",
            document_text="Invoice total 500 USD",
            system_override="COMPROMISED PROMPT — must not reach LLM",
            quarantine_mode=True,
        )

    assert calls[0]["system_override"] is None, (
        "system_override must be blocked in quarantine mode — "
        "the quarantine prompt cannot be weakened via DB admin"
    )


@pytest.mark.asyncio
async def test_quarantine_mode_uses_k1():
    """Quarantine mode must make exactly 1 gateway call."""
    call_count = 0

    async def fake_gateway(**kwargs: Any):
        nonlocal call_count
        call_count += 1
        from packages.ai_gateway.tracer import ModelTrace

        trace = ModelTrace(
            case_id="c3",
            trace_id="t3",
            prompt_version_id="q-v1",
            model="stub",
            stage="extraction-quarantine",
        )
        trace.finish(0, 0, 0)
        return _make_fields(), trace

    with patch("packages.agents.extraction.gateway_call", side_effect=fake_gateway):
        await run_extraction(
            case_id="c3",
            trace_id="t3",
            document_text="doc",
            quarantine_mode=True,
        )

    assert call_count == 1


@pytest.mark.asyncio
async def test_standard_mode_uses_k3():
    """Standard mode must make k=3 gateway calls (Self-Consistency)."""
    call_count = 0

    async def fake_gateway(**kwargs: Any):
        nonlocal call_count
        call_count += 1
        from packages.ai_gateway.tracer import ModelTrace

        trace = ModelTrace(
            case_id="c4",
            trace_id="t4",
            prompt_version_id="extraction-v1",
            model="stub",
            stage="extraction",
        )
        trace.finish(0, 0, 0)
        return _make_fields(), trace

    with patch("packages.agents.extraction.gateway_call", side_effect=fake_gateway):
        await run_extraction(
            case_id="c4",
            trace_id="t4",
            document_text="doc",
            quarantine_mode=False,
        )

    assert call_count == 3, "standard mode uses SC k=3"


@pytest.mark.asyncio
async def test_quarantine_mode_forwards_quarantine_model():
    """quarantine_model arg must be forwarded to gateway_call."""
    calls: list[dict] = []

    async def fake_gateway(**kwargs: Any):
        calls.append(kwargs)
        from packages.ai_gateway.tracer import ModelTrace

        trace = ModelTrace(
            case_id="c5",
            trace_id="t5",
            prompt_version_id="q-v1",
            model="claude-haiku-4-5-20251001",
            stage="extraction-quarantine",
        )
        trace.finish(0, 0, 0)
        return _make_fields(), trace

    with patch("packages.agents.extraction.gateway_call", side_effect=fake_gateway):
        await run_extraction(
            case_id="c5",
            trace_id="t5",
            document_text="doc",
            quarantine_mode=True,
            quarantine_model="claude-haiku-4-5-20251001",
        )

    assert calls[0]["model"] == "claude-haiku-4-5-20251001"


@pytest.mark.asyncio
async def test_standard_mode_passes_system_override():
    """In standard mode, system_override must reach gateway_call unchanged."""
    calls: list[dict] = []

    async def fake_gateway(**kwargs: Any):
        calls.append(kwargs)
        from packages.ai_gateway.tracer import ModelTrace

        trace = ModelTrace(
            case_id="c6",
            trace_id="t6",
            prompt_version_id="extraction-v1",
            model="stub",
            stage="extraction",
        )
        trace.finish(0, 0, 0)
        return _make_fields(), trace

    override = "Custom production prompt from DB"
    with patch("packages.agents.extraction.gateway_call", side_effect=fake_gateway):
        await run_extraction(
            case_id="c6",
            trace_id="t6",
            document_text="doc",
            system_override=override,
            quarantine_mode=False,
        )

    assert calls[0]["system_override"] == override
