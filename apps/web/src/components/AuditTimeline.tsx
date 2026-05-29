/**
 * AuditTimeline — chronological, accessible event log.
 *
 * Rendered as a <ol> (ordered list of events, not a decorative list) with
 * semantic time elements. Calm: the timeline communicates context without
 * demanding attention.
 */

import type { AuditEvent } from "@/lib/api";
import { formatDate } from "@/lib/format";

interface Props {
  events: AuditEvent[];
}

const ACTOR_LABELS: Record<string, string> = {
  system: "System",
  agent: "Agent",
  human: "Human",
};

export function AuditTimeline({ events }: Props) {
  if (events.length === 0) {
    return <p className="text-sm text-muted">No audit events yet.</p>;
  }

  return (
    <ol className="relative space-y-0" aria-label="Audit trail">
      {events.map((event, i) => (
        <li key={event.id} className="flex gap-4 pb-6 last:pb-0">
          {/* Timeline track */}
          <div className="flex flex-col items-center" aria-hidden="true">
            <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full border-2 border-primary bg-surface" />
            {i < events.length - 1 && (
              <span className="mt-1 w-px flex-1 bg-border" />
            )}
          </div>

          {/* Event content */}
          <div className="min-w-0 pb-1">
            <p className="text-sm font-medium">
              <span className="text-muted">{ACTOR_LABELS[event.actor_type] ?? event.actor_type}</span>
              {" · "}
              <span>
                {event.from_status} → {event.to_status}
              </span>
            </p>
            <time
              dateTime={event.occurred_at}
              className="mt-0.5 block text-xs text-muted"
            >
              {formatDate(event.occurred_at)}
            </time>
            {event.model_name && (
              <p className="mt-1 text-xs text-muted">
                Model: {event.model_name}
                {event.prompt_version_id && ` · prompt@${event.prompt_version_id}`}
              </p>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
