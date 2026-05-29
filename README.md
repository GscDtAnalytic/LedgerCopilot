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
> Technical backlog and known gaps: **[`RUNBOOK.md`](./RUNBOOK.md)**.

## Non-negotiable principles

1. **Audit is the backbone, not a feature** — every case state transition writes an immutable `audit_event`.
2. **Determinism before LLM** — validation, dedup, CNPJ checks, totals and policy are pure code.
3. **HITL prefers to escalate over guessing** — when in doubt, `human_review`.
4. **A document is untrusted data** — its content is sanitised before LLM injection.
5. **No invented values** — illegible/missing field = `null` + confidence `0.0`.

See `` §2 for the full list.

## Monorepo layout

```
apps/web/          Next.js (App Router): inbox, case detail, exceptions, version compare, monitoring
apps/api/          FastAPI: auth, cases, uploads, prompts/policies, endpoints
workers/           arq jobs: the document processing pipeline
packages/domain/   Pydantic entities + state machine + rules + decision logic (pure, no I/O)
packages/validation/      deterministic validation engine (CNPJ check digits, date order, ...)
packages/policy/          policy engine + versioning
packages/reconciliation/  reconciliation engine
packages/agents/          Extraction agent + stub extractor
packages/ai_gateway/      model abstraction, prompt registry, tracing, fallback, sanitization
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

## Phase status

| Phase | What | Status |
|---|---|---|
| **1 — Core MVP** | Upload, classification, extraction, validations, case detail, review queue, audit events | ✅ Complete |
| **2 — Workflow intelligence** | Policy engine ✅, per-field confidence ✅, approve/reject ✅ · Edit flow ⚠️ (re-enqueue wired, fields in request body — needs pipeline test) · Reconciliation ⚠️ | ⚠️ Partial |
| **3 — LLMOps layer** | Eval framework ✅, gate CLI ✅, scorecards ✅ · Prompt registry now wired to runtime ✅ · Tracing captures tokens/latency/cost ✅; prompt/completion capture planned · Dataset: 1 fixture/slice (expand for statistical significance) | ⚠️ Partial |
| **4 — Enterprise polish** | JWT auth ✅, RBAC enforced on all endpoints ✅, org-scoped queries ✅, dashboard ✅, audit export ✅ (approver+admin only), email intake ✅ | ✅ Complete |

See [`RUNBOOK.md`](./RUNBOOK.md) for the full backlog, priorities, and acceptance criteria.

## Demo — JWT auth and RBAC

Three demo users are seeded at API startup (password: `demo123`):

| Email | Role | Permissions |
|---|---|---|
| `analyst@demo.com` | analyst | Read cases, submit edit reviews |
| `approver@demo.com` | approver | All analyst + approve/reject + audit export |
| `admin@demo.com` | admin | Full access + create/promote prompts + dashboard |

```bash
# Login and get a JWT
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@demo.com","password":"demo123"}' | jq -r .access_token)

# Upload a document (auth required)
curl -s -X POST http://localhost:8000/api/v1/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/invoice.pdf"

# List cases (org-scoped)
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/cases

# Executive dashboard
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/dashboard

# Full audit package (approver/admin only)
curl -OJ -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/cases/{case_id}/audit-export

# Email intake
curl -s -X POST http://localhost:8000/api/v1/intake/email \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"from_address":"supplier@acme.com","subject":"Invoice #2024-001","body_text":"..."}'
```

## Blocked promotion demo (eval.gate)

`eval.gate` enforces ` promotion rules and exits non-zero on any violation.

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

The same rules are enforced by `POST /api/v1/prompts/{id}/promote` (admin only) when targeting
the `production` alias. Promoting to production wires the new `system_text` directly into the
pipeline worker — the registry is no longer in-process only.

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
