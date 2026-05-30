"""AI Gateway client — the only place in the codebase that calls the LLM.

Every model call goes through `gateway_call()`:
  1. Resolves the prompt from the registry (or uses system_override from DB).
  2. Calls Anthropic async or falls back to the stub extractor.
  3. Validates the raw JSON response with the caller-supplied Pydantic model.
  4. Records a trace (tokens, latency, cost).

Never returns raw JSON from the model — callers always get a validated Pydantic
instance, or an exception with a clear message.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from collections.abc import AsyncIterator
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from packages.ai_gateway.redact import redact_pii
from packages.ai_gateway.registry import get_prompt
from packages.ai_gateway.tracer import ModelTrace

T = TypeVar("T", bound=BaseModel)

_DEFAULT_MODEL = os.environ.get("AI_DEFAULT_MODEL", "claude-sonnet-4-6")
_FALLBACK_MODEL = os.environ.get("AI_FALLBACK_MODEL", "claude-haiku-4-5-20251001")

# Lazily initialised — avoids import error when the SDK is not installed.
_anthropic_client: Any = None

# Optional concurrency cap on outbound model calls.
# AI_MAX_CONCURRENCY=0 (default) means unlimited; a positive value bounds in-flight
# requests so a wide fan-out (e.g. eval SC k=3 over many fixtures) stays under the
# provider's rate limit. Created lazily inside the running loop so it binds correctly.
_concurrency_sem: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore | None:
    global _concurrency_sem
    try:
        limit = int(os.environ.get("AI_MAX_CONCURRENCY", "0"))
    except ValueError:
        return None
    if limit <= 0:
        return None
    if _concurrency_sem is None:
        _concurrency_sem = asyncio.Semaphore(limit)
    return _concurrency_sem


@contextlib.asynccontextmanager
async def _gate() -> AsyncIterator[None]:
    """Hold the concurrency semaphore around a single outbound call, if configured.

    Scoped to just the HTTP call (not the fallback recursion) so a limit of 1 cannot
    deadlock: the semaphore is released before any fallback gateway_call re-acquires.
    """
    sem = _get_semaphore()
    if sem is None:
        yield
        return
    async with sem:
        yield


def _get_client() -> Any:
    global _anthropic_client
    if _anthropic_client is not None:
        return _anthropic_client
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    try:
        import anthropic

        # AsyncAnthropic so gateway_call can be awaited concurrently.
        # The k=3 Self-Consistency calls in run_extraction are gathered in parallel;
        # a synchronous client would serialise them and block the event loop.
        _anthropic_client = anthropic.AsyncAnthropic(api_key=api_key)
    except Exception:
        return None
    return _anthropic_client


async def gateway_call(
    *,
    case_id: str,
    trace_id: str,
    prompt_alias: str,
    user_message: str,
    response_model: type[T],
    stage: str,
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    system_override: str | None = None,
) -> tuple[T, ModelTrace]:
    """Call the LLM and return a validated Pydantic instance + trace.

    system_override: when provided (resolved from DB by the pipeline via
    apps/api/services/prompts.get_active_system_text), it takes precedence
    over the in-process registry — this is what makes prompt promotion actually
    affect the running worker.

    Falls back to the stub extractor when ANTHROPIC_API_KEY is not configured,
    so the pipeline can run end-to-end without credentials.
    """
    prompt_version = get_prompt(prompt_alias)
    system_text = system_override if system_override is not None else prompt_version.system
    effective_model = model or _DEFAULT_MODEL

    trace = ModelTrace(
        case_id=case_id,
        trace_id=trace_id,
        prompt_version_id=prompt_version.id,
        model=effective_model,
        stage=stage,
    )

    client = _get_client()
    if client is None:
        return await _stub_response(user_message, response_model, trace, temperature=temperature)

    start = time.monotonic()
    try:
        async with _gate():
            message = await client.messages.create(
                model=effective_model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_text,
                messages=[{"role": "user", "content": user_message}],
            )
        raw = message.content[0].text
        in_tok = message.usage.input_tokens
        out_tok = message.usage.output_tokens
        trace.finish(
            start,
            in_tok,
            out_tok,
            prompt=redact_pii(user_message),
            completion=redact_pii(raw),
        )
    except Exception as exc:
        # Model fallback: try the cheaper model once.
        if effective_model != _FALLBACK_MODEL:
            return await gateway_call(
                case_id=case_id,
                trace_id=trace_id,
                prompt_alias=prompt_alias,
                user_message=user_message,
                response_model=response_model,
                stage=stage,
                model=_FALLBACK_MODEL,
                max_tokens=max_tokens,
                temperature=temperature,
                system_override=system_override,
            )
        raise RuntimeError(f"gateway: all models failed — {exc}") from exc

    # Strip markdown fences if the model wrapped the JSON.
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rstrip("`").strip()

    try:
        data = json.loads(raw)
        return response_model.model_validate(data), trace
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(
            f"gateway: model output failed Pydantic validation ({type(exc).__name__}): {exc}"
        ) from exc


async def _stub_response(
    user_message: str,
    response_model: type[T],
    trace: ModelTrace,
    temperature: float = 0.0,
) -> tuple[T, ModelTrace]:
    """Stub: run the regex extractor and coerce its output to response_model.

    When temperature > 0 (Self-Consistency k=3 path), SC is inert in stub mode
    because the extractor is deterministic — all k runs return identical output.
    A live ANTHROPIC_API_KEY enables real SC with genuine diversity across runs.
    """
    from packages.agents.stub_extractor import extract_from_text

    if temperature > 0:
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "gateway.stub sc=inert model=stub temperature=%.1f "
            "(SC k=3 calls are identical in stub mode — use a real API key for diversity)",
            temperature,
        )

    start = time.monotonic()
    fields = extract_from_text(user_message)
    trace.model = "stub"
    trace.finish(start, 0, 0)

    validated: T = response_model.model_validate(fields.model_dump())
    return validated, trace
