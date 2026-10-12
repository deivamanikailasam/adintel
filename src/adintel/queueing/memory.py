from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from typing import Any

from adintel.queueing.base import Message, Queue


class MemoryQueue(Queue):
    def __init__(self, name: str, *, visibility: float, max_receives: int) -> None:
        self.name = name
        self.visibility = visibility
        self.max_receives = max_receives
        self._ready: deque[tuple[str, dict[str, Any], int]] = deque()
        self._inflight: dict[str, tuple[str, dict[str, Any], int, float]] = {}
        self._dlq: list[dict[str, Any]] = []
        self._dedup: set[str] = set()
        self._cv = threading.Condition()

    def _reap(self) -> None:
        now = time.monotonic()
        for receipt, (mid, body, n, deadline) in list(self._inflight.items()):
            if deadline <= now:
                del self._inflight[receipt]
                self._requeue(mid, body, n)

    def _requeue(self, mid: str, body: dict[str, Any], n: int) -> None:
        if n >= self.max_receives:
            self._dlq.append({"id": mid, "body": body, "receives": n})
        else:
            self._ready.appendleft((mid, body, n))

    def send(self, body: dict[str, Any], *, dedup_id: str | None = None) -> str:
        with self._cv:
            if dedup_id:
                if dedup_id in self._dedup:
                    return dedup_id
                self._dedup.add(dedup_id)
            mid = dedup_id or uuid.uuid4().hex
            self._ready.append((mid, body, 0))
            self._cv.notify()
            return mid

    def receive(self, *, wait_seconds: float = 1.0) -> Message | None:
        deadline = time.monotonic() + wait_seconds
        with self._cv:
            while True:
                self._reap()
                if self._ready:
                    mid, body, n = self._ready.popleft()
                    receipt = uuid.uuid4().hex
                    self._inflight[receipt] = (mid, body, n + 1, time.monotonic() + self.visibility)
                    return Message(mid, body, receipt, n + 1)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._cv.wait(min(remaining, 0.2))

    def ack(self, msg: Message) -> None:
        with self._cv:
            self._inflight.pop(msg.receipt, None)

    def nack(self, msg: Message) -> None:
        with self._cv:
            item = self._inflight.pop(msg.receipt, None)
            if item:
                self._requeue(item[0], item[1], item[2])
                self._cv.notify()

    def depth(self) -> int:
        with self._cv:
            return len(self._ready)

    def dlq_depth(self) -> int:
        return len(self._dlq)

    def dlq_messages(self) -> list[dict[str, Any]]:
        return list(self._dlq)
