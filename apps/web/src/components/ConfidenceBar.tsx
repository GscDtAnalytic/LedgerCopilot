/**
 * ConfidenceBar — visual + numeric confidence indicator.
 *
 * Color and pattern together signal quality (§13.1: never color alone).
 * The aria-valuenow makes the value accessible to screen readers.
 */

import { confidenceColor, pct } from "@/lib/format";

interface Props {
  confidence: number;
  label: string;
}

export function ConfidenceBar({ confidence, label }: Props) {
  const color = confidenceColor(confidence);
  const pctVal = Math.round(confidence * 100);

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted">{label}</span>
        <span className={`font-medium ${color}`}>{pct(confidence)}</span>
      </div>
      <div
        className="h-1 w-full overflow-hidden rounded-full bg-border"
        role="progressbar"
        aria-valuenow={pctVal}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${label} confidence: ${pct(confidence)}`}
      >
        <div
          className={`h-full rounded-full transition-all duration-base ease-standard ${
            confidence >= 0.9
              ? "bg-success"
              : confidence >= 0.7
                ? "bg-warning"
                : "bg-danger"
          }`}
          style={{ width: `${pctVal}%` }}
        />
      </div>
    </div>
  );
}
