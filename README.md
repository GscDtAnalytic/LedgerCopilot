# LedgerCopilot

**AI operations platform for financial document workflows.**

LedgerCopilot ingests financial documents (NF-e/invoice, boleto, payment receipt) across
multiple channels and turns them into **traceable operational decisions**:
`classify → extract → validate → reconcile → apply policy → decide`
(`auto_approve` | `human_review` | `reject`) — always with a complete audit trail and selective
human-in-the-loop (HITL) review.

The value is not "reading documents". It is **safely automating** the rework that today is manual,
while keeping a record of who did what, when, and why — measurable and promotable across versions
like serious software.

> Project guide for contributors and agents: **[``]** (authoritative).
> AI-layer prompt design: **[``](./)**.

## Non-negotiable principles

1. **Audit is the backbone, not a feature** — every case state transition writes an immutable `audit_event`.
2. **Determinism before LLM** — validation, dedup, CNPJ checks, totals and policy are pure code.
3. **HITL prefers to escalate over guessing** — when in doubt, `human_review`.
4. **A document is untrusted data** — its content never becomes an instruction to the LLM.
5. **No invented values** — illegible/missing field = `null` + confidence `0.0`.

See `` §2 for the full list.

## Monorepo layout

```
apps/web/          Next.js (App Router): inbox, case detail, exceptions, version compare, monitoring
apps/api/          FastAPI: auth, cases, uploads, prompts/policies, endpoints
workers/           arq jobs: the document processing pipeline
packages/domain/   Pydantic entities + state machine + rules (pure, no I/O)
packages/validation/      deterministic validation engine
packages/policy/          policy engine + versioning
packages/reconciliation/  reconciliation engine
packages/agents/          Intake/Extraction/Validation/Policy/Reconciliation/Review/Audit
packages/ai_gateway/      model abstraction, prompt registry, tracing, fallback
eval/              dataset with slices, metrics, scorecards, gating
migrations/        Alembic
infra/             IaC + docker-compose for local dev
```

`packages/{domain,validation,policy,reconciliation}` are **pure and testable without DB or network**.
I/O lives in `apps/` and `workers/`.

## Getting started

Requirements: **Python 3.12+**, **Node 20+**, **uv**, **pnpm**, **Docker**.

```bash
# pnpm (via corepack, if not already installed)
corepack enable pnpm

# Python + frontend deps
uv sync
pnpm install

# Local infra (postgres + redis + storage) and migrations
docker compose -f infra/docker-compose.dev.yml up -d
uv run alembic upgrade head
```

### Dev

```bash
uv run uvicorn apps.api.main:app --reload     # API at :8000
uv run arq workers.pipeline.WorkerSettings    # pipeline worker
pnpm --filter web dev                         # frontend at :3000
```

### Quality gates (run before considering a task done)

```bash
make check      # ruff + mypy + pytest + web lint/typecheck
```

or individually — see the [`Makefile`](./Makefile) and `` §5.

## Roadmap

Built in phases:

1. ✅ **Core MVP** — upload, classification, extraction, basic validations, case detail, review queue, audit events.
2. ✅ **Workflow intelligence** — policy engine, reconciliation, per-field confidence, approve/reject/edit, agent explanations, inbox with filters/SLA.
3. ✅ **LLMOps layer** — detailed tracing, prompt registry, benchmark dataset, version compare, scorecards, regression gating.
4. **Enterprise polish** — RBAC, per-org inbox, email/API integrations, executive dashboards, audit package export, long-running workflows (Temporal).

## Blocked promotion demo (Phase 3 ✅)

`eval.gate` enforces  promotion rules and exits non-zero on any violation.
Here is a real run showing a candidate version being blocked:

```bash
$ uv run python -m eval.gate \
    --candidate eval/scorecards/candidate_v2_bad.json \
    --baseline  eval/scorecards/production.json

=== eval.gate: extraction-v2-experimental vs extraction-v1 ===

  PROMOTION BLOCKED for extraction-v2-experimental:

  ✗ false_auto_approve_rate: 0.025 > 0.000+0.01
  ✗ supplier_name_accuracy: 0.625 < 0.97
  ✗ decision_accuracy: 0.625 < 0.700 (baseline-0.05)

Exit code: 1
```

And the baseline promoting cleanly:

```bash
$ uv run python -m eval.gate \
    --candidate eval/scorecards/production.json \
    --baseline  eval/scorecards/production.json

=== eval.gate: extraction-v1 vs extraction-v1 ===

  ✓ All rules passed — extraction-v1 may be promoted.

Exit code: 0
```

The same rules are enforced by `POST /api/v1/prompts/{id}/promote` when targeting the
`production` alias, so CI and the API share a single source of truth.

## Eval commands

```bash
# Run eval against all 8 mandatory slices and write a scorecard
uv run python -m eval.run --prompt-version dev --out eval/scorecards/candidate.json

# Gate: compare candidate to production baseline (exit 1 = blocked)
uv run python -m eval.gate \
    --candidate eval/scorecards/candidate.json \
    --baseline  eval/scorecards/production.json
```

## UI/UX philosophy

The UI adapts to the user, disappears when not needed (calm technology), and speaks the user's
language (multimodal, accessible, contextual). Inclusive design is the foundation (WCAG 2.2 AA
floor), backed by a living design system, purposeful microinteractions, a conversational/command
layer, and XR as a documented long-term north star (web-first today). See `` §13.

> Status: **Phases 1–3 complete**. Phase 4 (Enterprise polish) is next.
