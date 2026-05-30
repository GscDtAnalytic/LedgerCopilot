/**
 * Design tokens — the single source of truth for the LedgerCopilot UI.
 *
 * Components consume these tokens via the CSS variables in `app/globals.css`
 * and Tailwind theme keys — never raw values.
 *
 * Naming is semantic (what a value means, not what color it is) so theming
 * (light/dark, high-contrast) is a matter of remapping CSS variables.
 */

export const motion = {
  /** Durations in ms. Calm tech: motion confirms, it does not perform. */
  duration: {
    instant: 80,
    fast: 140,
    base: 220,
    slow: 360,
  },
  easing: {
    standard: "cubic-bezier(0.2, 0, 0, 1)",
    emphasized: "cubic-bezier(0.2, 0, 0, 1.2)",
    exit: "cubic-bezier(0.4, 0, 1, 1)",
  },
} as const;

export const radius = {
  sm: "0.375rem",
  md: "0.625rem",
  lg: "1rem",
  full: "9999px",
} as const;

/**
 * Haptic / feedback "language" shared across visual, optional sound and touch.
 * Success, attention, and error have distinct patterns wherever the Vibration API
 * is supported — consistent across visual, audio, and tactile channels.
 */
export const feedback = {
  success: { tone: "success", vibrate: [12] },
  attention: { tone: "warning", vibrate: [10, 40, 10] },
  error: { tone: "danger", vibrate: [24, 40, 24] },
} as const;

/** Semantic color *roles*. Concrete values live as CSS variables in globals.css. */
export const colorRoles = [
  "background",
  "surface",
  "surface-translucent",
  "foreground",
  "muted",
  "border",
  "focus",
  "primary",
  "primary-foreground",
  "success",
  "warning",
  "danger",
] as const;

export type ColorRole = (typeof colorRoles)[number];
export type FeedbackKind = keyof typeof feedback;
