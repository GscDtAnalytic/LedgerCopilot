/**
 * Inbox — primary work surface for analysts.
 *
 * Server Component with URL-driven filters (status, document_type).
 * Calm layout: cases needing review are prominent;
 * closed/auto-approved are quieter. One thing at a time.
 */

import Link from "next/link";
import type { Route } from "next";
import { api, type CasesListResponse } from "@/lib/api";
import { SLABadge } from "@/components/SLABadge";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDate } from "@/lib/format";

export const dynamic = "force-dynamic";

const ALL_STATUSES = [
  "received",
  "classified",
  "extracted",
  "validated",
  "reconciled",
  "policy_evaluated",
  "decided",
  "auto_approved",
  "in_human_review",
  "approved",
  "edited",
  "rejected",
  "closed",
];

const ALL_DOC_TYPES = ["invoice", "boleto", "receipt", "out_of_scope"];

interface PageProps {
  searchParams: Promise<Record<string, string | undefined>>;
}

export default async function InboxPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const statusFilter = params.status ?? "";
  const typeFilter = params.type ?? "";
  const page = Number(params.page ?? 1);

  // Fetch all cases — filtering is applied client-side on the page data since
  // the API doesn't support filter params yet (Phase 3 adds server-side filter).
  let data: CasesListResponse = { items: [], total: 0, page: 1, page_size: 20 };
  try {
    data = await api.cases.list(page);
  } catch {
    // API may not be running; show empty state gracefully.
  }

  const items = data.items.filter((c) => {
    if (statusFilter && c.status !== statusFilter) return false;
    if (typeFilter && c.document_type !== typeFilter) return false;
    return true;
  });

  const needsReviewCount = data.items.filter((c) => c.status === "in_human_review").length;

  function filterHref(key: string, val: string): Route {
    const p = new URLSearchParams();
    if (key !== "status" && statusFilter) p.set("status", statusFilter);
    if (key !== "type" && typeFilter) p.set("type", typeFilter);
    if (val) p.set(key, val);
    const qs = p.toString();
    return `/inbox${qs ? `?${qs}` : ""}` as Route;
  }

  return (
    <main id="main" className="mx-auto max-w-5xl px-6 py-12">
      {/* Header */}
      <div className="mb-8 flex flex-wrap items-baseline justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Inbox</h1>
          <p className="mt-1 text-sm text-muted">
            {data.total} cases total
            {needsReviewCount > 0 && (
              <span className="ml-2 font-medium text-warning">
                · {needsReviewCount} need review
              </span>
            )}
          </p>
        </div>
      </div>

      {/* Filters — URL-driven for shareability */}
      <div className="mb-6 flex flex-wrap gap-2" role="group" aria-label="Filters">
        <div className="flex flex-wrap gap-1.5">
          <Link
            href={filterHref("status", "")}
            className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors duration-fast ${
              !statusFilter
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border bg-surface text-muted hover:text-foreground"
            }`}
          >
            All statuses
          </Link>
          {["in_human_review", "auto_approved", "rejected", "closed"].map((s) => (
            <Link
              key={s}
              href={filterHref("status", s)}
              className={`rounded-full border px-3 py-1 text-xs font-medium capitalize transition-colors duration-fast ${
                statusFilter === s
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-surface text-muted hover:text-foreground"
              }`}
            >
              {s.replace(/_/g, " ")}
            </Link>
          ))}
        </div>

        <div className="flex flex-wrap gap-1.5">
          <Link
            href={filterHref("type", "")}
            className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors duration-fast ${
              !typeFilter
                ? "border-border bg-primary text-primary-foreground"
                : "border-border bg-surface text-muted hover:text-foreground"
            }`}
          >
            All types
          </Link>
          {ALL_DOC_TYPES.map((t) => (
            <Link
              key={t}
              href={filterHref("type", t)}
              className={`rounded-full border px-3 py-1 text-xs font-medium capitalize transition-colors duration-fast ${
                typeFilter === t
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-surface text-muted hover:text-foreground"
              }`}
            >
              {t}
            </Link>
          ))}
        </div>
      </div>

      {/* Table */}
      {items.length === 0 ? (
        <div className="rounded-lg border border-border bg-surface px-6 py-16 text-center">
          <p className="text-muted">
            {statusFilter || typeFilter
              ? "No cases match the current filters."
              : "No cases yet. Upload a document to get started."}
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border" role="table" aria-label="Cases">
          <div
            role="row"
            className="grid grid-cols-[2fr_1fr_1fr_1fr_auto] gap-4 border-b border-border bg-surface px-4 py-3 text-xs font-medium uppercase tracking-wider text-muted"
          >
            <span role="columnheader">Document</span>
            <span role="columnheader">Type</span>
            <span role="columnheader">Status</span>
            <span role="columnheader">Received</span>
            <span role="columnheader">SLA</span>
          </div>

          {items.map((c) => (
            <Link
              key={c.id}
              href={`/cases/${c.id}`}
              role="row"
              className="grid grid-cols-[2fr_1fr_1fr_1fr_auto] items-center gap-4 border-b border-border px-4 py-3.5 text-sm transition-colors duration-fast ease-standard last:border-0 hover:bg-surface focus-visible:bg-surface"
            >
              <span role="cell" className="truncate font-medium" title={c.original_filename}>
                {c.original_filename}
              </span>
              <span role="cell" className="text-muted capitalize">{c.document_type ?? "—"}</span>
              <span role="cell"><StatusBadge status={c.status} /></span>
              <span role="cell" className="text-muted">{formatDate(c.created_at)}</span>
              <span role="cell">
                <SLABadge createdAt={c.created_at} status={c.status} />
              </span>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
