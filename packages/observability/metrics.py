"""Central Prometheus metric definitions for LedgerCopilot.

Imported by both the API and the arq worker. When PROMETHEUS_MULTIPROC_DIR is
set, prometheus_client writes metric state to shared files; the /metrics endpoint
aggregates across all processes via MultiProcessCollector.

Hierarchy follows wiki conceitos/monitoring-vs-observability — negócio → LLMOps → infra.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

# ── 1. Business metrics (negócio) ─────────────────────────────────────────────

cases_received_total = Counter(
    "ledger_cases_received_total",
    "Documents that entered the pipeline",
    ["org_id"],
)

cases_decided_total = Counter(
    "ledger_cases_decided_total",
    "Cases that reached a terminal decision",
    ["decision", "org_id"],
)
# decision label values: auto_approved | human_review | rejected

human_reviews_completed_total = Counter(
    "ledger_human_reviews_completed_total",
    "Human reviewer actions (approve / reject / edit)",
    ["action", "org_id"],
)
# action label values: approve | reject | edit
# human_review_rate = sum(human_reviews_completed) / sum(cases_decided)

# ── 2. LLMOps metrics ──────────────────────────────────────────────────────────

llm_latency_ms = Histogram(
    "ledger_llm_latency_ms",
    "LLM gateway call latency (ms) — use histogram_quantile for p50/p95/p99",
    ["stage", "model"],
    buckets=[100, 250, 500, 1_000, 2_000, 5_000, 10_000],
)

llm_cost_usd_total = Counter(
    "ledger_llm_cost_usd_total",
    "Cumulative LLM cost (USD) — divide by cases_received for cost/doc",
    ["stage", "model"],
)

llm_tokens_total = Counter(
    "ledger_llm_tokens_total",
    "LLM tokens consumed",
    ["stage", "model", "token_type"],
)
# token_type label values: input | output

# ── 3. Pipeline / infra metrics ────────────────────────────────────────────────

pipeline_stage_duration_ms = Histogram(
    "ledger_pipeline_stage_duration_ms",
    "End-to-end wall-clock duration of a pipeline stage (ms)",
    ["stage"],
    buckets=[10, 50, 100, 250, 500, 1_000, 2_500, 5_000, 10_000],
)

pipeline_errors_total = Counter(
    "ledger_pipeline_errors_total",
    "Unhandled errors per pipeline stage",
    ["stage", "error_type"],
)

injection_suspected_total = Counter(
    "ledger_injection_suspected_total",
    "Documents flagged for potential prompt injection",
)

# ── 4. HITL / Temporal metrics ────────────────────────────────────

hitl_workflows_started_total = Counter(
    "ledger_hitl_workflows_started_total",
    "Temporal HITL workflows started (cases routed to human review)",
)

hitl_workflows_completed_total = Counter(
    "ledger_hitl_workflows_completed_total",
    "HITL workflows resolved (signal received before SLA)",
    ["action"],
)
# action label: approve | reject | edit

hitl_sla_expirations_total = Counter(
    "ledger_hitl_sla_expirations_total",
    "HITL workflows where SLA expired before reviewer acted",
)
