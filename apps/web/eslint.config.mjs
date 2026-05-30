import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

// Flat config (ESLint 9) replacing the deprecated `next lint` wrapper. FlatCompat
// loads the same eslintrc-style presets we used before, so behavior is unchanged:
// Next core-web-vitals + TypeScript rules, jsx-a11y recommended, and our one
// custom override. `next lint` is deprecated and removed in Next 16 — running the
// ESLint CLI directly keeps us forward-compatible.
const eslintConfig = [
  {
    ignores: [".next/**", "out/**", "build/**", "node_modules/**", "next-env.d.ts"],
  },
  ...compat.extends(
    "next/core-web-vitals",
    "next/typescript",
    "plugin:jsx-a11y/recommended",
  ),
  {
    rules: {
      "jsx-a11y/no-autofocus": "warn",
    },
  },
];

export default eslintConfig;
