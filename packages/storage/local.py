"""Local filesystem storage backend — used in development.

Writes to a configurable base directory. Storage path == full filesystem path,
so existing Document rows that already hold a full path work without migration.

Bronze immutability: put() is a no-op when the file already exists, ensuring
the original bytes are never overwritten after first write.
"""

from __future__ import annotations

from pathlib import Path

from packages.storage.backend import StorageBackend


class LocalBackend(StorageBackend):
    def __init__(self, base_dir: str = "/tmp/ledgercopilot/uploads") -> None:
        self._base = Path(base_dir)

    def put(self, filename: str, data: bytes) -> str:
        self._base.mkdir(parents=True, exist_ok=True)
        dest = self._base / filename
        if not dest.exists():
            dest.write_bytes(data)
        return str(dest)

    def get(self, storage_path: str) -> bytes:
        return Path(storage_path).read_bytes()

    def exists(self, storage_path: str) -> bool:
        return Path(storage_path).exists()

    def list(self) -> list[str]:
        if not self._base.exists():
            return []
        return [str(p) for p in self._base.iterdir() if p.is_file()]
