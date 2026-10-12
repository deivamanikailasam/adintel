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
    from adintel.core.resilience import reset_breakers
    from adintel.llm.providers import set_provider_override
    from adintel.llm.providers.mock import MockProvider
    from adintel.llm.registry import reset_registry

    reset_breakers()
    import adintel.llm.semantic_cache as sc

    sc._cache = sc.SemanticCache()
    reset_registry()
    MockProvider.reset_shared()
    set_provider_override(None)
    yield
    reset_database()
    reset_settings_cache()


@pytest.fixture
def db():
    from adintel.storage import get_database

    return get_database()


@pytest.fixture
def mock_llm():
    from adintel.llm.providers import set_provider_override
    from adintel.llm.providers.mock import MockProvider

    m = MockProvider()
    set_provider_override(m)
    yield m
    set_provider_override(None)


@pytest.fixture(autouse=True)
def _fresh_queues():
    from adintel.queueing import reset_queues

    reset_queues()
    yield
    reset_queues()


@pytest.fixture
def fake_redis(monkeypatch):
    """Shared-state mode backed by fakeredis (same client for every 'process')."""
    import fakeredis

    import adintel.api.deps as deps
    import adintel.llm.semantic_cache as sc
    from adintel.config import reset_settings_cache
    from adintel.core.redis_client import set_redis
    from adintel.harness.admission import reset_limiters

    client = fakeredis.FakeRedis(decode_responses=True)
    set_redis(client)
    monkeypatch.setenv("ADINTEL_SHARED_STATE", "redis")
    reset_settings_cache()
    reset_limiters()
    deps._api_limiter = None
    sc._cache = None
    yield client
    set_redis(None)
    reset_limiters()
    deps._api_limiter = None
    sc._cache = None
