/**
 * Prompt versions page — list all versions with their scorecard metrics + verdict.
 *
 * The Ready/Blocked status and per-metric warnings come from the API gate verdict
 * (GET /prompts/{id}/gate), which reuses eval.gate against the live production
 * baseline. The list does not re-derive gate thresholds (the old version gated on
 * supplier_name, which is informational —). Color is paired with text/icon
 * (§13.1: never color alone).
 */

import Link from "next/link";
import { api, type GateVerdict, type MetricVerdict, type PromptVersion } from "@/lib/api";
import { formatDate, formatMetricValue, lifecycleStatus } from "@/lib/format";
import { NewPromptForm } from "@/components/NewPromptForm";
import { PromoteButton } from "@/components/PromoteButton";
import { DeletePromptButton } from "@/components/DeletePromptButton";

export const dynamic = "force-dynamic";

const ALIAS_COLORS: Record<string, string> = {
  production: "text-success",
  staging: "text-warning",
  dev: "text-muted",
};

const ALIAS_ROLE: Record<string, string> = {
  production: "baseline",
  staging: "candidate",
  dev: "candidate",
};

function Metric({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-muted">{label}</p>
      <p className={`truncate font-mono text-sm font-medium ${warn ? "text-danger" : ""}`}>{value}</p>
    </div>
  );
}

function ScorecardRow({ pv, verdict }: { pv: PromptVersion; verdict: GateVerdict | null }) {
  const sc = pv.scorecard as Record<string, number | string | object> | null;
  const byKey = new Map<string, MetricVerdict>((verdict?.metrics ?? []).map((m) => [m.key, m]));
  // A metric warns only if it is a gate rule that failed — informational metrics
  // (supplier_name_accuracy) never warn, however low they are.
  const failed = (key: string) => {
    const m = byKey.get(key);
    return m ? m.gated && !m.passed : false;
  };
  const num = (key: string) =>
    typeof sc?.[key] === "number" ? (sc[key] as number) : null;

  const status = lifecycleStatus(pv.alias, !!verdict?.has_scorecard, !!verdict?.passed);

  return (
    <div className="grid grid-cols-[1fr_auto_auto_auto_auto_auto_auto_auto_auto_auto] items-start gap-4 border-b border-border px-4 py-4 text-sm last:border-0">
      {/* Name + alias */}
      <div className="min-w-0">
        <Link href={`/prompts/${pv.id}`} className="font-medium hover:underline truncate block">
          {pv.name}
        </Link>
        <p className="text-xs text-muted font-mono mt-0.5">{pv.id.slice(0, 12)}…</p>
      </div>

      {/* Alias + role label */}
      <div className="min-w-0">
        {pv.alias ? (
          <>
            <span className={`text-xs font-medium uppercase ${ALIAS_COLORS[pv.alias] ?? "text-muted"}`}>
              {pv.alias}
            </span>
            {ALIAS_ROLE[pv.alias] && <p className="text-xs text-muted">{ALIAS_ROLE[pv.alias]}</p>}
          </>
        ) : (
          <span className="text-xs text-muted">—</span>
        )}
      </div>

      {/* Lifecycle status badge (precise: Production / Eligible / Blocked / Draft …) */}
      <div>
        <span
          title={status.label}
          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium capitalize ${status.badge}`}
        >
          <span aria-hidden="true">{status.icon}</span>
          {status.shortLabel}
        </span>
      </div>

      {sc ? (
        <>
          <Metric
            label="false_aa%"
            value={formatMetricValue("false_auto_approve_rate", num("false_auto_approve_rate"))}
            warn={failed("false_auto_approve_rate")}
          />
          <Metric
            label="supplier_acc"
            value={formatMetricValue("supplier_name_accuracy", num("supplier_name_accuracy"))}
          />
          <Metric
            label="decision_acc"
            value={formatMetricValue("decision_accuracy", num("decision_accuracy"))}
            warn={failed("decision_accuracy")}
          />
          <Metric
            label="cost/doc"
            value={formatMetricValue("avg_cost_per_doc", num("avg_cost_per_doc"))}
            warn={failed("avg_cost_per_doc")}
          />
        </>
      ) : (
        <p className="col-span-4 text-xs text-muted italic">no scorecard — run eval first</p>
      )}

      <p className="text-xs text-muted whitespace-nowrap">{formatDate(pv.created_at)}</p>

      <PromoteButton promptId={pv.id} currentAlias={pv.alias} hasScorecard={sc !== null} />
      <DeletePromptButton promptId={pv.id} currentAlias={pv.alias} />
    </div>
  );
}

export default async function PromptsPage() {
  const versions = await api.prompts.list().catch(() => [] as PromptVersion[]);
  // Fetch the real gate verdict per version (server-side, in parallel). N is small.
  const verdicts = await Promise.all(
    versions.map((v) => api.prompts.gate(v.id).catch(() => null)),
  );
  const verdictById = new Map(versions.map((v, i) => [v.id, verdicts[i]]));

  return (
    <main id="main" className="mx-auto max-w-5xl px-6 py-12">
      <div className="mb-6 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Prompt versions</h1>
          <p className="mt-1 text-sm text-muted">
            {versions.length} versions · verdict from eval.gate vs production baseline
          </p>
        </div>
        <Link href="/monitoring" className="text-sm text-muted transition-colors hover:text-foreground">
          ← Monitoring
        </Link>
      </div>

      {/* Gate legend — the four real promotion rules (eval/gate.py). supplier_acc is
          informational, not a gate. */}
      <div className="mb-6 rounded-md border border-border bg-surface px-4 py-3 text-xs text-muted">
        Promotion gate:
        <span className="ml-2 text-danger font-medium">false_auto_approve &gt; baseline+1pp</span>
        <span className="mx-1">·</span>
        <span className="text-danger font-medium">critical_field_acc &lt; 85%</span>
        <span className="mx-1">·</span>
        cost/doc &gt; baseline×1.20
        <span className="mx-1">·</span>
        decision_acc drops &gt; 5pp
      </div>

      {/* The registry is the entity of this page — table first (item 3). */}
      {versions.length === 0 ? (
        <div className="rounded-lg border border-border bg-surface px-6 py-16 text-center">
          <p className="text-muted">No prompt versions in the DB yet.</p>
          <p className="mt-2 text-xs text-muted">
            Admins can author one below, or{" "}
            <code className="rounded bg-background px-1.5 py-0.5">POST /api/v1/prompts</code>.
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border" role="table" aria-label="Prompt versions">
          {/* Column headers */}
          <div
            role="row"
            className="grid grid-cols-[1fr_auto_auto_auto_auto_auto_auto_auto_auto_auto] gap-4 border-b border-border bg-surface px-4 py-3 text-xs font-medium uppercase tracking-wider text-muted"
          >
            <span role="columnheader">Name</span>
            <span role="columnheader">Alias</span>
            <span role="columnheader">Status</span>
            <span role="columnheader">false_aa%</span>
            <span role="columnheader">supplier_acc</span>
            <span role="columnheader">decision_acc</span>
            <span role="columnheader">cost/doc</span>
            <span role="columnheader">Created</span>
            <span role="columnheader">Promote</span>
            <span role="columnheader">Delete</span>
          </div>

          {versions.map((pv) => (
            <ScorecardRow key={pv.id} pv={pv} verdict={verdictById.get(pv.id) ?? null} />
          ))}
        </div>
      )}

      {/* Author surface — subordinate to the registry, expands as a block (item 3).
          Renders only for admins (gated inside the component). */}
      <div className="mt-6">
        <NewPromptForm versions={versions} />
      </div>
    </main>
  );
}
