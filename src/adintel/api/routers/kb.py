from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from adintel.api.deps import ANY_STAFF, APPROVERS, check_brand, db, require
from adintel.audit import AuditLog
from adintel.core.ids import new_id
from adintel.domain.enums import AuditAction
from adintel.rag.indexer import DOC_TYPES, index_document
from adintel.security.auth import Principal
from adintel.storage.base import Database
from adintel.storage.tenant_repo import TenantScopedRepo

router = APIRouter(tags=["knowledge base"])
MAX_DOC_CHARS = 200_000


class Doc(BaseModel):
    title: str = Field(max_length=200)
    text: str
    doc_type: str
    brand_id: str = "*"
    vertical: str = "general"


@router.post("/kb/documents", status_code=201)
def upload(body: Doc, p: Principal = Depends(require(*APPROVERS)), database: Database = Depends(db)) -> dict[str, Any]:
    """Uploads are authenticated, sanitised, flagged for injection markers and audit-logged."""
    if body.doc_type not in DOC_TYPES:
        raise HTTPException(422, f"doc_type must be one of {DOC_TYPES}")
    if len(body.text) > MAX_DOC_CHARS:
        raise HTTPException(413, "document too large")
    if body.brand_id != "*":
        check_brand(p, body.brand_id)
    doc_id = new_id("doc")
    chunks = index_document(database, p.tenant_id, doc_id=doc_id, title=body.title, text=body.text,
                            doc_type=body.doc_type, brand_id=body.brand_id, vertical=body.vertical,
                            source=f"upload:{p.user_id}")
    flagged = sorted({m for c in chunks for m in c["injection_markers"]})
    AuditLog(database, p.tenant_id).append(AuditAction.DATA_ACCESS, actor_type="human", actor_id=p.user_id,
                                           subject_type="kb_document", subject_id=doc_id,
                                           details={"op": "upload", "chunks": len(chunks), "flags": flagged})
    return {"doc_id": doc_id, "chunks": len(chunks), "injection_markers": flagged}


@router.get("/kb/documents")
def list_docs(p: Principal = Depends(require(*ANY_STAFF)), database: Database = Depends(db)) -> list[dict[str, Any]]:
    rows = TenantScopedRepo(database, "kb_chunks", p.tenant_id).find({"is_active": True}, projection={"embedding": 0})
    seen: dict[str, dict[str, Any]] = {}
    for r in rows:
        seen.setdefault(r["doc_id"], {"doc_id": r["doc_id"], "title": r["doc_title"], "doc_type": r["doc_type"],
                                      "brand_id": r["brand_id"], "chunks": 0})["chunks"] += 1
    return sorted(seen.values(), key=lambda d: d["title"])
