"use client";

/**
 * Login — demo credential quick-fill + submit.
 * Pre-fills analyst/approver/admin credentials so the demo is one click.
 * On success: stores JWT in localStorage and redirects to /inbox.
 */

import { useState } from "react";
import { setToken } from "@/lib/auth";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const DEMO_USERS = [
  { label: "Analyst", email: "analyst@demo.com", description: "Read cases, submit reviews" },
  { label: "Approver", email: "approver@demo.com", description: "Approve / reject cases" },
  { label: "Admin", email: "admin@demo.com", description: "Full access + executive view" },
] as const;

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function fillDemo(demoEmail: string) {
    setEmail(demoEmail);
    setPassword("demo123");
    setError(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`${BASE_URL}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const data = (await res.json()) as { detail?: string };
        setError(data.detail ?? "Login failed.");
        return;
      }
      const data = (await res.json()) as { access_token: string };
      setToken(data.access_token);
      window.location.href = "/inbox";
    } catch {
      setError("Cannot reach the API. Make sure the server is running.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main
      id="main"
      className="flex min-h-[calc(100vh-56px)] items-center justify-center px-4"
    >
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
          <p className="mt-1 text-sm text-muted">LedgerCopilot · AI Operations Platform</p>
        </div>

        {/* Demo quick-fill */}
        <div className="mb-6 rounded-lg border border-border bg-surface p-4">
          <p className="mb-3 text-xs font-medium uppercase tracking-wider text-muted">
            Demo accounts — password: demo123
          </p>
          <div className="flex flex-col gap-2">
            {DEMO_USERS.map((u) => (
              <button
                key={u.email}
                type="button"
                onClick={() => fillDemo(u.email)}
                className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-left text-sm transition-colors hover:bg-background focus:outline-none focus:ring-2 focus:ring-foreground"
              >
                <span className="font-medium">{u.label}</span>
                <span className="text-xs text-muted">{u.description}</span>
              </button>
            ))}
          </div>
        </div>

        <form onSubmit={(e) => { void handleSubmit(e); }} className="space-y-4" noValidate>
          <div>
            <label htmlFor="email" className="mb-1.5 block text-sm font-medium">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-foreground"
              placeholder="you@example.com"
            />
          </div>

          <div>
            <label htmlFor="password" className="mb-1.5 block text-sm font-medium">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-foreground"
              placeholder="••••••••"
            />
          </div>

          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-md bg-foreground px-4 py-2.5 text-sm font-medium text-background transition-opacity disabled:opacity-60"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </main>
  );
}
