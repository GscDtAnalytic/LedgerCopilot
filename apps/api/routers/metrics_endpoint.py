"""GET /metrics — Prometheus scrape endpoint.

Uses multiprocess collector when PROMETHEUS_MULTIPROC_DIR is set, letting
the arq worker and the API process share a single scrape surface.
Without the env var, only in-process metrics are exported.
"""

from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest, multiprocess

router = APIRouter(tags=["meta"])


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        data = generate_latest(registry)
    else:
        data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
