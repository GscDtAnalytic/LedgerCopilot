/**
 * Prompt version detail — changelog + promotion verdict + lifecycle/aliases + config.
 *
 * The verdict (which gate rules pass/fail, against the live production baseline) is
 * computed by the API (GET /prompts/{id}/gate), which reuses eval.gate. The page does
 * NOT re-implement gate thresholds — the old version did, and drifted from the real
 * gate.
 */

import Link from "next/link";
import type { Route } from "next";
import { notFound } from "next/navigation";
import { api, type GateVerdict, type PromptVersion } from "@/lib/api";
import { formatDate, formatMetricValue, lifecycleStatus, severityMeta } from "@/lib/format";
import { PromoteButton } from "@/components/PromoteButton";
import { DeletePromptButton } from "@/components/DeletePromptButton";
import { RunEvalButton } from "@/components/RunEvalButton";

interface Props {
  params: Promise<{ id: string }>;
}

const CONFIG_FIELDS: { key: "model" | "temperature" | "top_p" | "max_tokens" | "k"; label: string }[] = [
  { key: "model", label: "Model" },
  { key: "temperature", label: "Temperature" },
  { key: "top_p", label: "top_p" },
  { key: "max_tokens", label: "Max tokens" },
  { key: "k", label: "Self-consistency k" },
];

