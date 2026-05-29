"""AI Gateway: model abstraction, prompt registry, tracing, fallback.

Every model call in the platform goes through here. The gateway:
- abstracts providers (Anthropic/OpenAI) behind one interface with model fallback;
- resolves prompts from the versioned registry by ``prompt_version_id`` — prompts
  never live inline in code; the canonical content is in
  ````;
- captures a trace for each call (prompt, completion, tool calls, tokens, latency,
  model, stage, cost);
- always returns output that the caller validates with a Pydantic model before use
  — never raw JSON from the model.
"""
