"""Encryption at rest for the local secret store (stand-in for KMS-encrypted Secrets Manager).

* AES-256-GCM, one random 96-bit nonce per file, the secret reference
  (``adintel/<tenant>/<platform>/<scope>``) as associated data — so an encrypted file copied to another
  tenant's or scope's path fails to decrypt instead of being accepted.
* **One key per scope.** ``read`` and ``write`` credentials are encrypted with different keys. Only the
  executor is given the write key (its own key file or env var), which turns the process-role policy into
  a cryptographic boundary: a compromised agent worker that can read the disk still cannot decrypt a
  credential that spends money.
* Keys: ``ADINTEL_SECRETS_KEY_READ`` / ``ADINTEL_SECRETS_KEY_WRITE`` (base64url, 32 bytes) or files
  ``<secrets_dir>/.keys/<scope>.key`` that must be private to the user (mode 0600).
"""

from __future__ import annotations

import base64
import json
import os
import secrets as pysecrets
import stat
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from adintel.core.errors import AuthError

SUFFIX = ".json.enc"


def generate_key() -> str:
    return base64.urlsafe_b64encode(AESGCM.generate_key(bit_length=256)).decode()


def load_key(root: Path, scope: str) -> bytes | None:
    env = os.environ.get(f"ADINTEL_SECRETS_KEY_{scope.upper()}")
    if env:
        raw = env
    else:
        path = root / ".keys" / f"{scope}.key"
        if not path.exists():
            return None
        if path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise AuthError(f"{path} must be readable by its owner only (chmod 600)")
        raw = path.read_text().strip()
    key = base64.urlsafe_b64decode(raw.encode())
    if len(key) != 32:
        raise AuthError(f"secrets key for scope {scope!r} must be 32 bytes")
    return key


def encrypt(key: bytes, ref: str, values: dict[str, Any]) -> str:
    nonce = pysecrets.token_bytes(12)
    ct = AESGCM(key).encrypt(nonce, json.dumps(values).encode(), ref.encode())
    return json.dumps(
        {
            "v": 1,
            "alg": "AES-256-GCM",
            "ref": ref,
            "nonce": base64.b64encode(nonce).decode(),
            "ct": base64.b64encode(ct).decode(),
        }
    )


def decrypt(key: bytes, ref: str, blob: str) -> dict[str, Any]:
    doc = json.loads(blob)
    try:
        plain = AESGCM(key).decrypt(base64.b64decode(doc["nonce"]), base64.b64decode(doc["ct"]), ref.encode())
    except Exception as exc:
        raise AuthError(f"cannot decrypt {ref}: wrong key, wrong location or tampered file") from exc
    values: dict[str, Any] = json.loads(plain)
    return values
