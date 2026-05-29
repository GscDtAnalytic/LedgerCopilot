"use client";

/**
 * TopBar — client component that reads the JWT to show user/role context.
 * Shows role badge and logout. Fades to a login link when unauthenticated.
 * WCAG: nav landmark, keyboard-accessible buttons.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { type AuthUser, ROLE_LABELS, clearToken, getCurrentUser } from "@/lib/auth";

const ROLE_COLORS: Record<string, string> = {
  analyst: "bg-blue-50 text-blue-700 border-blue-200",
  approver: "bg-amber-50 text-amber-700 border-amber-200",
  admin: "bg-purple-50 text-purple-700 border-purple-200",
};

export function TopBar() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setUser(getCurrentUser());
    setMounted(true);
  }, []);

  function handleLogout() {
    clearToken();
    window.location.href = "/login";
  }

  return (
    <header className="border-b border-border bg-surface">
      <nav
        className="mx-auto flex max-w-5xl items-center gap-6 px-6 py-3"
        aria-label="Main navigation"
      >
        <a href="/inbox" className="text-sm font-semibold tracking-tight">
          LedgerCopilot
        </a>
        <div className="flex gap-4 text-sm text-muted">
          <Link href="/inbox" className="transition-colors hover:text-foreground">
            Inbox
          </Link>
          <Link href="/dashboard" className="transition-colors hover:text-foreground">
            Dashboard
          </Link>
          <Link href="/monitoring" className="transition-colors hover:text-foreground">
            Monitoring
          </Link>
          <Link href="/prompts" className="transition-colors hover:text-foreground">
            Prompts
          </Link>
        </div>

        <div className="ml-auto flex items-center gap-3">
          {mounted && user ? (
            <>
              <span className="hidden text-xs text-muted sm:block">{user.email}</span>
              <span
                className={`rounded border px-2 py-0.5 text-xs font-medium ${ROLE_COLORS[user.role] ?? ""}`}
                aria-label={`Role: ${ROLE_LABELS[user.role] ?? user.role}`}
              >
                {ROLE_LABELS[user.role] ?? user.role}
              </span>
              <button
                onClick={handleLogout}
                className="text-xs text-muted transition-colors hover:text-foreground"
                aria-label="Log out"
              >
                Sign out
              </button>
            </>
          ) : mounted ? (
            <Link
              href="/login"
              className="rounded-md border border-border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-surface"
            >
              Sign in
            </Link>
          ) : null}
        </div>
      </nav>
    </header>
  );
}
