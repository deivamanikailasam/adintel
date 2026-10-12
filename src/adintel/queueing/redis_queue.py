"""Redis queue (local stand-in for SQS): a ready list, an in-flight sorted set scored by visibility
deadline, a receive counter, a DLQ list and a dedup set. Enable AOF in Redis for durability."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from adintel.queueing.base import Message, Queue

_RECEIVE = """
local now = tonumber(ARGV[1])
local vis = tonumber(ARGV[2])
local maxr = tonumber(ARGV[3])
-- move expired in-flight messages back to ready (or the DLQ)
local expired = redis.call('ZRANGEBYSCORE', KEYS[2], '-inf', now)
for _, mid in ipairs(expired) do
  redis.call('ZREM', KEYS[2], mid)
  local n = tonumber(redis.call('HGET', KEYS[4], mid) or '0')
  if n >= maxr then redis.call('RPUSH', KEYS[5], mid) else redis.call('LPUSH', KEYS[1], mid) end
end
local mid = redis.call('RPOP', KEYS[1])
if not mid then return nil end
local n = redis.call('HINCRBY', KEYS[4], mid, 1)
redis.call('ZADD', KEYS[2], now + vis, mid)
return {mid, redis.call('HGET', KEYS[3], mid), n}
"""


class RedisQueue(Queue):
    def __init__(self, name: str, url: str, *, visibility: float, max_receives: int, fifo: bool) -> None:
        import redis

        self.name = name
        self._r: Any = redis.Redis.from_url(url, decode_responses=True)
        self.visibility = visibility
        self.max_receives = max_receives
        self.fifo = fifo
        p = f"adintel:q:{name}"
        self._keys = [f"{p}:ready", f"{p}:inflight", f"{p}:bodies", f"{p}:receives", f"{p}:dlq"]
        self._dedup = f"{p}:dedup"
        self._script = self._r.register_script(_RECEIVE)

    def send(self, body: dict[str, Any], *, dedup_id: str | None = None) -> str:
        mid = dedup_id or uuid.uuid4().hex
        if dedup_id and not self._r.set(f"{self._dedup}:{dedup_id}", 1, nx=True, ex=86400):
            return mid
        pipe = self._r.pipeline()
        pipe.hset(self._keys[2], mid, json.dumps(body, default=str))
        pipe.lpush(self._keys[0], mid)  # RPOP on receive → FIFO
        pipe.execute()
        return mid

    def receive(self, *, wait_seconds: float = 1.0) -> Message | None:
        deadline = time.monotonic() + wait_seconds
        while True:
            out = self._script(keys=self._keys, args=[time.time(), self.visibility, self.max_receives])
            if out:
                mid, body, n = out
                return Message(mid, json.loads(body), mid, int(n))
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.2)

    def ack(self, msg: Message) -> None:
        pipe = self._r.pipeline()
        pipe.zrem(self._keys[1], msg.receipt)
        pipe.hdel(self._keys[2], msg.receipt)
        pipe.hdel(self._keys[3], msg.receipt)
        pipe.execute()

    def nack(self, msg: Message) -> None:
        if self._r.zrem(self._keys[1], msg.receipt):
            self._r.rpush(self._keys[0], msg.receipt)

    def depth(self) -> int:
        return int(self._r.llen(self._keys[0]))

    def dlq_depth(self) -> int:
        return int(self._r.llen(self._keys[4]))

    def dlq_messages(self) -> list[dict[str, Any]]:
        ids = self._r.lrange(self._keys[4], 0, 100)
        return [{"id": i, "body": json.loads(self._r.hget(self._keys[2], i) or "{}")} for i in ids]
