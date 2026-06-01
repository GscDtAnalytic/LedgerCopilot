import path from "node:path";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Self-contained server bundle for a slim container image (apps/web/Dockerfile).
  output: "standalone",
  // Monorepo: trace workspace files from the repo root so the standalone output
  // bundles hoisted dependencies correctly.
  outputFileTracingRoot: path.join(import.meta.dirname, "../../"),
  // Server Components by default; Client Components only where there is interaction.
  experimental: {
    typedRoutes: true,
  },
};

export default nextConfig;
