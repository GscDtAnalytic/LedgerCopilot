# Next.js (App Router) image — built from the REPO ROOT context so the pnpm
# workspace + root lockfile are available:
#   docker build -f apps/web/Dockerfile \
#     --build-arg NEXT_PUBLIC_API_URL=https://api.example.run.app -t ledgercopilot-web .
#
# NEXT_PUBLIC_API_URL is a build-time variable (baked into the client bundle), so
# the API URL must be known before this image is built — the deploy workflow
# deploys the API first, reads its URL, then builds the web image with it.

# ── deps ─────────────────────────────────────────────────────────────────────
FROM node:20-slim AS deps
RUN corepack enable
WORKDIR /app

# Workspace manifests first for a cached install layer.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile --filter web...

# ── build ────────────────────────────────────────────────────────────────────
FROM node:20-slim AS build
RUN corepack enable
WORKDIR /app

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_TELEMETRY_DISABLED=1

COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web ./apps/web

RUN pnpm --filter web build

# ── runtime ──────────────────────────────────────────────────────────────────
FROM node:20-slim AS runtime
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=8080 \
    HOSTNAME=0.0.0.0

# The node:20-slim base already ships a non-root `node` user (uid 1000).
# Next standalone output mirrors the workspace layout: server at apps/web/server.js
# with a hoisted node_modules at the root.
COPY --from=build --chown=node:node /app/apps/web/.next/standalone ./
COPY --from=build --chown=node:node /app/apps/web/.next/static ./apps/web/.next/static
# (no apps/web/public — the app ships no static assets dir; add a COPY here if one lands)

USER node
EXPOSE 8080

CMD ["node", "apps/web/server.js"]
