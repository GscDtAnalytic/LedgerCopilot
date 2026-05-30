/**
 * StatusBadge — accessible chip conveying case status.
 *
 * Color is never the sole carrier of meaning: the label is always present.
 * The aria-label makes the semantic explicit for screen readers.
 */

import { statusMeta } from "@/lib/format";

interface Props {
  status: string;
}

export function StatusBadge({ status }: Props) {
  const { label, color } = statusMeta(status);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-0.5 text-xs font-medium ${color}`}
      aria-label={`Status: ${label}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
      {label}
    </span>
  );
}
