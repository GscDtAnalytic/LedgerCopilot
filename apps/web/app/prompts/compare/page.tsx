/**
 * Version compare — put two prompt versions side by side with per-metric delta and
 * verdict. This is where "improved quality but failed the cost/risk gate" becomes
 * visible: a version can look better on accuracy and still be Blocked. The metrics +
 * verdict come straight from the API (eval.gate), so they match the promotion gate.
 *
 * Query: ?a=<id>&b=<id>&baseline=a|b. b defaults to the production version.
 */

import Link from "next/link";
import { api, type CompareResult, type PromptVersion } from "@/lib/api";
import { formatMetricDelta, formatMetricValue, severityMeta } from "@/lib/format";

interface Props {
  searchParams: Promise<{ a?: string; b?: string; baseline?: string }>;
}

const CONFIG_FIELDS: { key: "model" | "temperature" | "top_p" | "max_tokens" | "k"; label: string }[] = [
  { key: "model", label: "Model" },
  { key: "temperature", label: "Temperature" },
  { key: "top_p", label: "top_p" },
  { key: "max_tokens", label: "Max tokens" },
  { key: "k", label: "k" },
];

function configValue(v: number | string | null): string {
  return v === null || v === undefined ? "default" : String(v);
}

function ComparePicker({
  versions,
  a,
  b,
  baseline,
}: {
  versions: PromptVersion[];
  a?: string;
  b?: string;
  baseline: string;
}) {
  // Plain GET form — works without JS, navigates back to this page with new params.
  return (
    <form
      method="get"
      className="flex flex-wrap items-end gap-3 rounded-lg border border-border bg-surface p-4"
      aria-label="Choose versions to compare"
    >
      <label className="flex flex-col gap-1 text-xs text-muted">
        Version A
        <select name="a" defaultValue={a ?? ""} className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground">
          <option value="" disabled>
            Select…
          </option>
          {versions.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
              {v.alias ? ` (${v.alias})` : ""}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-xs text-muted">
        Version B
        <select name="b" defaultValue={b ?? ""} className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground">
          <option value="">production (default)</option>
          {versions.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
              {v.alias ? ` (${v.alias})` : ""}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-xs text-muted">
        Baseline
        <select name="baseline" defaultValue={baseline} className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground">
          <option value="b">B is baseline</option>
          <option value="a">A is baseline</option>
        </select>
      </label>
      <button
        type="submit"
        className="rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground"
      >
        Compare
      </button>
    </form>
  );
}

export default async function ComparePage({ searchParams }: Props) {
  const { a, b, baseline: baselineParam } = await searchParams;
  const baseline = baselineParam === "a" ? "a" : "b";

  const versions = await api.prompts.list().catch(() => [] as PromptVersion[]);
  const result: CompareResult | null = a
    ? await api.prompts.compare(a, b, baseline).catch(() => null)
    : null;

  // The candidate is the non-baseline side; the verdict reads candidate-vs-baseline.
  const candidate = result ? (result.baseline === "a" ? result.b : result.a) : null;
  const baselineVersion = result ? (result.baseline === "a" ? result.a : result.b) : null;
  const candidateHasScorecard = result
    ? result.baseline === "a"
      ? result.b_has_scorecard
      : result.a_has_scorecard
    : false;
  const baselineHasScorecard = result
    ? result.baseline === "a"
      ? result.a_has_scorecard
      : result.b_has_scorecard
    : false;

  const overallPassed = result ? result.metrics.filter((m) => m.gated).every((m) => m.passed) : false;

  return (
    <main id="main" className="mx-auto max-w-4xl px-6 py-12">
      <Link
        href="/prompts"
        className="mb-8 flex items-center gap-1.5 text-sm text-muted transition-colors hover:text-foreground"
      >
        <span aria-hidden>←</span> Prompt versions
      </Link>

      <h1 className="mb-1 text-xl font-semibold">Compare versions</h1>
      <p className="mb-6 text-sm text-muted">
        Metrics and verdict are computed by the gate (eval.gate) — a version can improve quality and
        still be blocked by cost or risk.
      </p>

      <div className="mb-8">
        <ComparePicker versions={versions} a={a} b={b} baseline={baseline} />
      </div>

      {!result || !candidate || !baselineVersion ? (
        <p className="text-sm text-muted">
          {a ? "Could not load the comparison." : "Pick a version A to compare against production."}
        </p>
      ) : (
        <>
          {/* Overall verdict */}
          <div
            className={`mb-6 flex items-center gap-2 rounded-md px-4 py-3 text-sm font-medium ${
              overallPassed ? "bg-success/10 text-success" : "bg-danger/10 text-danger"
            }`}
            role="status"
          >
            <span aria-hidden>{overallPassed ? "✓" : "✗"}</span>
            {overallPassed
              ? `${candidate.name} passes all gate rules vs ${baselineVersion.name}`
              : `${candidate.name} is blocked vs ${baselineVersion.name}`}
          </div>

          {(!candidateHasScorecard || !baselineHasScorecard) && (
            <p className="mb-4 rounded-md border border-warning/40 bg-warning/5 px-3 py-2 text-xs text-warning">
              ▲ Missing scorecard:{" "}
              {!candidateHasScorecard ? `${candidate.name} ` : ""}
              {!baselineHasScorecard ? `${baselineVersion.name} ` : ""}
              has no eval scorecard — its metrics read as 0. Run eval first for a meaningful compare.
            </p>
          )}

          {/* Metric table */}
          <div className="overflow-hidden rounded-lg border border-border" role="table" aria-label="Metric comparison">
            <div
              role="row"
              className="grid grid-cols-[1.4fr_auto_auto_auto_auto] gap-3 border-b border-border bg-surface px-4 py-3 text-xs font-medium uppercase tracking-wider text-muted"
            >
              <span role="columnheader">Metric</span>
              <span role="columnheader" className="text-right">{candidate.name}</span>
              <span role="columnheader" className="text-right">{baselineVersion.name}</span>
              <span role="columnheader" className="text-right">Δ</span>
              <span role="columnheader" className="text-right">Verdict</span>
            </div>
            {result.metrics.map((m) => {
              const sev = severityMeta(m.severity);
              return (
                <div
                  key={m.key}
                  role="row"
                  className="grid grid-cols-[1.4fr_auto_auto_auto_auto] items-center gap-3 border-b border-border px-4 py-3 text-sm last:border-0"
                >
                  <div>
                    <span>{m.label}</span>
                    <span className="ml-2 text-xs text-muted">
                      {m.gated ? `(${m.threshold_label})` : "informational"}
                    </span>
                  </div>
                  <span className="text-right font-mono">{formatMetricValue(m.key, m.candidate)}</span>
                  <span className="text-right font-mono text-muted">
                    {formatMetricValue(m.key, m.baseline)}
                  </span>
                  <span className="text-right font-mono">{formatMetricDelta(m.key, m.delta)}</span>
                  <span className={`flex items-center justify-end gap-1 ${sev.color}`}>
                    <span aria-hidden>{sev.icon}</span>
                    <span className="text-xs">{m.gated ? sev.label : "—"}</span>
                  </span>
                </div>
              );
            })}
          </div>

          {/* Config diff */}
          <h2 className="mb-3 mt-8 text-sm font-semibold uppercase tracking-wider">Generation config</h2>
          <div className="overflow-hidden rounded-lg border border-border" role="table" aria-label="Config comparison">
            <div
              role="row"
              className="grid grid-cols-[1fr_auto_auto] gap-3 border-b border-border bg-surface px-4 py-3 text-xs font-medium uppercase tracking-wider text-muted"
            >
              <span role="columnheader">Field</span>
              <span role="columnheader" className="text-right">{candidate.name}</span>
              <span role="columnheader" className="text-right">{baselineVersion.name}</span>
            </div>
            {CONFIG_FIELDS.map(({ key, label }) => {
              const av = candidate[key];
              const bv = baselineVersion[key];
              const changed = av !== bv;
              return (
                <div
                  key={key}
                  role="row"
                  className={`grid grid-cols-[1fr_auto_auto] items-center gap-3 border-b border-border px-4 py-2.5 text-sm last:border-0 ${
                    changed ? "bg-warning/5" : ""
                  }`}
                >
                  <span className="flex items-center gap-2">
                    {label}
                    {changed && (
                      <span className="text-xs text-warning" aria-label="changed">
                        ▲ changed
                      </span>
                    )}
                  </span>
                  <span className="text-right font-mono">{configValue(av)}</span>
                  <span className="text-right font-mono text-muted">{configValue(bv)}</span>
                </div>
              );
            })}
            <div className="grid grid-cols-[1fr_auto] items-center gap-3 px-4 py-2.5 text-sm">
              <span className="flex items-center gap-2">
                System prompt
                {result.system_text_changed && (
                  <span className="text-xs text-warning" aria-label="changed">
                    ▲ changed
                  </span>
                )}
              </span>
              <span className="text-right text-xs text-muted">
                {result.system_text_changed ? "differs between versions" : "identical"}
              </span>
            </div>
          </div>
        </>
      )}
    </main>
  );
}
