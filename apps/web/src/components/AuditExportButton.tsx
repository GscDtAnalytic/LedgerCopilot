"use client";

/**
 * AuditExportButton — downloads the full audit package for a case as JSON.
 * Uses the browser's native download mechanism (no temp URL needed).
 * Shown to approvers and admins; analysts see a read-only hint.
 */

import { useState } from "react";
import { getCurrentUser } from "@/lib/auth";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function AuditExportButton({ caseId }: { caseId: string }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const user = getCurrentUser();
  const canExport = user && ["approver", "admin"].includes(user.role);

  if (!canExport) {
    return (
      <p className="text-xs text-muted">
        Sign in as <strong>Approver</strong> or <strong>Admin</strong> to export the audit
        package.
      </p>
    );
  }

  async function handleExport() {
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem("lc_token");
      const res = await fetch(
        `${BASE_URL}/api/v1/cases/${caseId}/audit-export`,
        token ? { headers: { Authorization: `Bearer ${token}` } } : {},
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit_${caseId.slice(0, 8)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("Export failed — check the console.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <button
        onClick={() => { void handleExport(); }}
        disabled={loading}
        className="w-full rounded-md border border-border px-3 py-2 text-left text-sm font-medium transition-colors hover:bg-background disabled:opacity-60"
        aria-label="Export audit package as JSON"
      >
        {loading ? "Preparing…" : "Export audit package"}
      </button>
      {error && (
        <p role="alert" className="mt-1.5 text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
