"""Resilience primitives shared by model providers and ad-platform connectors.

* ``CircuitBreaker`` — opens after 5 failures in 60 s, half-opens after 30 s (one trial call).
* ``retry_call`` — bounded retries with full jitter, only for errors declared transient.
"""

from __future__ import annotations

import random
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class CircuitOpen(Exception):
    pass


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        window_seconds: float = 60.0,
        reset_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.reset_seconds = reset_seconds
        self._clock = clock
        self._failures: deque[float] = deque()
        self._opened_at: float | None = None
        self._half_open_trial = False
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            return self._state()

    def _state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if self._clock() - self._opened_at >= self.reset_seconds:
            return "half_open"
        return "open"

    def before_call(self) -> None:
        with self._lock:
            st = self._state()
            if st == "open":
                raise CircuitOpen(self.name)
            if st == "half_open":
                if self._half_open_trial:
                    raise CircuitOpen(self.name)
                self._half_open_trial = True

    def record_success(self) -> None:
        with self._lock:
            self._failures.clear()
            self._opened_at = None
            self._half_open_trial = False

    def record_failure(self) -> None:
        with self._lock:
            now = self._clock()
            if self._state() == "half_open":
                self._opened_at = now
                self._half_open_trial = False
                return
            self._failures.append(now)
            while self._failures and now - self._failures[0] > self.window_seconds:
                self._failures.popleft()
            if len(self._failures) >= self.failure_threshold:
                self._opened_at = now


_breakers: dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def breaker(name: str) -> CircuitBreaker:
    with _breakers_lock:
        if name not in _breakers:
            _breakers[name] = CircuitBreaker(name)
        return _breakers[name]


def reset_breakers() -> None:
    with _breakers_lock:
        _breakers.clear()


def retry_call(
    fn: Callable[[], T],
    *,
    retries: int,
    transient: tuple[type[BaseException], ...],
    base_delay: float = 0.25,
    max_delay: float = 4.0,
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, BaseException], None] | None = None,
) -> T:
    """Call ``fn``; on a transient error wait ``uniform(0, min(max, base*2**n))`` and retry."""
    attempt = 0
    while True:
        try:
            return fn()
        except transient as exc:
            if attempt >= retries:
                raise
            if on_retry:
                on_retry(attempt + 1, exc)
            sleep(random.uniform(0, min(max_delay, base_delay * 2**attempt)))  # noqa: S311 - jitter, not crypto
            attempt += 1
