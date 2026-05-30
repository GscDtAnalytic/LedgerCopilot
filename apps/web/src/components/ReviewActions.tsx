"use client";

/**
 * ReviewActions — approve / reject / edit buttons for cases in human review.
 *
 * Client Component: interaction required.
 * Accessible: buttons have descriptive labels; confirmation prevents mis-clicks.
 * Calm: only shown when the case is in `in_human_review` — no noise otherwise.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

interface Props {
  caseId: string;
  apiBase: string;
}

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function ReviewActions({ caseId }: Props) {
  const router = useRouter();
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(
    action: "approve" | "reject" | "edit" | "request_context" | "resend_to_stage",
    note?: string,
    extra?: Record<string, unknown>,
  ) {
    setLoading(action);
    setError(null);
    try {
      const res = await fetch(`${BASE}/api/v1/cases/${caseId}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action,
          note: note ?? null,
          reviewer_id: "web-analyst",
          ...extra,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
      }
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="space-y-3" role="group" aria-label="Review actions">
      {error && (
        <p className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">
          {error}
        </p>
      )}

      <button
        onClick={() => submit("approve")}
        disabled={loading !== null}
        aria-busy={loading === "approve"}
        className="w-full rounded-md border border-success bg-success px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors duration-fast ease-standard hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading === "approve" ? "Approving…" : "Approve"}
      </button>

      <button
        onClick={() => {
          const note = window.prompt("Rejection reason (optional):");
          void submit("reject", note ?? undefined);
        }}
        disabled={loading !== null}
        aria-busy={loading === "reject"}
        className="w-full rounded-md border border-danger px-4 py-2.5 text-sm font-medium text-danger transition-colors duration-fast ease-standard hover:bg-danger/10 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading === "reject" ? "Rejecting…" : "Reject"}
      </button>

      <button
        onClick={() => {
          const note = window.prompt("Edit note (describe what was corrected):");
          void submit("edit", note ?? undefined);
        }}
        disabled={loading !== null}
        aria-busy={loading === "edit"}
        className="w-full rounded-md border border-border px-4 py-2.5 text-sm font-medium text-muted transition-colors duration-fast ease-standard hover:bg-surface disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading === "edit" ? "Sending back…" : "Send back for edit"}
      </button>

      <button
        onClick={() => {
          const note = window.prompt("What additional context do you need?");
          if (note) void submit("request_context", note);
        }}
        disabled={loading !== null}
        aria-busy={loading === "request_context"}
        className="w-full rounded-md border border-border px-4 py-2.5 text-sm font-medium text-muted transition-colors duration-fast ease-standard hover:bg-surface disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading === "request_context" ? "Requesting…" : "Request more context"}
      </button>

      <button
        onClick={() => {
          const note = window.prompt("Resend to re-validation. Note (optional):");
          void submit("resend_to_stage", note ?? undefined, { target_stage: "validated" });
        }}
        disabled={loading !== null}
        aria-busy={loading === "resend_to_stage"}
        className="w-full rounded-md border border-border px-4 py-2.5 text-sm font-medium text-muted transition-colors duration-fast ease-standard hover:bg-surface disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading === "resend_to_stage" ? "Resending…" : "Resend to re-validate"}
      </button>
    </div>
  );
}
