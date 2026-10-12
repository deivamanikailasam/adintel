"""One shared Redis client for cross-process state (rate limits, semantic cache). Tests inject fakeredis."""

from __future__ import annotations

import threading
from typing import Any

_client: Any = None
_lock = threading.Lock()


def get_redis() -> Any:
    global _client
    with _lock:
        if _client is None:
            import redis

            from adintel.config import get_settings

            _client = redis.Redis.from_url(
                get_settings().redis_url, decode_responses=True, socket_timeout=2.0, socket_connect_timeout=2.0
            )
        return _client


def set_redis(client: Any) -> None:
    global _client
    with _lock:
        _client = client
