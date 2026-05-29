/**
 * Inbox — the primary work surface for analysts.
 *
 * Server Component: no client-side JS needed for a list.
 * Calm layout: cases needing review are prominent; closed/auto-approved are
 * quieter. One data structure, consistent landmark, no off-screen noise.
 */

import Link from "next/link";
import { api } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDate } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function InboxPage() {
  const { items, total } = await api.cases.list(1).catch(() => ({
    items: [],
    total: 0,
  }));

  return (
    <main id="main" className="mx-auto max-w-5xl px-6 py-12">
      <div className="mb-8 flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Inbox</h1>
          <p className="mt-1 text-sm text-muted">{total} cases total</p>
        </div>
      </div>

      {items.length === 0 ? (
        <div className="rounded-lg border border-border bg-surface px-6 py-16 text-center">
          <p className="text-muted">No cases yet. Upload a document to get started.</p>
          <p className="mt-2 text-xs text-muted">
            <code className="rounded bg-background px-1.5 py-0.5">
              POST /api/v1/documents
            </code>
          </p>
        </div>
      ) : (
        <div
          className="overflow-hidden rounded-lg border border-border"
          role="table"
          aria-label="Cases"
        >
          {/* Header */}
          <div
            role="row"
            className="grid grid-cols-[2fr_1fr_1fr_1fr] gap-4 border-b border-border bg-surface px-4 py-3 text-xs font-medium uppercase tracking-wider text-muted"
          >
            <span role="columnheader">Document</span>
            <span role="columnheader">Type</span>
            <span role="columnheader">Status</span>
            <span role="columnheader">Received</span>
          </div>

          {/* Rows */}
          {items.map((c) => (
            <Link
              key={c.id}
              href={`/cases/${c.id}`}
              role="row"
              className="grid grid-cols-[2fr_1fr_1fr_1fr] items-center gap-4 border-b border-border px-4 py-3.5 text-sm transition-colors duration-fast ease-standard last:border-0 hover:bg-surface focus-visible:bg-surface"
            >
              <span
                role="cell"
                className="truncate font-medium"
                title={c.original_filename}
              >
                {c.original_filename}
              </span>
              <span role="cell" className="text-muted capitalize">
                {c.document_type ?? "—"}
              </span>
              <span role="cell">
                <StatusBadge status={c.status} />
              </span>
              <span role="cell" className="text-muted">
                {formatDate(c.created_at)}
              </span>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
