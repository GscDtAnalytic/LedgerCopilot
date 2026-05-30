/**
 * Case detail — the analyst's primary review surface.
 *
 * Server Component. Calm layout: decision and justification first (what the
 * analyst needs to act), then extracted fields with confidence, then validation
 * results, then the full audit timeline. Context on demand, not all at once
 *.
 */

import Link from "next/link";
import { notFound } from "next/navigation";
import { api, type FieldValue } from "@/lib/api";
import { AuditExportButton } from "@/components/AuditExportButton";
import { AuditTimeline } from "@/components/AuditTimeline";
import { ConfidenceBar } from "@/components/ConfidenceBar";
import { ReviewActions } from "@/components/ReviewActions";
import { StatusBadge } from "@/components/StatusBadge";
import { decisionMeta, formatDate, pct } from "@/lib/format";

interface Props {
  params: Promise<{ id: string }>;
}

const FIELD_LABELS: Record<string, string> = {
  supplier_name: "Supplier",
  tax_id_cnpj: "CNPJ",
  total_amount: "Total",
  currency: "Currency",
  issue_date: "Issue date",
  due_date: "Due date",
  document_number: "Document #",
  cost_center: "Cost center",
  category: "Category",
};

function FieldRow({ name, fv }: { name: string; fv: FieldValue }) {
  return (
    <div className="grid grid-cols-[8rem_1fr_6rem] items-center gap-4 border-b border-border py-2.5 text-sm last:border-0">
      <span className="text-muted">{FIELD_LABELS[name] ?? name}</span>
      <span className={fv.value !== null ? "font-medium" : "text-muted italic"}>
        {fv.value !== null ? String(fv.value) : "not found"}
      </span>
      <ConfidenceBar confidence={fv.confidence} label={FIELD_LABELS[name] ?? name} />
    </div>
  );
}

