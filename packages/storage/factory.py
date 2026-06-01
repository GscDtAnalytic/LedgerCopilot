"""Storage backend factory.

Returns a cached backend instance. Add new backends here when a new target lands —
callers do not change, only the backend registry grows.
"""

from __future__ import annotations

from functools import lru_cache

from packages.storage.backend import StorageBackend


@lru_cache(maxsize=1)
def _make_backend(
    backend: str,
    local_dir: str,
    gcs_bucket: str,
    gcs_prefix: str,
) -> StorageBackend:
    if backend == "local":
        from packages.storage.local import LocalBackend

        return LocalBackend(local_dir)
    if backend == "gcs":
        from packages.storage.gcs import GcsBackend

        return GcsBackend(gcs_bucket, gcs_prefix)
    raise ValueError(f"Unknown storage backend: {backend!r}. Supported: 'local', 'gcs'.")


def get_storage(
    backend: str = "local",
    local_dir: str = "/tmp/ledgercopilot/uploads",
    gcs_bucket: str = "",
    gcs_prefix: str = "",
) -> StorageBackend:
    """Return the configured storage backend (cached after first call)."""
    return _make_backend(backend, local_dir, gcs_bucket, gcs_prefix)
