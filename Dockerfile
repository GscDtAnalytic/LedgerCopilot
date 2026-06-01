# Python image — serves both the FastAPI API and the arq worker (same codebase,
# different start command, selected by the Cloud Run service). Multi-stage build
# with uv for reproducible, lockfile-pinned dependencies.
#
# Build (from repo root):
#   docker build -t ledgercopilot-api .
# Run the API:
#   docker run -e PORT=8080 ledgercopilot-api
# Run the worker (Cloud Run overrides the command):
#   docker run ledgercopilot-api python -m workers.serve

# ── builder ──────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Resolve and install dependencies first (cached layer — changes only when the
# lockfile changes), then the project itself.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ── runtime ──────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user (Docker best practice — never run as root in prod).
RUN useradd --create-home --uid 1000 app

WORKDIR /app

# Bring the resolved virtualenv + source from the builder. Owned by the app user.
COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

USER app
EXPOSE 8080

# Default command = API. Cloud Run's worker service overrides this with
# `python -m workers.serve`, and the migration job with `alembic upgrade head`.
CMD ["sh", "-c", "uvicorn apps.api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
