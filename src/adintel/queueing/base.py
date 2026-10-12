"""Queue interface with at-least-once delivery, visibility timeouts and dead-letter queues.

Redelivery is harmless because run starts are idempotent and executions are unique per recommendation.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class Message:
    id: str
    body: dict[str, Any]
    receipt: str
    receives: int


class Queue(ABC):
    name: str

    @abstractmethod
    def send(self, body: dict[str, Any], *, dedup_id: str | None = None) -> str: ...

    @abstractmethod
    def receive(self, *, wait_seconds: float = 1.0) -> Message | None: ...

    @abstractmethod
    def ack(self, msg: Message) -> None: ...

    @abstractmethod
    def nack(self, msg: Message) -> None:
        """Make the message visible again now (e.g. graceful shutdown)."""

    @abstractmethod
    def depth(self) -> int: ...

    @abstractmethod
    def dlq_depth(self) -> int: ...

    @abstractmethod
    def dlq_messages(self) -> list[dict[str, Any]]: ...


_queues: dict[str, Queue] = {}
_lock = threading.Lock()


def get_queue(name: str) -> Queue:
    from adintel.config import get_settings
    from adintel.queueing import MAX_RECEIVES, VISIBILITY

    with _lock:
        if name not in _queues:
            kind = get_settings().queue
            fifo = name == "executions"
            if kind == "redis":
                from adintel.queueing.redis_queue import RedisQueue

                _queues[name] = RedisQueue(name, get_settings().redis_url, visibility=VISIBILITY.get(name, 300.0),
                                           max_receives=MAX_RECEIVES, fifo=fifo)
            elif kind == "sqs":
                from adintel.queueing.sqs import SqsQueue

                _queues[name] = SqsQueue(name, fifo=fifo)
            else:
                from adintel.queueing.memory import MemoryQueue

                _queues[name] = MemoryQueue(name, visibility=VISIBILITY.get(name, 300.0), max_receives=MAX_RECEIVES)
        return _queues[name]


def reset_queues() -> None:
    with _lock:
        _queues.clear()
