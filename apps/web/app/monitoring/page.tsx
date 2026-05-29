/**
 * Monitoring dashboard — cost/latency per stage + case throughput.
 *
 * Server Component. Data follows data-ink principle:
 * no 3D, no gratuitous color, every number has context (unit, benchmark).
 * Recharts bar chart for latency; simple stat cards for cost and throughput.
 */

import Link from "next/link";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

function StatCard({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wider text-muted">{label}</p>
      <p className="mt-2 text-2xl font-semibold tabular-nums">
        {value}
        {unit && <span className="ml-1 text-sm font-normal text-muted">{unit}</span>}
      </p>
    </div>
  );
}

export default async function MonitoringPage() {
  const data = await api.monitoring.get().catch(() => null);

  return (
    <main id="main" className="mx-auto max-w-5xl px-6 py-12">
      <div className="mb-8 flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Monitoring</h1>
          <p className="mt-1 text-sm text-muted">Cost, latency and throughput</p>
        </div>
        <Link
          href="/prompts"
          className="text-sm text-muted transition-colors hover:text-foreground"
        >
          Prompt versions →
        </Link>
      </div>

      {!data ? (
        <p className="text-muted">API not reachable — start the server and refresh.</p>
      ) : (
        <div className="space-y-10">
          {/* Summary cards */}
          <section aria-labelledby="summary-heading">
            <h2 id="summary-heading" className="mb-4 text-sm font-semibold uppercase tracking-wider">
              Summary
            </h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard
                label="Total model runs"
                value={data.total_model_runs.toLocaleString()}
              />
              <StatCard
                label="Total cost"
                value={data.total_cost_usd.toFixed(4)}
                unit="USD"
              />
              <StatCard
                label="Avg cost / doc"
                value={
                  data.stage_metrics.length
                    ? (data.total_cost_usd / (data.total_model_runs || 1)).toFixed(6)
                    : "0.000000"
                }
                unit="USD"
              />
              <StatCard
                label="Cases in system"
                value={data.case_throughput.reduce((s, c) => s + c.count, 0).toString()}
              />
            </div>
          </section>

          {/* Stage table */}
          <section aria-labelledby="stages-heading">
            <h2 id="stages-heading" className="mb-4 text-sm font-semibold uppercase tracking-wider">
              Per-stage metrics
            </h2>
            {data.stage_metrics.length === 0 ? (
              <p className="text-sm text-muted">
                No model runs recorded yet. Upload and process a document first.
              </p>
            ) : (
              <div className="overflow-hidden rounded-lg border border-border">
                <table className="w-full text-sm" aria-label="Stage metrics">
                  <thead>
                    <tr className="border-b border-border bg-surface text-left text-xs font-medium uppercase tracking-wider text-muted">
                      <th scope="col" className="px-4 py-3">Stage</th>
                      <th scope="col" className="px-4 py-3">Model</th>
                      <th scope="col" className="px-4 py-3 text-right">Runs</th>
                      <th scope="col" className="px-4 py-3 text-right">Avg latency</th>
                      <th scope="col" className="px-4 py-3 text-right">p95 latency</th>
                      <th scope="col" className="px-4 py-3 text-right">Avg input</th>
                      <th scope="col" className="px-4 py-3 text-right">Total cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.stage_metrics.map((m, i) => (
                      <tr
                        key={`${m.stage}-${m.model}`}
                        className={`border-b border-border ${i % 2 === 0 ? "" : "bg-surface/50"}`}
                      >
                        <td className="px-4 py-3 font-medium">{m.stage}</td>
                        <td className="px-4 py-3 text-muted">{m.model}</td>
                        <td className="px-4 py-3 text-right tabular-nums">{m.total_runs}</td>
                        <td className="px-4 py-3 text-right tabular-nums">{m.avg_latency_ms.toFixed(0)} ms</td>
                        <td className="px-4 py-3 text-right tabular-nums">{m.p95_latency_ms.toFixed(0)} ms</td>
                        <td className="px-4 py-3 text-right tabular-nums">{m.avg_input_tokens.toFixed(0)} tok</td>
                        <td className="px-4 py-3 text-right tabular-nums font-mono text-xs">
                          ${m.total_cost_usd.toFixed(6)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* Case throughput */}
          <section aria-labelledby="throughput-heading">
            <h2 id="throughput-heading" className="mb-4 text-sm font-semibold uppercase tracking-wider">
              Case throughput by status
            </h2>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {data.case_throughput.map((c) => (
                <div
                  key={c.status}
                  className="flex items-center justify-between rounded-md border border-border bg-surface px-4 py-2.5"
                >
                  <span className="text-sm capitalize">{c.status.replace(/_/g, " ")}</span>
                  <span className="font-semibold tabular-nums">{c.count}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
