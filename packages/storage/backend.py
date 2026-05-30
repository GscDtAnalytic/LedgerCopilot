"""StorageBackend — abstract interface for document storage.

The backend is responsible for storing and retrieving raw document bytes.
Callers use put/get; the concrete implementation decides where bytes live
(local filesystem in dev, GCS/S3 in prod).

Design: never overwrite — the bronze immutability principle
 means every document is written once and the original
is always retrievable for re-extraction with a better model.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class StorageBackend(ABC):
    @abstractmethod
    def put(self, filename: str, data: bytes) -> str:
        """Write data and return the canonical storage key/path.

        The returned value is stored in Document.storage_path and passed back
        to get() later — it is opaque to callers.
        Never overwrites an existing key (bronze immutability).
        """

    @abstractmethod
    def get(self, storage_path: str) -> bytes:
        """Retrieve bytes by the key previously returned by put()."""

    @abstractmethod
    def exists(self, storage_path: str) -> bool:
        """Return True if a key exists (used for idempotency checks)."""

    @abstractmethod
    def list(self) -> list[str]:
        """Return all storage keys currently present.

        Used by the bucket-scan ingestion channel to discover files dropped into
        storage out-of-band. Dedup against already-ingested files is the caller's
        responsibility (by content hash).
        """
