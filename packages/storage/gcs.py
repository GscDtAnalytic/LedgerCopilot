"""Google Cloud Storage backend — production document storage.

Cloud Run instances have an ephemeral, per-instance filesystem, so LocalBackend
cannot be used in production: bytes written by one instance are invisible to the
next and vanish on restart. GcsBackend persists the bronze layer in a GCS bucket
shared by every API/worker instance.

storage_path contract: put() returns the object key (blob name, prefix-relative
path included). That key is what gets persisted on Document rows, and get()/exists()
read it back from the same configured bucket. This mirrors LocalBackend, where the
returned path is what callers store and later read.

Bronze immutability: put() never overwrites an existing object — once the original
bytes land, they are frozen.
"""

from __future__ import annotations

from packages.storage.backend import StorageBackend


class GcsBackend(StorageBackend):
    def __init__(self, bucket: str, prefix: str = "") -> None:
        if not bucket:
            raise ValueError("GcsBackend requires a non-empty bucket name")
        # Lazy import: google-cloud-storage is a prod dependency; keep the package
        # importable in environments that never select the 'gcs' backend.
        from google.cloud import storage

        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket)
        # Application Default Credentials supply the service account on Cloud Run.
        self._prefix = prefix.strip("/")

    def _key(self, filename: str) -> str:
        return f"{self._prefix}/{filename}" if self._prefix else filename

    def put(self, filename: str, data: bytes) -> str:
        key = self._key(filename)
        blob = self._bucket.blob(key)
        # Bronze immutability: skip the write if the object already exists.
        if not blob.exists():
            blob.upload_from_string(data)
        return key

    def get(self, storage_path: str) -> bytes:
        return self._bucket.blob(storage_path).download_as_bytes()

    def exists(self, storage_path: str) -> bool:
        return self._bucket.blob(storage_path).exists()

    def list(self) -> list[str]:
        prefix = f"{self._prefix}/" if self._prefix else None
        return [blob.name for blob in self._client.list_blobs(self._bucket, prefix=prefix)]
