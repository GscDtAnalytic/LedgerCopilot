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
import { AuditTimeline } from "@/components/AuditTimeline";
import { ConfidenceBar } from "@/components/ConfidenceBar";
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
  const extractionEntries = caseData.extraction
    ? Object.entries(caseData.extraction).filter(([, v]) => v !== null && v !== undefined)
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
