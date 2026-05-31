"use client";

/**
 * PromoteButton — admin-only action to set/change a prompt version's alias.
 *
 * Two variants so the alias semantics read clearly instead of looking like a row of
 * mystery buttons:
 *   - "compact" (list rows): just the promote buttons, space-constrained.
 *   - "full" (detail page): shows the CURRENT alias, the available promotions, and
 *     greys out unavailable ones WITH the reason (already holds it / needs a scorecard).
 *
 * Gated by role (reads JWT on mount, renders nothing for non-admins). On success,
 * router.refresh() makes the parent Server Component re-fetch.
 */

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { getCurrentUser, getToken } from "@/lib/auth";

const ALIASES = ["dev", "staging", "production"] as const;

interface Props {
  promptId: string;
  currentAlias: string | null;
  hasScorecard?: boolean;
  variant?: "compact" | "full";
}

export function PromoteButton({
  promptId,
  currentAlias,
  hasScorecard = false,
  variant = "compact",
}: Props) {
  const [isAdmin, setIsAdmin] = useState(false);
  useEffect(() => {
    setIsAdmin(getCurrentUser()?.role === "admin");
  }, []);

  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  if (!isAdmin) return null;

  function promote(alias: string) {
    setError(null);
    startTransition(async () => {
      const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const token = getToken();
      const res = await fetch(`${base}/api/v1/prompts/${promptId}/promote`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ alias }),
      });
      if (res.ok) {
        router.refresh();
      } else {
        const body = await res.json().catch(() => null);
        const detail = body?.detail ?? `Promotion failed (${res.status})`;
        setError(typeof detail === "string" ? detail : JSON.stringify(detail));
      }
    });
  }

  // Why is a given alias unavailable right now? (null = available)
  function unavailableReason(alias: string): string | null {
    if (currentAlias === alias) return "current";
    if (alias === "production" && !hasScorecard) return "needs scorecard";
    return null;
  }

  if (variant === "compact") {
    return (
      <div className="flex flex-col items-end gap-1">
        <div role="group" aria-label="Promote to alias" className="flex gap-1">
          {ALIASES.map((alias) => {
            const reason = unavailableReason(alias);
            return (
              <button
                key={alias}
                onClick={() => promote(alias)}
                disabled={pending || reason !== null}
                aria-busy={pending}
                title={reason === "needs scorecard" ? "Run eval first to generate a scorecard" : undefined}
                className="rounded border border-border px-2 py-0.5 text-xs font-medium text-muted transition-colors hover:border-primary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
              >
                {alias}
              </button>
            );
          })}
        </div>
        {error && (
          <p role="alert" className="max-w-48 text-right text-xs text-danger">
            {error}
          </p>
        )}
      </div>
    );
  }

  // ── full variant ──────────────────────────────────────────────────────────
  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wider text-muted">Current alias</span>
        {currentAlias ? (
          <span className="rounded-full border border-border bg-background px-2.5 py-0.5 text-xs font-medium uppercase">
            {currentAlias}
          </span>
        ) : (
          <span className="text-xs text-muted">none (draft)</span>
        )}
      </div>

      <div>
        <p className="mb-1.5 text-xs font-medium uppercase tracking-wider text-muted">Promote to</p>
        <div role="group" aria-label="Promote to alias" className="flex flex-wrap gap-2">
          {ALIASES.map((alias) => {
            const reason = unavailableReason(alias);
            return (
              <button
                key={alias}
                onClick={() => promote(alias)}
                disabled={pending || reason !== null}
                aria-busy={pending}
                title={reason === "needs scorecard" ? "Run eval first to generate a scorecard" : undefined}
                className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium transition-colors hover:border-primary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
              >
                <span className="uppercase">{alias}</span>
                {reason && <span className="text-[10px] font-normal text-muted">· {reason}</span>}
              </button>
            );
          })}
        </div>
      </div>

      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
