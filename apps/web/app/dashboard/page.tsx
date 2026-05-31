/**
 * Executive Dashboard — aggregate org metrics for approvers and admins.
 *
 * Server Component: fetches data at render time.
 * Layout: KPI cards → decision breakdown (inline bar chart) → status table.
 * Data-ink: bars, not pies; every value has a unit;
 * color carries meaning (success/warning/danger tokens from design system).
 */

import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

function KpiCard({
  label,
  value,
  unit,
  sub,
}: {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-surface p-5">
      <p className="text-xs font-medium uppercase tracking-wider text-muted">{label}</p>
      <p className="mt-2 text-3xl font-semibold tabular-nums">
        {value}
        {unit && <span className="ml-1 text-sm font-normal text-muted">{unit}</span>}
      </p>
      {sub && <p className="mt-1 text-xs text-muted">{sub}</p>}
    </div>
  );
}

const DECISION_COLORS: Record<string, string> = {
  auto_approve: "bg-success",
  human_review: "bg-warning",
  reject: "bg-danger",
};

function HBar({ pct, decision }: { pct: number; decision: string | null }) {
  const color = DECISION_COLORS[decision ?? ""] ?? "bg-muted";
  return (
    <div className="flex items-center gap-3">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-border">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
          role="presentation"
        />
      </div>
      <span className="w-10 text-right text-xs tabular-nums text-muted">{pct.toFixed(1)}%</span>
    </div>
  );
}

export default async function DashboardPage() {
  const data = await api.dashboard.get().catch(() => null);

  return (
    <main id="main" className="mx-auto max-w-5xl px-6 py-12">
      <div className="mb-8 flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Executive Dashboard</h1>
          <p className="mt-1 text-sm text-muted">Org-level throughput, accuracy and cost</p>
        </div>
        <Link
          href="/monitoring"
          className="text-sm text-muted transition-colors hover:text-foreground"
        >
          LLMOps detail →
        </Link>
      </div>

      {!data ? (
        <div className="rounded-lg border border-border bg-surface p-8 text-center">
          <p className="text-muted">API not reachable — start the server and refresh.</p>
        </div>
      ) : (
        <div className="space-y-10">
          {/* KPI row */}
          <section aria-labelledby="kpi-heading">
            <h2 id="kpi-heading" className="sr-only">
              Key performance indicators
            </h2>
            {(() => {
              const totalDecided = data.decision_breakdown.reduce((s, d) => s + d.count, 0);
              const autoRow = data.decision_breakdown.find((d) => d.decision === "auto_approve");
              const autoApprovalRate =
                totalDecided > 0 && autoRow ? autoRow.count / totalDecided : null;

              return (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  <KpiCard
                    label="Total cases"
                    value={data.total_cases.toLocaleString()}
                    sub={`${data.cases_this_week} this week`}
                  />
                  <KpiCard
                    label="Pending review"
                    value={data.pending_review.toString()}
                    sub="Awaiting human decision"
                  />
                  <KpiCard
                    label="Avg confidence"
                    value={
                      data.avg_confidence !== null
                        ? `${(data.avg_confidence * 100).toFixed(1)}`
                        : "—"
                    }
                    unit={data.avg_confidence !== null ? "%" : undefined}
                    sub="Extraction field avg"
                  />
                  <KpiCard
                    label="Cost / doc"
                    value={data.avg_cost_per_doc_usd.toFixed(5)}
                    unit="USD"
                    sub={`Total: $${data.total_cost_usd.toFixed(4)}`}
                  />
                  <KpiCard
                    label="Auto-approval rate"
                    value={autoApprovalRate !== null ? (autoApprovalRate * 100).toFixed(1) : "—"}
                    unit={autoApprovalRate !== null ? "%" : undefined}
                    sub={autoRow ? `${autoRow.count.toLocaleString()} cases` : "No decisions yet"}
                  />
                  <KpiCard
                    label="Human override rate"
                    value={data.human_override_rate != null ? (data.human_override_rate * 100).toFixed(1) : "—"}
                    unit={data.human_override_rate != null ? "%" : undefined}
                    sub={data.human_override_count != null ? `${data.human_override_count.toLocaleString()} overridden` : "Restart API to load"}
                  />
                </div>
              );
            })()}
          </section>

          {/* Decision breakdown */}
          <section aria-labelledby="decisions-heading">
            <h2
              id="decisions-heading"
              className="mb-4 text-sm font-semibold uppercase tracking-wider"
            >
              Decision breakdown
            </h2>
            {data.decision_breakdown.length === 0 ? (
              <p className="text-sm text-muted">No decisions recorded yet.</p>
            ) : (
              <div className="rounded-lg border border-border bg-surface">
                <table className="w-full text-sm" aria-label="Decision breakdown">
                  <thead>
                    <tr className="border-b border-border text-left text-xs font-medium uppercase tracking-wider text-muted">
                      <th scope="col" className="px-5 py-3 w-40">
                        Decision
                      </th>
                      <th scope="col" className="px-5 py-3 w-20 text-right">
                        Count
                      </th>
                      <th scope="col" className="px-5 py-3">
                        Share
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.decision_breakdown.map((d, i) => (
                      <tr
                        key={d.decision ?? "null"}
                        className={`border-b border-border last:border-0 ${i % 2 !== 0 ? "bg-surface/50" : ""}`}
                      >
                        <td className="px-5 py-3 font-medium capitalize">
                          {(d.decision ?? "undecided").replace(/_/g, " ")}
                        </td>
                        <td className="px-5 py-3 text-right tabular-nums">{d.count}</td>
                        <td className="px-5 py-3">
                          <HBar pct={d.pct} decision={d.decision} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* Status breakdown */}
          <section aria-labelledby="status-heading">
            <h2
              id="status-heading"
              className="mb-4 text-sm font-semibold uppercase tracking-wider"
            >
              Cases by pipeline status
            </h2>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {data.status_breakdown.map((s) => (
                <div
                  key={s.status}
                  className="flex items-center justify-between rounded-md border border-border bg-surface px-4 py-2.5"
                >
                  <span className="text-sm capitalize">{s.status.replace(/_/g, " ")}</span>
                  <span className="font-semibold tabular-nums">{s.count}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
