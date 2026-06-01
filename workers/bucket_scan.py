"""Bucket-scan ingestion channel — polls storage and ingests new files as cases.

Periodically lists the storage backend and ingests files that do not yet have a
Document row. Files written by the other channels already have a Document (keyed by
content hash), so they are skipped by the dedup check inside ingest_document — only
files dropped into the bucket out-of-band create new cases.

Registered as an arq cron job (see WorkerSettings.cron_jobs in workers/pipeline.py).
Org attribution: bucket files carry no tenant, so they are ingested into the default
org for the dev/demo flow.
"""

from __future__ import annotations

import logging
import mimetypes
import os
from typing import Any

from apps.api.config import settings
from apps.api.database import async_session_factory
from apps.api.seed import DEFAULT_ORG_ID
from apps.api.services.ingestion import ingest_document
from packages.storage.factory import get_storage

logger = logging.getLogger(__name__)


async def scan_bucket(ctx: dict[str, Any]) -> int:
    """Ingest any new files found in storage. Returns the count of new cases."""
    storage = get_storage(
        settings.storage_backend,
        settings.storage_local_dir,
        settings.storage_gcs_bucket,
        settings.storage_gcs_prefix,
    )
    try:
        paths = storage.list()
    except Exception as exc:  # storage unavailable — log and move on
        logger.warning("bucket_scan.list_failed error=%s", exc)
        return 0

    new_cases = 0
    async with async_session_factory() as session:
        for path in paths:
            try:
                content = storage.get(path)
            except Exception:
                continue
            if not content:
                continue
            filename = os.path.basename(path)
            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

            result = await ingest_document(
                session,
                DEFAULT_ORG_ID,
                filename=filename,
                content_type=content_type,
                content=content,
                channel="bucket",
                existing_storage_path=path,  # already in storage — do not re-put
            )
            if result.is_duplicate:
                continue
            new_cases += 1
            try:
                await ctx["redis"].enqueue_job("process_document", result.case_id)
            except Exception:
                logger.warning("bucket_scan.enqueue_failed case_id=%s", result.case_id)

    if new_cases:
        logger.info("bucket_scan.ingested new_cases=%d", new_cases)
    return new_cases
