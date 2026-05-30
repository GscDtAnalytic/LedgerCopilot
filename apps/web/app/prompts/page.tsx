/**
 * Prompt versions page — list all versions with their scorecard metrics.
 *
 * The key Phase 3 surface: shows which versions are safe to promote and which
 * are blocked. Color is paired with text (§13.1: never color alone).
 */

import Link from "next/link";
import { api, type PromptVersion } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { NewPromptForm } from "@/components/NewPromptForm";

export const dynamic = "force-dynamic";

const ALIAS_COLORS: Record<string, string> = {
  production: "text-success",
  staging: "text-warning",
  dev: "text-muted",
};

function Metric({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-muted">{label}</p>
      <p className={`truncate font-mono text-sm font-medium ${warn ? "text-danger" : ""}`}>
        {value}
      </p>
    </div>
  );
}

function ScorecardRow({ pv }: { pv: PromptVersion }) {
  const sc = pv.scorecard as Record<string, number | string | object> | null;
  const far = typeof sc?.false_auto_approve_rate === "number" ? sc.false_auto_approve_rate : null;
  const sna = typeof sc?.supplier_name_accuracy === "number" ? sc.supplier_name_accuracy : null;
  const da = typeof sc?.decision_accuracy === "number" ? sc.decision_accuracy : null;
  const cost = typeof sc?.avg_cost_per_doc === "number" ? sc.avg_cost_per_doc : null;

  const farWarn = far !== null && far > 0.01;
  const snaWarn = sna !== null && sna < 0.97;

  return (
    <div className="grid grid-cols-[1fr_auto_auto_auto_auto_auto_auto] items-start gap-4 border-b border-border px-4 py-4 text-sm last:border-0">
      {/* Name + alias */}
      <div className="min-w-0">
        <Link
          href={`/prompts/${pv.id}`}
          className="font-medium hover:underline truncate block"
        >
          {pv.name}
        </Link>
        <p className="text-xs text-muted font-mono mt-0.5">{pv.id.slice(0, 12)}…</p>
      </div>

      <div>
        {pv.alias ? (
          <span className={`text-xs font-medium uppercase ${ALIAS_COLORS[pv.alias] ?? "text-muted"}`}>
            {pv.alias}
          </span>
        ) : (
          <span className="text-xs text-muted">—</span>
        )}
      </div>

      {sc ? (
        <>
          <Metric label="false_aa%" value={far !== null ? `${(far * 100).toFixed(1)}%` : "—"} warn={farWarn} />
          <Metric label="supplier_acc" value={sna !== null ? `${(sna * 100).toFixed(0)}%` : "—"} warn={snaWarn} />
          <Metric label="decision_acc" value={da !== null ? `${(da * 100).toFixed(0)}%` : "—"} />
          <Metric label="cost/doc" value={cost !== null ? `$${cost.toFixed(6)}` : "—"} />
        </>
      ) : (
        <p className="col-span-4 text-xs text-muted italic">no scorecard — run eval first</p>
      )}

      <p className="text-xs text-muted whitespace-nowrap">{formatDate(pv.created_at)}</p>
    </div>
  );
}

export default async function PromptsPage() {
  const versions = await api.prompts.list().catch(() => [] as PromptVersion[]);

  return (
    <main id="main" className="mx-auto max-w-5xl px-6 py-12">
      <div className="mb-8 flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Prompt versions</h1>
          <p className="mt-1 text-sm text-muted">
            {versions.length} versions · scorecard metrics from eval.run
          </p>
        </div>
        <Link
          href="/monitoring"
          className="text-sm text-muted transition-colors hover:text-foreground"
        >
          ← Monitoring
        </Link>
      </div>

      {/* Gate legend */}
      <div className="mb-6 rounded-md border border-border bg-surface px-4 py-3 text-xs text-muted">
        Promotion gate:
        <span className="ml-2 text-danger font-medium">false_auto_approve &gt; baseline+1%</span>
        <span className="mx-1">·</span>
        <span className="text-danger font-medium">supplier_acc &lt; 97%</span>
        <span className="mx-1">·</span>
        cost/doc &gt; baseline+20%
        <span className="mx-1">·</span>
        decision_acc drops &gt; 5pp
      </div>

      {/* Author surface — renders only for admins (gated inside the component). */}
      <div className="mb-6">
        <NewPromptForm />
      </div>

      {versions.length === 0 ? (
        <div className="rounded-lg border border-border bg-surface px-6 py-16 text-center">
          <p className="text-muted">No prompt versions in the DB yet.</p>
          <p className="mt-2 text-xs text-muted">
            Admins can author one with “+ New version” above, or{" "}
            <code className="rounded bg-background px-1.5 py-0.5">POST /api/v1/prompts</code>.
          </p>
        </div>
      ) : (
        <div
          className="overflow-hidden rounded-lg border border-border"
          role="table"
          aria-label="Prompt versions"
        >
          {/* Column headers */}
          <div
            role="row"
            className="grid grid-cols-[1fr_auto_auto_auto_auto_auto_auto] gap-4 border-b border-border bg-surface px-4 py-3 text-xs font-medium uppercase tracking-wider text-muted"
          >
            <span role="columnheader">Name</span>
            <span role="columnheader">Alias</span>
            <span role="columnheader">false_aa%</span>
            <span role="columnheader">supplier_acc</span>
            <span role="columnheader">decision_acc</span>
            <span role="columnheader">cost/doc</span>
            <span role="columnheader">Created</span>
          </div>

          {versions.map((pv) => (
            <ScorecardRow key={pv.id} pv={pv} />
          ))}
        </div>
      )}
    </main>
  );
}