export default async function CaseDetailPage({ params }: Props) {
  const { id } = await params;

  const [caseData, auditEvents] = await Promise.all([
    api.cases.get(id).catch(() => null),
    api.cases.audit(id).catch(() => []),
  ]);

  if (!caseData) notFound();

  const { label: decisionLabel, color: decisionColor } = decisionMeta(caseData.decision);
  const items = caseData.extraction?.items ?? [];
  // Scalar fields only — `items` is rendered separately as a table below.
  const extractionEntries = caseData.extraction
    ? Object.entries(caseData.extraction).filter(
        ([k, v]) => k !== "items" && v !== null && v !== undefined,
      )
    : [];

  return (
    <main id="main" className="mx-auto max-w-4xl px-6 py-12">
      {/* Back link */}
      <Link
        href="/inbox"
        className="mb-8 flex items-center gap-1.5 text-sm text-muted transition-colors duration-fast hover:text-foreground"
      >
        <span aria-hidden="true">←</span> Inbox
      </Link>

      {/* Header */}
      <div className="mb-10">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1
              className="truncate text-xl font-semibold tracking-tight"
              title={caseData.original_filename}
            >
              {caseData.original_filename}
            </h1>
            <p className="mt-1 font-mono text-xs text-muted">Case {caseData.id}</p>
          </div>
          <StatusBadge status={caseData.status} />
        </div>

        {/* Decision callout — the most important thing for a reviewer */}
        {caseData.decision && (
          <div
            className="mt-6 rounded-md border border-border bg-surface p-4"
            role="region"
            aria-labelledby="decision-heading"
          >
            <p id="decision-heading" className="text-xs font-medium uppercase tracking-wider text-muted">
              Decision
            </p>
            <p className={`mt-1 text-lg font-semibold ${decisionColor}`}>{decisionLabel}</p>
            {caseData.justification && (
              <p className="mt-2 text-sm text-muted">{caseData.justification}</p>
            )}
            {caseData.reason_code && (
              <p className="mt-1 font-mono text-xs text-muted">{caseData.reason_code}</p>
            )}
            {caseData.requires_dual_approval && (
              <p
                className="mt-3 flex items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-1.5 text-xs font-medium text-warning"
                role="note"
              >
                <span aria-hidden="true">⚠</span> Urgent payment — second approver required
              </p>
            )}
          </div>
        )}
      </div>

      <div className="grid gap-8 lg:grid-cols-[1fr_20rem]">
        {/* Left column */}
        <div className="space-y-8">
          {/* Extracted fields */}
          <section aria-labelledby="fields-heading">
            <h2 id="fields-heading" className="mb-4 text-sm font-semibold uppercase tracking-wider">
              Extracted fields
              {caseData.overall_confidence !== null && (
                <span className="ml-2 font-normal normal-case text-muted">
                  · overall {pct(caseData.overall_confidence)}
                </span>
              )}
            </h2>

            {extractionEntries.length > 0 ? (
              <div className="rounded-lg border border-border bg-surface px-4">
                {extractionEntries.map(([name, fv]) => (
                  <FieldRow key={name} name={name} fv={fv as FieldValue} />
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted">No extraction results yet.</p>
            )}
          </section>

          {/* Line items */}
          {items.length > 0 && (
            <section aria-labelledby="items-heading">
              <h2 id="items-heading" className="mb-4 text-sm font-semibold uppercase tracking-wider">
                Line items
                <span className="ml-2 font-normal normal-case text-muted">· {items.length}</span>
              </h2>
              <div className="overflow-hidden rounded-lg border border-border bg-surface">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-muted">
                      <th className="px-4 py-2 font-medium">Description</th>
                      <th className="px-4 py-2 text-right font-medium">Qty</th>
                      <th className="px-4 py-2 text-right font-medium">Unit</th>
                      <th className="px-4 py-2 text-right font-medium">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((it, i) => (
                      <tr key={i} className="border-b border-border last:border-0">
                        <td className="px-4 py-2">{it.description ?? "—"}</td>
                        <td className="px-4 py-2 text-right tabular-nums">{it.quantity ?? "—"}</td>
                        <td className="px-4 py-2 text-right tabular-nums">{it.unit_price ?? "—"}</td>
                        <td className="px-4 py-2 text-right font-medium tabular-nums">
                          {it.line_total ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* Validation rules */}
          {caseData.validations.length > 0 && (
            <section aria-labelledby="validation-heading">
              <h2 id="validation-heading" className="mb-4 text-sm font-semibold uppercase tracking-wider">
                Validation
                {caseData.has_blocking_failure && (
                  <span className="ml-2 font-normal normal-case text-danger">· blocking failure</span>
                )}
              </h2>
              <ul className="space-y-2" aria-label="Validation rules">
                {caseData.validations.map((rule) => (
                  <li
                    key={rule.rule}
                    className="flex items-center gap-3 rounded-md border border-border bg-surface px-3 py-2 text-sm"
                  >
                    <span
                      className={rule.passed ? "text-success" : rule.severity === "block" ? "text-danger" : "text-warning"}
                      aria-label={rule.passed ? "Passed" : "Failed"}
                    >
                      {rule.passed ? "✓" : "✗"}
                    </span>
                    <span className="flex-1">{rule.rule}</span>
                    <span
                      className={`text-xs ${rule.severity === "block" ? "text-danger" : "text-warning"}`}
                    >
                      {rule.severity}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        {/* Right column — metadata + audit */}
        <div className="space-y-8">
          {/* Metadata */}
          <section aria-labelledby="meta-heading" className="rounded-lg border border-border bg-surface p-4">
            <h2 id="meta-heading" className="mb-3 text-xs font-medium uppercase tracking-wider text-muted">
              Details
            </h2>
            <dl className="space-y-2 text-sm">
              {[
                ["Channel", caseData.channel],
                ["Type", caseData.document_type ?? "—"],
                ["Risk", caseData.risk_score !== null ? pct(caseData.risk_score) : "—"],
                ["Pipeline", caseData.pipeline_version],
                ["Received", formatDate(caseData.created_at)],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4">
                  <dt className="text-muted">{k}</dt>
                  <dd className="font-medium">{v}</dd>
                </div>
              ))}
            </dl>
          </section>

          {/* Review actions — only when human decision is needed */}
          {caseData.status === "in_human_review" && (
            <section aria-labelledby="actions-heading" className="rounded-lg border border-border bg-surface p-4">
              <h2 id="actions-heading" className="mb-4 text-sm font-semibold uppercase tracking-wider">
                Your decision
              </h2>
              <ReviewActions caseId={caseData.id} apiBase="" />
            </section>
          )}

          {/* Audit export — Phase 4, role-gated in the component */}
          <section
            aria-labelledby="export-heading"
            className="rounded-lg border border-border bg-surface p-4"
          >
            <h2 id="export-heading" className="mb-3 text-xs font-medium uppercase tracking-wider text-muted">
              Audit package
            </h2>
            <AuditExportButton caseId={caseData.id} />
          </section>

          {/* Audit trail */}
          <section aria-labelledby="audit-heading">
            <h2 id="audit-heading" className="mb-4 text-sm font-semibold uppercase tracking-wider">
              Audit trail
            </h2>
            <AuditTimeline events={auditEvents} />
          </section>
        </div>
      </div>
    </main>
  );
}
