import type { Config } from "tailwindcss";

import { motion, radius } from "./src/design-system/tokens";

/**
 * Tailwind theme is wired to the design tokens. Colors resolve to CSS variables
 * (declared in app/globals.css) so light/dark/high-contrast are a remap, not a
 * rebuild. There is no loose CSS outside this system.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "rgb(var(--color-background) / <alpha-value>)",
        surface: "rgb(var(--color-surface) / <alpha-value>)",
        foreground: "rgb(var(--color-foreground) / <alpha-value>)",
        muted: "rgb(var(--color-muted) / <alpha-value>)",
        border: "rgb(var(--color-border) / <alpha-value>)",
        focus: "rgb(var(--color-focus) / <alpha-value>)",
        primary: {
          DEFAULT: "rgb(var(--color-primary) / <alpha-value>)",
          foreground: "rgb(var(--color-primary-foreground) / <alpha-value>)",
        },
        success: "rgb(var(--color-success) / <alpha-value>)",
        warning: "rgb(var(--color-warning) / <alpha-value>)",
        danger: "rgb(var(--color-danger) / <alpha-value>)",
      },
      borderRadius: {
        sm: radius.sm,
        md: radius.md,
        lg: radius.lg,
      },
      transitionDuration: {
        fast: `${motion.duration.fast}ms`,
        base: `${motion.duration.base}ms`,
        slow: `${motion.duration.slow}ms`,
      },
      transitionTimingFunction: {
        standard: motion.easing.standard,
        emphasized: motion.easing.emphasized,
      },
    },
  },
  plugins: [],
};

export default config;
