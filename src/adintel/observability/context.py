"""Request/run context carried in contextvars so every log line and span gets the same IDs."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextvars import ContextVar
from typing import Any

_ctx: ContextVar[dict[str, Any] | None] = ContextVar("adintel_ctx", default=None)


def current() -> dict[str, Any]:
    return dict(_ctx.get() or {})


@contextlib.contextmanager
def bind(**values: Any) -> Iterator[None]:
    merged = {**current(), **{k: v for k, v in values.items() if v is not None}}
    token = _ctx.set(merged)
    try:
        yield
    finally:
        _ctx.reset(token)
