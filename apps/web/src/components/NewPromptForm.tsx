"use client";

/**
 * New prompt version form — admin-only authoring surface on the Prompts page.
 *
 * Client Component: it owns the form state and pending/error UI. The mutation
 * goes through the /api/prompts route handler (which forwards the session cookie
 * to FastAPI); on success we router.refresh() so the server-rendered list picks
 * up the new row. Visibility is gated by the server (page renders this only for
 * admins) AND by the API (require_roles("admin")) — defence in depth.
 *
 * Calm UI (§13.2): collapsed by default so the read-only list stays the focus;
 * the author opens it deliberately. New versions land with NO alias and NO
 * scorecard — they only become promotable after eval.run writes a scorecard.
 */

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";

export function NewPromptForm() {
  // Role lives in the JWT in localStorage, only readable after mount. Gate on it
  // so non-admins never see an action the API would reject (calm UI, §13.2).
  // The POST is still enforced admin-only server-side — this is just the surface.
  const [isAdmin, setIsAdmin] = useState(false);
  useEffect(() => {
    setIsAdmin(getCurrentUser()?.role === "admin");
  }, []);

  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [systemText, setSystemText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  const canSubmit = name.trim().length > 0 && systemText.trim().length > 0 && !pending;

  async function submit() {
    if (!canSubmit) return;
    setError(null);

    const res = await fetch("/api/prompts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: name.trim(),
        description: description.trim(),
        system_text: systemText,
      }),
    });

    if (!res.ok) {
      const body = await res.json().catch(() => ({ error: "Request failed" }));
      setError(body.error ?? `Failed (${res.status})`);
      return;
    }

    setName("");
    setDescription("");
    setSystemText("");
    setOpen(false);
    startTransition(() => {
      router.refresh();
    });
  }

  if (!isAdmin) return null;

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-md border border-border bg-surface px-4 py-2 text-sm font-medium transition-colors hover:bg-background focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground"
      >
        + New version
      </button>
    );
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
      className="w-full rounded-lg border border-border bg-surface p-4"
      aria-label="Create prompt version"
    >
      <div className="space-y-4">
        <div>
          <label htmlFor="pv-name" className="block text-xs font-medium text-muted">
            Name
          </label>
          <input
            id="pv-name"
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="extraction-v2"
            className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground"
          />
        </div>

        <div>
          <label htmlFor="pv-desc" className="block text-xs font-medium text-muted">
            Description <span className="font-normal">(optional)</span>
          </label>
          <input
            id="pv-desc"
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What changed and why"
            className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground"
          />
        </div>

        <div>
          <label htmlFor="pv-system" className="block text-xs font-medium text-muted">
            System text
          </label>
          <textarea
            id="pv-system"
            required
            rows={8}
            value={systemText}
            onChange={(e) => setSystemText(e.target.value)}
            placeholder="You are the extraction agent for LedgerCopilot…"
            className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground"
          />
        </div>

        {error && (
          <p role="alert" className="text-sm text-danger">
            ⚠ {error}
          </p>
        )}

        <p className="text-xs text-muted">
          New versions start with no alias and no scorecard. Run{" "}
          <code className="rounded bg-background px-1 py-0.5">eval.run</code> to score, then
          promote.
        </p>

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={!canSubmit}
            className="rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground"
          >
            {pending ? "Creating…" : "Create version"}
          </button>
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              setError(null);
            }}
            className="text-sm text-muted transition-colors hover:text-foreground"
          >
            Cancel
          </button>
        </div>
      </div>
    </form>
  );
}
