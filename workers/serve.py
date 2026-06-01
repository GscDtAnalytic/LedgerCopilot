"""Cloud Run entrypoint for the arq pipeline worker.

Cloud Run *services* must answer HTTP health checks on ``$PORT``, but arq is a
Redis queue consumer with no HTTP surface. This shim runs a minimal liveness
server in a background daemon thread and the arq worker in the main process.

Deployed with ``min-instances=1`` and CPU always allocated (``--no-cpu-throttling``)
so the background consume loop keeps draining the queue even with zero inbound
requests. Run locally with: ``python -m workers.serve`` (or keep using
``uv run arq workers.pipeline.WorkerSettings`` for plain local dev).
"""

from __future__ import annotations

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from arq import run_worker

from workers.pipeline import WorkerSettings


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # http.server dispatch method
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args: object) -> None:
        # Silence per-request logging; arq emits the meaningful logs.
        return


def _serve_health() -> None:
    port = int(os.environ.get("PORT", "8080"))
    HTTPServer(("0.0.0.0", port), _HealthHandler).serve_forever()


def main() -> None:
    threading.Thread(target=_serve_health, daemon=True).start()
    run_worker(WorkerSettings)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
