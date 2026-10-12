"""Shared fixtures: every test gets a fresh in-memory database and default settings."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("ADINTEL_ENV", "test")
os.environ.setdefault("ADINTEL_LOG_JSON", "false")
os.environ.setdefault("ADINTEL_LLM_PROVIDER", "mock")


@pytest.fixture(autouse=True)
def _fresh_state(tmp_path, monkeypatch):
    from adintel.config import reset_settings_cache
    from adintel.storage import reset_database

    monkeypatch.setenv("ADINTEL_VAR_DIR", str(tmp_path / "var"))
    monkeypatch.setenv("ADINTEL_SECRETS_DIR", str(tmp_path / "secrets"))
    reset_settings_cache()
    reset_database()
    yield
    reset_database()
    reset_settings_cache()


@pytest.fixture
def db():
    from adintel.storage import get_database

    return get_database()
