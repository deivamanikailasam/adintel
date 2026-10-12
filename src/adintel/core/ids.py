"""Identifier helpers. Prefixed IDs make logs and audit entries self-describing."""

from __future__ import annotations

import uuid


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"
