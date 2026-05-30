"""Tests for LocalBackend and the storage factory."""

from __future__ import annotations

import pytest

from packages.storage.factory import _make_backend, get_storage
from packages.storage.local import LocalBackend


def test_local_put_get(tmp_path):
    backend = LocalBackend(base_dir=str(tmp_path))
    data = b"NF-e content"
    key = backend.put("invoice.xml", data)
    assert backend.get(key) == data


def test_local_put_immutable(tmp_path):
    """put() must not overwrite existing file (bronze immutability)."""
    backend = LocalBackend(base_dir=str(tmp_path))
    original = b"original bytes"
    key = backend.put("doc.pdf", original)
    backend.put("doc.pdf", b"new bytes -- must be ignored")
    assert backend.get(key) == original


def test_local_exists(tmp_path):
    backend = LocalBackend(base_dir=str(tmp_path))
    key = backend.put("x.txt", b"hi")
    assert backend.exists(key)
    assert not backend.exists(str(tmp_path / "missing.txt"))


def test_factory_returns_local(tmp_path):
    _make_backend.cache_clear()
    storage = get_storage("local", str(tmp_path))
    assert isinstance(storage, LocalBackend)


def test_factory_unknown_backend():
    _make_backend.cache_clear()
    with pytest.raises(ValueError, match="Unknown storage backend"):
        get_storage("s3_not_yet", "/tmp")
