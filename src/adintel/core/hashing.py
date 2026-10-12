"""Canonical hashing helpers.

Hashes are used for idempotency keys, checkpoint integrity, prompt/response archiving, entity
snapshots and the audit chain. They must be stable across processes and Python versions, so all
structured data is serialised canonically (sorted keys, no whitespace, ISO dates).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


def _default(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    if isinstance(obj, set | frozenset):
        return sorted(obj)
    raise TypeError(f"not canonically serialisable: {type(obj)!r}")


def canonical_json(data: Any) -> str:
    """Serialise ``data`` deterministically."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=_default, ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_obj(data: Any) -> str:
    return sha256_text(canonical_json(data))


def hmac_sign(key: str, data: Any) -> str:
    """HMAC-SHA256 over the canonical form of ``data``."""
    return hmac.new(key.encode("utf-8"), canonical_json(data).encode("utf-8"), hashlib.sha256).hexdigest()


def hmac_verify(key: str, data: Any, signature: str) -> bool:
    return hmac.compare_digest(hmac_sign(key, data), signature)
