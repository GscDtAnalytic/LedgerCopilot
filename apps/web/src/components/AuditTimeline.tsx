/**
 * AuditTimeline — chronological, accessible event log.
 *
 * Rendered as a <ol> (ordered list of events, not a decorative list) with
 * semantic time elements. Calm: the timeline communicates context without
 * demanding attention.
 */

import type { AuditEvent } from "@/lib/api";
import { formatDate, statusMeta } from "@/lib/format";

interface Props {
  events: AuditEvent[];
}

const ACTOR_META: Record<string, { label: string; icon: string; dot: string; badge: string }> = {
  system: { label: "System", icon: "⚙", dot: "border-muted",   badge: "bg-border/60 text-muted"    },
  agent:  { label: "Agent",  icon: "◈", dot: "border-primary", badge: "bg-primary/10 text-primary" },
  human:  { label: "Human",  icon: "◉", dot: "border-success", badge: "bg-success/10 text-success" },
};

function ActorBadge({ actorType }: { actorType: string }) {
  const meta = ACTOR_META[actorType] ?? { label: actorType, icon: "○", dot: "border-muted", badge: "bg-border/60 text-muted" };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${meta.badge}`}>
      <span aria-hidden="true">{meta.icon}</span>
      {meta.label}
    </span>
  );
}

export function AuditTimeline({ events }: Props) {
  if (events.length === 0) {
    return <p className="text-sm text-muted">No audit events yet.</p>;
  }

  return (
    <ol className="relative space-y-0" aria-label="Audit trail">
      {events.map((event, i) => {
        const meta = ACTOR_META[event.actor_type] ?? ACTOR_META.system;
        const isReprocessing = event.from_status === "edited" && event.to_status === "extracted";
        const fromLabel = statusMeta(event.from_status).label;
        const toLabel = statusMeta(event.to_status).label;

        return (
          <li key={event.id} className="flex gap-4 pb-6 last:pb-0">
            {/* Timeline track */}
            <div className="flex flex-col items-center" aria-hidden="true">
              <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full border-2 bg-surface ${meta.dot}`} />
              {i < events.length - 1 && (
                <span className="mt-1 w-px flex-1 bg-border" />
              )}
            </div>

            {/* Event content */}
            <div className="min-w-0 pb-1">
              <div className="flex flex-wrap items-center gap-2">
                <ActorBadge actorType={event.actor_type} />
                <span className="text-sm">
                  {fromLabel} → {toLabel}
                </span>
              </div>
              {isReprocessing && (
                <p className="mt-1 inline-flex items-center gap-1 rounded-sm bg-warning/10 px-2 py-0.5 text-xs text-warning">
                  <span aria-hidden="true">↺</span>
                  Re-entered pipeline for re-validation
                </p>
              )}
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
        );
      })}
    </ol>
  );
}
