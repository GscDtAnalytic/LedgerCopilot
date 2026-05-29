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

export function decisionMeta(decision: string | null): { label: string; color: string } {
  if (!decision) return { label: "—", color: "text-muted" };
  const map: Record<string, { label: string; color: string }> = {
    auto_approve: { label: "Auto-approved", color: "text-success" },
    human_review: { label: "Review", color: "text-warning" },
    reject: { label: "Rejected", color: "text-danger" },
  };
  return map[decision] ?? { label: decision, color: "text-muted" };
}

export function confidenceColor(confidence: number): string {
  if (confidence >= 0.9) return "text-success";
  if (confidence >= 0.7) return "text-warning";
  return "text-danger";
}
