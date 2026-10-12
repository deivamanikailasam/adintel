"""Report provenance: every released client report is signed, so anyone can check it is genuine.

A report travels by email, PDF and slide decks; once it leaves AdIntel nobody can tell whether a number was
edited or a whole page invented. Each released report therefore carries:

* ``sha256`` of its canonical content (title, sections, facts, model tier, adapter hash, system version…);
* an **Ed25519 signature** of that hash — asymmetric, so clients and auditors verify it **offline** with the
  public key (``GET /.well-known/adintel-report-key``) without trusting or contacting AdIntel;
* an **AI-assistance disclosure** (EU AI Act-style transparency) included in the signed content.

``GET /verify/reports/{report_id}`` (no login) answers "is this report genuine and unchanged since signing?"
by recomputing the hash from the stored report — which also detects a report edited in the database.

Key: ``ADINTEL_REPORT_SIGNING_KEY`` (base64 Ed25519 seed). Locally one is generated in ``var/keys`` on
first use; staging/production refuse to start without an explicit key.
"""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from adintel.config import get_settings
from adintel.core.clock import utcnow
from adintel.core.hashing import sha256_obj

SIGNED_FIELDS = (
    "report_id",
    "brand_id",
    "run_id",
    "title",
    "sections",
    "facts",
    "model_tier",
    "adapter_sha256",
    "deterministic_template",
    "system_version",
    "disclosure",
)


def disclosure(system_version: str) -> str:
    return (
        f"This report was drafted with AI assistance (AdIntel {system_version}). Every figure is taken directly "
        "from your advertising-platform data and checked automatically; any change to your campaigns is approved "
        "by a named account manager."
    )


def _key() -> Ed25519PrivateKey:
    s = get_settings()
    seed = s.report_signing_key
    if not seed:
        path = Path(s.var_dir) / "keys" / "report-signing.key"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(base64.b64encode(os.urandom(32)).decode())
            os.chmod(path, 0o600)
        seed = path.read_text().strip()
    return Ed25519PrivateKey.from_private_bytes(base64.b64decode(seed))


def public_key_pem() -> str:
    return (
        _key()
        .public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )


def key_id(pub: Ed25519PublicKey | None = None) -> str:
    raw = (pub or _key().public_key()).public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()[:16]


def content_hash(report: dict[str, Any]) -> str:
    return sha256_obj({k: report.get(k) for k in SIGNED_FIELDS})


def sign(report: dict[str, Any]) -> dict[str, Any]:
    digest = content_hash(report)
    return {
        "algorithm": "Ed25519",
        "sha256": digest,
        "signature": base64.b64encode(_key().sign(bytes.fromhex(digest))).decode(),
        "key_id": key_id(),
        "signed_at": utcnow().isoformat(),
        "signed_fields": list(SIGNED_FIELDS),
    }


def verify(report: dict[str, Any], public_pem: str | None = None) -> dict[str, Any]:
    prov = report.get("provenance") or {}
    if not prov:
        return {"valid": False, "reason": "report is not signed (held, or produced before signing existed)"}
    pub = serialization.load_pem_public_key(public_pem.encode()) if public_pem else _key().public_key()
    assert isinstance(pub, Ed25519PublicKey)
    digest = content_hash(report)
    if digest != prov.get("sha256"):
        return {"valid": False, "reason": "content changed after signing", "key_id": prov.get("key_id")}
    try:
        pub.verify(base64.b64decode(prov["signature"]), bytes.fromhex(digest))
    except Exception:
        return {"valid": False, "reason": "signature does not match this key", "key_id": prov.get("key_id")}
    return {"valid": True, "sha256": digest, "signed_at": prov.get("signed_at"), "key_id": prov.get("key_id")}
