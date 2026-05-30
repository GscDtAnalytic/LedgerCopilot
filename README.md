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
| **2 — Workflow intelligence** | Policy engine ✅, per-field confidence ✅, approve/reject ✅ · Edit flow ✅ · Reconciliation ✅ | ✅ Complete |
| **3 — LLMOps layer** | Eval framework ✅, gate CLI ✅, scorecards ✅ · Prompt registry wired to runtime ✅ · Tracing captures tokens/latency/cost + redacted prompt/completion ✅ · Dataset: 1 fixture/slice (expand for statistical significance) | ✅ Complete |
| **4 — Enterprise polish** | JWT auth ✅, RBAC enforced on all endpoints ✅, org-scoped queries ✅, dashboard ✅, audit export ✅ (approver+admin only) · **Ingestion channels**: upload ✅, email ✅, CSV/XLSX ✅, ERP/API ✅, bucket scan ✅ · **Reference data** (suppliers/POs/payments/cost centers) wired into policy + reconciliation ✅ | ✅ Complete |

### Full functional scope

- **Ingestion channels**: manual upload, email webhook (`/intake/email`), CSV/XLSX
  batch (`/intake/csv`, one case per row), ERP/automation JSON (`/intake/erp`), and a bucket scan
  cron that ingests files dropped into storage out-of-band.
- **Extraction fields**: supplier, CNPJ, total, currency, issue/due dates, document number, plus
  **line items**, **cost center** and **category**.
- **Validation** (deterministic): amount sign, CNPJ presence/format/check-digits, date order,
  currency, **sum-of-items vs total**, **cost-center membership** (against the org registry).
- **Policy** (deterministic, versioned): low/medium confidence, unknown supplier, amount-vs-PO
  delta, **amount over auto-approve limit**, **category requires justification**, **urgent payment
  → double check** (`requires_dual_approval`).
- **Reconciliation**: document vs PO, vs payment/ledger, vs history (business-key dedup), plus
  supplier blocklist hard-reject — all against seeded reference data.
- **HITL queue** (5 actions): approve, reject, edit, **request more context** (annotation, no
  status change), **resend to stage** (re-enters the resumable pipeline at `extracted`/`validated`).

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

# Email intake (creates a case AND queues the pipeline)
curl -s -X POST http://localhost:8000/api/v1/intake/email \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"from_address":"supplier@acme.com","subject":"Invoice #2024-001","body_text":"..."}'

# CSV/XLSX intake — one case per data row
curl -s -X POST http://localhost:8000/api/v1/intake/csv \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/invoices.csv"

# ERP / automation intake — structured JSON
curl -s -X POST http://localhost:8000/api/v1/intake/erp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_system":"sap","external_id":"DOC-42","fields":{"fornecedor":"Acme","cnpj":"11.444.777/0001-61","numero":"778231","total":"12000.00"}}'

# HITL: request more context / resend to an earlier stage
curl -s -X POST http://localhost:8000/api/v1/cases/{case_id}/review \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"action":"request_context","note":"Need the matching PO number"}'
curl -s -X POST http://localhost:8000/api/v1/cases/{case_id}/review \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"action":"resend_to_stage","target_stage":"validated"}'
```

The bucket-scan channel runs automatically as an arq cron job (every 5 min) in the worker —
drop a file into the storage directory and a case appears.

## Blocked promotion demo (eval.gate)

`eval.gate` enforces ` promotion rules and exits non-zero on any violation.

```bash
$ uv run python -m eval.gate \
    --candidate eval/scorecards/candidate_v2_bad.json \
    --baseline  eval/scorecards/production.json

=== eval.gate: extraction-v2-experimental vs extraction-v1 ===

  PROMOTION BLOCKED for extraction-v2-experimental:

  ✗ false_auto_approve_rate: 0.025 > 0.000+0.01
  ✗ critical_field_accuracy: 0.000 < 0.85
  ✗ decision_accuracy: 0.625 < 0.700 (baseline-0.05)

Exit code: 1
```

The same rules are enforced by `POST /api/v1/prompts/{id}/promote` (admin only) when targeting
the `production` alias. Promoting to production wires the new `system_text` directly into the
pipeline worker — the registry is no longer in-process only.

## Eval commands

```bash
# Run eval against all slices (8 mandatory + 5 for the new rules) and write a scorecard
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
