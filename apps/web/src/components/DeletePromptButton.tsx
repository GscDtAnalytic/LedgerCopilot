"use client";

/**
 * DeletePromptButton — admin-only soft-delete action for a prompt version.
 *
 * Uses a two-step confirmation (click → confirm/cancel) to prevent accidental
 * deletion. Blocked by the API if the version has alias=production.
 * On success, router.refresh() causes the Server Component list to re-fetch.
 */

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { getCurrentUser, getToken } from "@/lib/auth";

interface Props {
  promptId: string;
  currentAlias: string | null;
}

export function DeletePromptButton({ promptId, currentAlias }: Props) {
  const [isAdmin, setIsAdmin] = useState(false);
  useEffect(() => {
    setIsAdmin(getCurrentUser()?.role === "admin");
  }, []);

  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  if (!isAdmin) return null;

  function requestConfirm() {
    setError(null);
    setConfirming(true);
  }

  function cancel() {
    setConfirming(false);
    setError(null);
  }

  function confirm() {
    startTransition(async () => {
      const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const token = getToken();
      const res = await fetch(`${base}/api/v1/prompts/${promptId}`, {
        method: "DELETE",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok || res.status === 204) {
        router.refresh();
        router.push("/prompts");
      } else {
        const body = await res.json().catch(() => null);
        const detail = body?.detail ?? `Delete failed (${res.status})`;
        setError(typeof detail === "string" ? detail : JSON.stringify(detail));
        setConfirming(false);
      }
    });
  }

  const isProduction = currentAlias === "production";

  if (confirming) {
    return (
      <div className="flex flex-col items-end gap-1">
        {isProduction && (
          <p className="max-w-48 text-right text-xs text-warning">
            ⚠ Production version — pipeline falls back to built-in prompt.
          </p>
        )}
        <div className="flex items-center gap-1">
          <span className="text-xs text-muted">Delete?</span>
          <button
            onClick={confirm}
            disabled={pending}
            aria-busy={pending}
            className="rounded border border-danger/60 px-2 py-0.5 text-xs font-medium text-danger transition-colors hover:bg-danger/10 disabled:opacity-40"
          >
            {pending ? "…" : "Yes"}
          </button>
          <button
            onClick={cancel}
            disabled={pending}
            className="rounded border border-border px-2 py-0.5 text-xs font-medium text-muted transition-colors hover:text-foreground disabled:opacity-40"
          >
            No
          </button>
        </div>
        {error && (
          <p role="alert" className="max-w-48 text-right text-xs text-danger">
            {error}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={requestConfirm}
        className="rounded border border-border px-2 py-0.5 text-xs font-medium text-muted transition-colors hover:border-danger/60 hover:text-danger"
      >
        delete
      </button>
      {error && (
        <p role="alert" className="max-w-48 text-right text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
