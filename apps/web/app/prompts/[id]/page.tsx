/**
 * Prompt version detail — scorecard metrics + full system text for review.
 *
 * This is the "version compare" surface: shows each metric against the
 * production baseline thresholds. A blocked metric is highlighted in red.
 * Analysts can see exactly why a promotion is blocked.
 */

import Link from "next/link";
import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";

interface Props {
  params: Promise<{ id: string }>;
}

const GATE_RULES = [
  {
    key: "false_auto_approve_rate",
    label: "False auto-approve rate",
    format: (v: number) => `${(v * 100).toFixed(2)}%`,
    passes: (v: number) => v <= 0.01,
    threshold: "≤ 1%",
  },
  {
    key: "supplier_name_accuracy",
    label: "Supplier name accuracy",
    format: (v: number) => `${(v * 100).toFixed(1)}%`,
    passes: (v: number) => v >= 0.97,
    threshold: "≥ 97%",
  },
  {
    key: "decision_accuracy",
    label: "Decision accuracy",
    format: (v: number) => `${(v * 100).toFixed(1)}%`,
    passes: (v: number) => v >= 0.0, // relative — no absolute threshold
    threshold: "baseline − 5pp",
  },
  {
    key: "avg_cost_per_doc",
    label: "Avg cost / doc",
    format: (v: number) => `$${v.toFixed(6)}`,
    passes: (v: number) => v >= 0.0,
    threshold: "baseline × 1.20",
  },
  {
    key: "p95_latency_ms",
    label: "p95 latency",
    format: (v: number) => `${v.toFixed(0)} ms`,
    passes: (v: number) => v >= 0.0,
    threshold: "informational",
  },
] as const;

export default async function PromptDetailPage({ params }: Props) {
  const { id } = await params;
  const pv = await api.prompts.get(id).catch(() => null);
  if (!pv) notFound();

  const sc = pv.scorecard as Record<string, number | object> | null;

  return (
    <main id="main" className="mx-auto max-w-4xl px-6 py-12">
      <Link
        href="/prompts"
        className="mb-8 flex items-center gap-1.5 text-sm text-muted transition-colors hover:text-foreground"
      >
        <span aria-hidden>←</span> Prompt versions
      </Link>

      <div className="mb-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold">{pv.name}</h1>
            <p className="mt-1 font-mono text-xs text-muted">{pv.id}</p>
          </div>
          {pv.alias && (
            <span className="rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium uppercase">
              {pv.alias}
            </span>
          )}
        </div>
        {pv.description && <p className="mt-3 text-sm text-muted">{pv.description}</p>}
        <p className="mt-1 text-xs text-muted">Created {formatDate(pv.created_at)}</p>
      </div>

      <div className="grid gap-8 lg:grid-cols-[1fr_20rem]">
        {/* Scorecard / gate check */}
        <section aria-labelledby="scorecard-heading">
          <h2 id="scorecard-heading" className="mb-4 text-sm font-semibold uppercase tracking-wider">
            Scorecard vs promotion gate rules
          </h2>

          {!sc ? (
            <p className="text-sm text-muted">
              No scorecard yet. Run eval.run to generate one:
              <code className="ml-2 rounded bg-surface px-2 py-0.5 text-xs">
                uv run python -m eval.run --prompt-version {pv.id} --out scorecard.json
              </code>
            </p>
          ) : (
            <ul className="space-y-2" aria-label="Gate metrics">
              {GATE_RULES.map(({ key, label, format, passes, threshold }) => {
                const raw = sc[key];
                const value = typeof raw === "number" ? raw : null;
                const ok = value === null ? true : passes(value);
                return (
                  <li
                    key={key}
                    className={`flex items-center justify-between rounded-md border px-3 py-2.5 text-sm ${
                      ok ? "border-border bg-surface" : "border-danger/40 bg-danger/5"
                    }`}
                  >
                    <div>
                      <span className={ok ? "" : "font-medium text-danger"}>{label}</span>
                      <span className="ml-2 text-xs text-muted">({threshold})</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`font-mono font-medium ${ok ? "" : "text-danger"}`}>
                        {value !== null ? format(value) : "—"}
                      </span>
                      <span
                        aria-label={ok ? "Passes gate" : "Fails gate"}
                        className={ok ? "text-success" : "text-danger"}
                      >
                        {ok ? "✓" : "✗"}
                      </span>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {/* Field accuracy if available */}
        {sc?.field_accuracy && typeof sc.field_accuracy === "object" && (
          <section aria-labelledby="field-acc-heading" className="rounded-lg border border-border bg-surface p-4">
            <h2 id="field-acc-heading" className="mb-3 text-xs font-medium uppercase tracking-wider text-muted">
              Field accuracy
            </h2>
            <dl className="space-y-2 text-sm">
              {Object.entries(sc.field_accuracy as Record<string, number>).map(([field, acc]) => (
                <div key={field} className="flex justify-between gap-4">
                  <dt className="text-muted capitalize">{field.replace(/_/g, " ")}</dt>
                  <dd className={`font-mono font-medium ${acc < 0.9 ? "text-warning" : ""}`}>
                    {(acc * 100).toFixed(0)}%
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        )}
      </div>
    </main>
  );
}
