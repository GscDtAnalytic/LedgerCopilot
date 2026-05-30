"""Production guards in apps.api.config.Settings.

secret_key signs every JWT, so production must not boot with the dev default
or a weak key. These tests pin that fail-fast behavior.
"""

from __future__ import annotations

import pytest

from apps.api.config import _DEV_SECRET_KEY, _MIN_SECRET_LEN, Settings


def test_production_rejects_dev_secret() -> None:
    with pytest.raises(ValueError, match="dev default"):
        Settings(environment="production", secret_key=_DEV_SECRET_KEY)


def test_production_rejects_short_secret() -> None:
    with pytest.raises(ValueError, match="at least"):
        Settings(environment="production", secret_key="x" * (_MIN_SECRET_LEN - 1))


def test_production_accepts_strong_secret() -> None:
    s = Settings(environment="production", secret_key="x" * _MIN_SECRET_LEN)
    assert s.environment == "production"


def test_development_allows_dev_secret() -> None:
    # No guard outside production: the dev default keeps local setup one command.
    s = Settings(environment="development", secret_key=_DEV_SECRET_KEY)
    assert s.secret_key == _DEV_SECRET_KEY
