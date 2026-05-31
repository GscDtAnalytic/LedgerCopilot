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
import type { PromptVersion } from "@/lib/api";

interface NewPromptFormProps {
  /** Existing versions, to populate the "Based on" parent selector. */
  versions?: Pick<PromptVersion, "id" | "name" | "alias">[];
}

export function NewPromptForm({ versions = [] }: NewPromptFormProps) {
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
  // Generation config. Blank → omitted from the POST → persists NULL → runtime default,
  // so the version behaves like today unless the author deliberately tunes it.
  const [model, setModel] = useState("");
  const [temperature, setTemperature] = useState("");
  const [topP, setTopP] = useState("");
  const [maxTokens, setMaxTokens] = useState("");
  const [k, setK] = useState("");
  // Changelog — what changed vs the parent (item 4: governance, not just text).
  const [basedOn, setBasedOn] = useState("");
  const [changeSummary, setChangeSummary] = useState("");
  const [expectedOutcome, setExpectedOutcome] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  const canSubmit = name.trim().length > 0 && systemText.trim().length > 0 && !pending;

  async function submit() {
    if (!canSubmit) return;
    setError(null);

    const num = (s: string) => (s.trim() === "" ? null : Number(s));
    const res = await fetch("/api/prompts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: name.trim(),
        description: description.trim(),
        system_text: systemText,
        model: model.trim() === "" ? null : model.trim(),
        temperature: num(temperature),
        top_p: num(topP),
        max_tokens: num(maxTokens),
        k: num(k),
        based_on: basedOn === "" ? null : basedOn,
        change_summary: changeSummary.trim() === "" ? null : changeSummary.trim(),
        expected_outcome: expectedOutcome.trim() === "" ? null : expectedOutcome.trim(),
      }),
    });

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setError(body.detail ?? body.error ?? `Failed (${res.status})`);
      return;
    }

    setName("");
    setDescription("");
    setSystemText("");
    setModel("");
    setTemperature("");
    setTopP("");
    setMaxTokens("");
    setK("");
    setBasedOn("");
    setChangeSummary("");
    setExpectedOutcome("");
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
            placeholder="Short label for this version"
            className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground"
          />
        </div>

        {/* Changelog — frames a new version as a controlled behaviour change, not a
            text edit (item 4): what it derives from, what changed, expected effect. */}
        <fieldset className="rounded-md border border-border p-3">
          <legend className="px-1 text-xs font-medium text-muted">Changelog</legend>
          <div className="space-y-3">
            <div>
              <label htmlFor="pv-basedon" className="block text-xs text-muted">
                Based on <span className="font-normal">(parent version)</span>
              </label>
              <select
                id="pv-basedon"
                value={basedOn}
                onChange={(e) => setBasedOn(e.target.value)}
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground"
              >
                <option value="">— none (new lineage) —</option>
                {versions.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                    {v.alias ? ` (${v.alias})` : ""}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="pv-change" className="block text-xs text-muted">
                Change summary
              </label>
              <input
                id="pv-change"
                type="text"
                value={changeSummary}
                onChange={(e) => setChangeSummary(e.target.value)}
                placeholder="e.g. reduced verbosity, stricter output schema"
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground"
              />
            </div>
            <div>
              <label htmlFor="pv-outcome" className="block text-xs text-muted">
                Expected outcome
              </label>
              <input
                id="pv-outcome"
                type="text"
                value={expectedOutcome}
                onChange={(e) => setExpectedOutcome(e.target.value)}
                placeholder="e.g. improve critical field precision"
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground"
              />
            </div>
          </div>
        </fieldset>

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

        {/* Generation config — the full config that drives behaviour, not just text.
            Leave blank to inherit the standard default. */}
        <fieldset className="rounded-md border border-border p-3">
          <legend className="px-1 text-xs font-medium text-muted">
            Generation config <span className="font-normal">(optional — blank = default)</span>
          </legend>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <div className="col-span-2 sm:col-span-1">
              <label htmlFor="pv-model" className="block text-xs text-muted">
                Model
              </label>
              <input
                id="pv-model"
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="claude-sonnet-4-6"
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground"
              />
            </div>
            <div>
              <label htmlFor="pv-temp" className="block text-xs text-muted">
                Temperature
              </label>
              <input
                id="pv-temp"
                type="number"
                min={0}
                max={1}
                step={0.1}
                value={temperature}
                onChange={(e) => setTemperature(e.target.value)}
                placeholder="1.0"
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground"
              />
            </div>
            <div>
              <label htmlFor="pv-topp" className="block text-xs text-muted">
                top_p
              </label>
              <input
                id="pv-topp"
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={topP}
                onChange={(e) => setTopP(e.target.value)}
                placeholder="—"
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground"
              />
            </div>
            <div>
              <label htmlFor="pv-maxtok" className="block text-xs text-muted">
                Max tokens
              </label>
              <input
                id="pv-maxtok"
                type="number"
                min={1}
                step={1}
                value={maxTokens}
                onChange={(e) => setMaxTokens(e.target.value)}
                placeholder="512"
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground"
              />
            </div>
            <div>
              <label htmlFor="pv-k" className="block text-xs text-muted">
                Self-consistency k
              </label>
              <input
                id="pv-k"
                type="number"
                min={1}
                max={5}
                step={1}
                value={k}
                onChange={(e) => setK(e.target.value)}
                placeholder="3"
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground"
              />
            </div>
          </div>
        </fieldset>

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
