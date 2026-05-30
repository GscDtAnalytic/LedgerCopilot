"""Lightweight trace capture for every model call.

Every call to the gateway records: prompt, completion, tool calls, tokens,
latency, model, stage, cost. Phase 3 persists these to the `model_run` table.
For Phase 2, traces are logged as structured JSON — enough for debugging and
cost awareness without the DB schema yet.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Approximate cost per 1M tokens (USD). Kept simple for Phase 2; Phase 3
# moves to a proper cost table updated from provider pricing.
_COST_PER_MTK: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25},
    "stub": {"input": 0.0, "output": 0.0},
}


@dataclass
class ModelTrace:
    case_id: str
    trace_id: str
    prompt_version_id: str
    model: str
    stage: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    # PII-redacted copies of what was sent/received.
    # Empty string means trace was not captured (stub or pre-finish).
    prompt_redacted: str = ""
    completion_redacted: str = ""
    extra: dict = field(default_factory=dict)

    def finish(
        self,
        start: float,
        input_tokens: int,
        output_tokens: int,
        prompt: str = "",
        completion: str = "",
    ) -> None:
        self.latency_ms = (time.monotonic() - start) * 1000
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.prompt_redacted = prompt
        self.completion_redacted = completion
        rates = _COST_PER_MTK.get(self.model, {"input": 0.0, "output": 0.0})
        self.cost_usd = (
            input_tokens * rates["input"] + output_tokens * rates["output"]
        ) / 1_000_000

        # Prometheus metrics — best-effort, never block the pipeline.
        try:
            from packages.observability.metrics import (
                llm_cost_usd_total,
                llm_latency_ms,
                llm_tokens_total,
            )

            llm_latency_ms.labels(stage=self.stage, model=self.model).observe(self.latency_ms)
            llm_cost_usd_total.labels(stage=self.stage, model=self.model).inc(self.cost_usd)
            llm_tokens_total.labels(stage=self.stage, model=self.model, token_type="input").inc(
                input_tokens
            )
            llm_tokens_total.labels(stage=self.stage, model=self.model, token_type="output").inc(
                output_tokens
            )
        except Exception:
            pass  # observability must never break the pipeline

        logger.info(
            "gateway.trace case=%s stage=%s model=%s prompt=%s "
            "in_tok=%d out_tok=%d lat_ms=%.0f cost_usd=%.6f",
            self.case_id,
            self.stage,
            self.model,
            self.prompt_version_id,
            input_tokens,
            output_tokens,
            self.latency_ms,
            self.cost_usd,
        )
