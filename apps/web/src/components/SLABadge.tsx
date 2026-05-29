/**
 * SLABadge — shows a warning when a case has been waiting too long.
 *
 * Calm tech: only renders something visible when action is
 * genuinely needed. Hidden otherwise. Color is paired with a text label.
 */

interface Props {
  createdAt: string;
  status: string;
  slaHours?: number;
}

export function SLABadge({ createdAt, status, slaHours = 24 }: Props) {
  const needsAttention =
    status === "in_human_review" &&
    Date.now() - new Date(createdAt).getTime() > slaHours * 3_600_000;

  if (!needsAttention) return null;

  return (
    <span
      className="inline-flex items-center gap-1 rounded-full bg-danger/10 px-2 py-0.5 text-xs font-medium text-danger"
      aria-label={`SLA breach: case waiting over ${slaHours} hours`}
      title={`Waiting over ${slaHours}h`}
    >
      <span aria-hidden="true">⚠</span> Overdue
    </span>
  );
}
