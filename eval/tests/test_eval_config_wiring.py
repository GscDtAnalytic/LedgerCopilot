"""run_eval forwards the candidate version's config into extraction.

Before this change, eval ran every fixture through registry defaults and ignored
the version's system_text/temperature/k — so a version's scorecard did not reflect
the version. We assert the config is threaded through to run_extraction. This is
deterministic (it patches run_extraction) and so does not depend on a live API key,
unlike asserting that two configs produce different outputs.
"""

from __future__ import annotations

import eval.runner as runner
from eval.runner import EvalConfig, run_eval
from packages.ai_gateway.tracer import ModelTrace
from packages.domain.entities import ExtractionOutput


async def test_run_eval_threads_config_into_extraction(monkeypatch, tmp_path) -> None:
    seen: list[dict] = []

    async def fake_run_extraction(**kwargs):
        seen.append(kwargs)
        trace = ModelTrace(
            case_id=kwargs["case_id"],
            trace_id=kwargs["trace_id"],
            prompt_version_id="extraction-test",
            model=kwargs.get("model") or "stub",
            stage="extraction",
        )
        return ExtractionOutput(), trace, [], False

    monkeypatch.setattr(runner, "run_extraction", fake_run_extraction)

    # Minimal one-fixture dataset.
    (tmp_path / "f1.json").write_text(
        '{"id": "f1", "slice": "clean_invoice", "document_text": "x",'
        ' "expected": {"expected_decision": "human_review"}}'
    )

    cfg = EvalConfig(
        system_text="CUSTOM SYSTEM",
        model="claude-haiku-4-5-20251001",
        temperature=0.3,
        top_p=0.9,
        max_tokens=256,
        k=5,
    )
    await run_eval(dataset_root=tmp_path, config=cfg)

    assert len(seen) == 1
    call = seen[0]
    assert call["system_override"] == "CUSTOM SYSTEM"
    assert call["model"] == "claude-haiku-4-5-20251001"
    assert call["temperature"] == 0.3
    assert call["top_p"] == 0.9
    assert call["max_tokens"] == 256
    assert call["k"] == 5


async def test_run_eval_defaults_when_no_config(monkeypatch, tmp_path) -> None:
    """No config → historic behaviour (registry prompt, temperature=1.0, k=3)."""
    seen: list[dict] = []

    async def fake_run_extraction(**kwargs):
        seen.append(kwargs)
        trace = ModelTrace(
            case_id=kwargs["case_id"],
            trace_id=kwargs["trace_id"],
            prompt_version_id="extraction-v1",
            model="stub",
            stage="extraction",
        )
        return ExtractionOutput(), trace, [], False

    monkeypatch.setattr(runner, "run_extraction", fake_run_extraction)
    (tmp_path / "f1.json").write_text(
        '{"id": "f1", "slice": "clean_invoice", "document_text": "x",'
        ' "expected": {"expected_decision": "human_review"}}'
    )

    await run_eval(dataset_root=tmp_path)

    call = seen[0]
    assert call["system_override"] is None  # falls back to registry prompt
    assert call["temperature"] == runner.DEFAULT_TEMPERATURE
    assert call["k"] == runner.DEFAULT_K
