"use client";

/**
 * RunEvalButton — admin-only action to trigger the eval suite for a prompt version.
 *
 * Calls POST /api/v1/prompts/{id}/eval, which runs all 13 eval fixtures and saves
 * the scorecard to the DB. On success the page refreshes to show the new scorecard
 * and gate status. Eval typically takes 5–15 s depending on the model.
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getCurrentUser, getToken } from "@/lib/auth";

interface Props {
  promptId: string;
}

export function RunEvalButton({ promptId }: Props) {
  const [isAdmin, setIsAdmin] = useState(false);
  useEffect(() => {
    setIsAdmin(getCurrentUser()?.role === "admin");
  }, []);

  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  if (!isAdmin) return null;

  async function runEval() {
    setError(null);
    setRunning(true);
    try {
      const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const token = getToken();
      const res = await fetch(`${base}/api/v1/prompts/${promptId}/eval`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        router.refresh();
      } else {
        const body = await res.json().catch(() => null);
        setError(body?.detail ?? `Eval failed (${res.status})`);
      }
    } catch {
      setError("Cannot reach the API.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-1">
      <button
        onClick={() => { void runEval(); }}
        disabled={running}
        aria-busy={running}
        className="inline-flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-1.5 text-sm font-medium transition-colors hover:border-primary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
      >
        {running ? (
          <>
            <span aria-hidden="true" className="animate-spin">⟳</span>
            Running eval…
          </>
        ) : (
          <>
            <span aria-hidden="true">▶</span>
            Run eval
          </>
        )}
      </button>
      {running && (
        <p className="text-xs text-muted">
          Running 13 fixtures — this takes ~5–15 s
        </p>
      )}
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
