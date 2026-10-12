"""Public, unauthenticated report verification (provenance) — reveals validity only, never content."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from adintel.api.deps import db
from adintel.audit import provenance
from adintel.storage.base import Database
from adintel.storage.tenant_repo import SystemRepo

router = APIRouter(tags=["verify"])


@router.get("/.well-known/adintel-report-key", response_class=PlainTextResponse)
def report_public_key() -> str:
    """Ed25519 public key that verifies AdIntel report signatures offline."""
    return provenance.public_key_pem()


@router.get("/verify/reports/{report_id}")
def verify_report(report_id: str, database: Database = Depends(db)) -> dict[str, Any]:
    doc = SystemRepo(database, "reports", purpose="public report verification").find_one({"report_id": report_id})
    if doc is None:
        raise HTTPException(404, "unknown report")
    out = provenance.verify(doc)
    return {
        "report_id": report_id,
        **{k: v for k, v in out.items() if k in ("valid", "reason", "signed_at", "key_id", "sha256")},
    }