export default async function PromptDetailPage({ params }: Props) {
  const { id } = await params;
  const pv = await api.prompts.get(id).catch(() => null);
  if (!pv) notFound();

  const verdict: GateVerdict | null = await api.prompts.gate(id).catch(() => null);
  // Resolve the parent version (Based on) for a human-readable changelog link.
  const parent: PromptVersion | null = pv.based_on
    ? await api.prompts.get(pv.based_on).catch(() => null)
    : null;

  const status = lifecycleStatus(pv.alias, !!verdict?.has_scorecard, !!verdict?.passed);

  const gatedMetrics = verdict?.metrics.filter((m) => m.gated) ?? [];
  const infoMetrics = verdict?.metrics.filter((m) => !m.gated) ?? [];
  const canCompare = pv.alias !== "production";
  const hasChangelog = !!(pv.based_on || pv.change_summary || pv.expected_outcome);
  // Pre-select the parent as the compare baseline when present.
  const compareHref = (
    pv.based_on
      ? `/prompts/compare?a=${pv.id}&b=${pv.based_on}&baseline=b`
      : `/prompts/compare?a=${pv.id}`
  ) as Route;

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
          <div className="flex flex-wrap items-center gap-2">
            <span
              title={status.label}
              className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium capitalize ${status.badge}`}
            >
              <span aria-hidden="true">{status.icon}</span>
              {status.label}
            </span>
            {canCompare && (
              <Link
                href={compareHref}
                className="rounded-md border border-border bg-surface px-3 py-1 text-xs font-medium transition-colors hover:bg-background focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground"
              >
                {pv.based_on ? "Compare vs parent" : "Compare vs production"}
              </Link>
            )}
            <DeletePromptButton promptId={pv.id} currentAlias={pv.alias} />
          </div>
        </div>
        {pv.description && <p className="mt-3 text-sm text-muted">{pv.description}</p>}
        <p className="mt-1 text-xs text-muted">Created {formatDate(pv.created_at)}</p>
      </div>

      {/* Changelog — what changed vs the parent (item 4). Only when recorded. */}
      {hasChangelog && (
        <section
          aria-labelledby="changelog-heading"
          className="mb-8 rounded-lg border border-border bg-surface p-4"
        >
          <h2 id="changelog-heading" className="mb-3 text-xs font-medium uppercase tracking-wider text-muted">
            Changelog
          </h2>
          <dl className="space-y-3 text-sm">
            <div className="flex flex-wrap items-baseline gap-2">
              <dt className="w-32 shrink-0 text-muted">Based on</dt>
              <dd>
                {pv.based_on ? (
                  parent ? (
                    <Link href={`/prompts/${parent.id}`} className="font-medium hover:underline">
                      {parent.name}
                      {parent.alias ? ` (${parent.alias})` : ""}
                    </Link>
                  ) : (
                    <span className="font-mono text-xs text-muted">{pv.based_on}</span>
                  )
                ) : (
                  <span className="text-muted">— new lineage</span>
                )}
              </dd>
            </div>
            <div className="flex flex-wrap items-baseline gap-2">
              <dt className="w-32 shrink-0 text-muted">Change summary</dt>
              <dd>{pv.change_summary || <span className="text-muted">—</span>}</dd>
            </div>
            <div className="flex flex-wrap items-baseline gap-2">
              <dt className="w-32 shrink-0 text-muted">Expected outcome</dt>
              <dd>{pv.expected_outcome || <span className="text-muted">—</span>}</dd>
            </div>
          </dl>
        </section>
      )}

      <div className="grid gap-8 lg:grid-cols-[1fr_18rem]">
        {/* Scorecard / gate check */}
        <section aria-labelledby="scorecard-heading">
          <h2 id="scorecard-heading" className="mb-2 text-sm font-semibold uppercase tracking-wider">
            Promotion gate
          </h2>
          {verdict?.baseline_id ? (
            <p className="mb-4 text-xs text-muted">
              Compared against baseline <span className="font-mono">{verdict.baseline_id}</span>.
            </p>
          ) : (
            <p className="mb-4 text-xs text-muted">No production baseline yet — absolute rules only.</p>
          )}

          {!verdict?.has_scorecard ? (
            <div className="space-y-4">
              <p className="text-sm text-muted">No scorecard yet. Run the eval suite to generate one.</p>
              <RunEvalButton promptId={pv.id} />
              <p className="text-xs text-muted">
                Or via CLI:{" "}
                <code className="rounded bg-surface px-1.5 py-0.5">
                  uv run python -m eval.run --prompt-version {pv.id} --post-scorecard {pv.id} --token $TOKEN
                </code>
              </p>
            </div>
          ) : (
            <>
              <ul className="space-y-2" aria-label="Gate metrics">
                {gatedMetrics.map((m) => {
                  const sev = severityMeta(m.severity);
                  return (
                    <li
                      key={m.key}
                      className={`flex items-center justify-between rounded-md border px-3 py-2.5 text-sm ${
                        m.passed ? "border-border bg-surface" : "border-danger/40 bg-danger/5"
                      }`}
                    >
                      <div>
                        <span className={m.passed ? "" : "font-medium text-danger"}>{m.label}</span>
                        <span className="ml-2 text-xs text-muted">({m.threshold_label})</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`font-mono font-medium ${m.passed ? "" : "text-danger"}`}>
                          {formatMetricValue(m.key, m.candidate)}
                        </span>
                        <span aria-label={sev.label} className={sev.color}>
                          {sev.icon}
                        </span>
                      </div>
                    </li>
                  );
                })}
              </ul>

              {/* Informational metrics — shown, never block (§13.1: labelled, not just dimmed). */}
              {infoMetrics.length > 0 && (
                <div className="mt-5">
                  <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted">
                    Informational — not gated
                  </h3>
                  <ul className="space-y-2" aria-label="Informational metrics">
                    {infoMetrics.map((m) => (
                      <li
                        key={m.key}
                        className="flex items-center justify-between rounded-md border border-border bg-surface/50 px-3 py-2 text-sm"
                      >
                        <span className="text-muted">{m.label}</span>
                        <span className="font-mono">{formatMetricValue(m.key, m.candidate)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="mt-4">
                <RunEvalButton promptId={pv.id} />
              </div>
            </>
          )}
        </section>

        <div className="space-y-6">
          {/* Lifecycle & aliases — current alias + available promotions with reasons (item 1). */}
          <section
            aria-labelledby="alias-heading"
            className="rounded-lg border border-border bg-surface p-4"
          >
            <h2 id="alias-heading" className="mb-3 text-xs font-medium uppercase tracking-wider text-muted">
              Lifecycle &amp; aliases
            </h2>
            <PromoteButton
              promptId={pv.id}
              currentAlias={pv.alias}
              hasScorecard={!!verdict?.has_scorecard}
              variant="full"
            />
          </section>

          {/* Generation config — the full config that affects behaviour, not just text. */}
          <section
            aria-labelledby="config-heading"
            className="rounded-lg border border-border bg-surface p-4"
          >
            <h2 id="config-heading" className="mb-3 text-xs font-medium uppercase tracking-wider text-muted">
              Generation config
            </h2>
            <dl className="space-y-2 text-sm">
              {CONFIG_FIELDS.map(({ key, label }) => {
                const value = pv[key];
                return (
                  <div key={key} className="flex justify-between gap-4">
                    <dt className="text-muted">{label}</dt>
                    <dd className="font-mono">
                      {value === null || value === undefined ? (
                        <span className="text-muted">default</span>
                      ) : (
                        String(value)
                      )}
                    </dd>
                  </div>
                );
              })}
            </dl>
          </section>
        </div>
      </div>
    </main>
  );
}
