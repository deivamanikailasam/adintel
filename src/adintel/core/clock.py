"""Injectable clock so tests, replays and golden runs are deterministic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


class Clock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock(Clock):
    """A clock that only moves when told to."""

    def __init__(self, at: datetime) -> None:
        self._now = at if at.tzinfo else at.replace(tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs: float) -> None:
        self._now = self._now + timedelta(**kwargs)


_clock: Clock = Clock()


def get_clock() -> Clock:
    return _clock


def set_clock(clock: Clock) -> None:
    global _clock
    _clock = clock


def utcnow() -> datetime:
    return _clock.now()
