/**
 * Presentation helpers — pure functions, no side-effects.
 */

export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));
}

export function pct(confidence: number): string {
  return `${Math.round(confidence * 100)}%`;
}

/** Maps a case status to a human label and a semantic color role. */
export function statusMeta(status: string): { label: string; color: string } {
  const map: Record<string, { label: string; color: string }> = {
    received: { label: "Received", color: "text-muted" },
    classified: { label: "Classifying", color: "text-muted" },
    extracted: { label: "Extracting", color: "text-muted" },
    validated: { label: "Validating", color: "text-muted" },
    reconciled: { label: "Reconciling", color: "text-muted" },
    policy_evaluated: { label: "Policy check", color: "text-muted" },
    decided: { label: "Decided", color: "text-muted" },
    auto_approved: { label: "Auto-approved", color: "text-success" },
    in_human_review: { label: "Needs review", color: "text-warning" },
    approved: { label: "Approved", color: "text-success" },
    edited: { label: "Edited", color: "text-warning" },
    rejected: { label: "Rejected", color: "text-danger" },
    closed: { label: "Closed", color: "text-muted" },
  };
  return map[status] ?? { label: status, color: "text-muted" };
}

export function decisionMeta(decision: string | null): { label: string; color: string; icon: string } {
  if (!decision) return { label: "—", color: "text-muted", icon: "○" };
  const map: Record<string, { label: string; color: string; icon: string }> = {
    auto_approve: { label: "Auto-approved", color: "text-success", icon: "✓" },
    human_review: { label: "Review", color: "text-warning", icon: "⟳" },
    reject: { label: "Rejected", color: "text-danger", icon: "✗" },
  };
  return map[decision] ?? { label: decision, color: "text-muted", icon: "○" };
}

export function nextActionLabel(decision: string | null, status: string): string {
  if (decision === "auto_approve") return "No action required — processing automatically";
  if (decision === "human_review") {
    return status === "in_human_review"
      ? "Review and approve or reject below"
      : "Awaiting assignment to review queue";
  }
  if (decision === "reject") return "Case closed — rejected";
  return "—";
}

export function confidenceColor(confidence: number): string {
  if (confidence >= 0.9) return "text-success";
  if (confidence >= 0.7) return "text-warning";
  return "text-danger";
}

/** Format a scorecard metric value by its key (percent, USD, or ms). */
export function formatMetricValue(key: string, value: number | null): string {
  if (value === null) return "—";
  if (key === "avg_cost_per_doc") return `$${value.toFixed(6)}`;
  if (key === "p95_latency_ms") return `${value.toFixed(0)} ms`;
  // Everything else is a 0–1 rate/accuracy.
  return `${(value * 100).toFixed(1)}%`;
}

/** Format a candidate−baseline delta with a sign, in the metric's own units. */
export function formatMetricDelta(key: string, delta: number | null): string {
  if (delta === null) return "—";
  const sign = delta > 0 ? "+" : "";
  if (key === "avg_cost_per_doc") return `${sign}$${delta.toFixed(6)}`;
  if (key === "p95_latency_ms") return `${sign}${delta.toFixed(0)} ms`;
  return `${sign}${(delta * 100).toFixed(1)}pp`;
}

/**
 * Precise lifecycle state for a prompt version, derived from (alias, scorecard,
 * gate verdict). Replaces the ambiguous "Ready to promote" badge: a production
 * version reads as a baseline, a passing candidate as eligible, a failing one as
 * blocked, an un-evaluated one as draft. Color is paired with icon + label (§13.1).
 */
export function lifecycleStatus(
  alias: string | null,
  hasScorecard: boolean,
  passed: boolean,
): { label: string; shortLabel: string; icon: string; badge: string } {
  const success = "bg-success/10 text-success";
  if (alias === "production") {
    return { label: "Production baseline", shortLabel: "Production", icon: "★", badge: success };
  }
  if (!hasScorecard) {
    return alias
      ? {
          label: `In ${alias} — needs eval`,
          shortLabel: alias,
          icon: "○",
          badge: "bg-border/50 text-muted",
        }
      : { label: "Draft — needs eval", shortLabel: "Draft", icon: "○", badge: "bg-border/50 text-muted" };
  }
  if (!passed) {
    return { label: "Blocked by gate", shortLabel: "Blocked", icon: "✗", badge: "bg-danger/10 text-danger" };
  }
  if (alias === "staging" || alias === "dev") {
    return { label: `In ${alias} — passed`, shortLabel: alias, icon: "◐", badge: success };
  }
  return { label: "Promotion passed — eligible", shortLabel: "Eligible", icon: "✓", badge: success };
}

/**
 * Visual treatment for a metric verdict severity. Color is paired with an icon and
 * label so meaning never rides on color alone (§13.1).
 */
export function severityMeta(
  severity: "good" | "warning" | "fail",
): { color: string; icon: string; label: string } {
  const map: Record<string, { color: string; icon: string; label: string }> = {
    good: { color: "text-success", icon: "✓", label: "Pass" },
    warning: { color: "text-warning", icon: "▲", label: "Warning" },
    fail: { color: "text-danger", icon: "✗", label: "Fail" },
  };
  return map[severity] ?? { color: "text-muted", icon: "○", label: severity };
}
