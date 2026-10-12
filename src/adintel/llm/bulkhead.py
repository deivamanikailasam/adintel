"""Bulkheads: a cap on concurrent requests per model tier.

A local model server works through requests largely one at a time (mlx-lm, llama.cpp with one slot). When
the API, chat and several worker threads all call it at once, requests queue inside the server until they
hit their HTTP timeout — every caller fails slowly, together. A bulkhead makes saturation explicit and fast:
at most ``max_concurrency`` requests per tier are in flight from this process; a caller waits up to
``queue_timeout_seconds`` for a slot and otherwise gets ``TierSaturated`` (an ``LLMUnavailable``), which
the validation wrapper treats like an outage — next tier in the fallback chain, or a visible degradation.
The safety tier still fails closed.

Per process by design: the number of processes is known (api, worker, scheduler), so the total in flight
is bounded by ``processes × max_concurrency``; set the YAML values accordingly.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from adintel.core.errors import LLMUnavailable
from adintel.llm.types import TierConfig
from adintel.observability.metrics import LLM_BULKHEAD_REJECTIONS, LLM_IN_FLIGHT


class TierSaturated(LLMUnavailable):
    """Every slot for this tier is busy and none freed up within the queue timeout."""


_lock = threading.Lock()
_slots: dict[str, tuple[int, threading.BoundedSemaphore]] = {}


def _semaphore(tier: TierConfig) -> threading.BoundedSemaphore:
    key = f"{tier.base_url}|{tier.model_id}"  # tiers on the same server+model share its capacity
    with _lock:
        size, sem = _slots.get(key, (0, None))  # type: ignore[assignment]
        if sem is None or size != tier.max_concurrency:
            sem = threading.BoundedSemaphore(tier.max_concurrency)
            _slots[key] = (tier.max_concurrency, sem)
        return sem


@contextmanager
def slot(tier: TierConfig) -> Iterator[None]:
    sem = _semaphore(tier)
    if not sem.acquire(timeout=tier.queue_timeout_seconds):
        LLM_BULKHEAD_REJECTIONS.labels(tier=tier.name).inc()
        raise TierSaturated(
            f"tier {tier.name}: {tier.max_concurrency} request(s) already in flight; "
            f"no slot within {tier.queue_timeout_seconds:.0f}s"
        )
    LLM_IN_FLIGHT.labels(tier=tier.name).inc()
    try:
        yield
    finally:
        LLM_IN_FLIGHT.labels(tier=tier.name).dec()
        sem.release()


def reset() -> None:
    with _lock:
        _slots.clear()
