"""Indexing into ``kb_chunks`` (tenant-scoped). Re-indexing a document soft-deletes its old chunks."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from adintel.core.clock import utcnow
from adintel.core.hashing import sha256_text
from adintel.rag.chunking import Chunk, chunk_prose, chunk_report
from adintel.rag.embeddings import Embedder, get_embedder
from adintel.security.fencing import injection_markers, neutralise
from adintel.storage.base import Database
from adintel.storage.tenant_repo import TenantScopedRepo

DOC_TYPES = ("playbook", "guideline", "report", "incident", "narrative", "platform_doc")


def anonymise(text: str, names: list[str]) -> str:
    """Cross-brand incidents are stored as 'a client in this vertical'."""
    for n in sorted(names, key=len, reverse=True):
        if n:
            text = re.sub(re.escape(n), "a client in this vertical", text, flags=re.IGNORECASE)
    return text


def index_document(db: Database, tenant_id: str, *, doc_id: str, title: str, text: str, doc_type: str,
                   brand_id: str = "*", vertical: str = "general", doc_date: date | None = None,
                   source: str = "upload", anonymise_names: list[str] | None = None,
                   embedder: Embedder | None = None) -> list[dict[str, Any]]:
    if doc_type not in DOC_TYPES:
        raise ValueError(f"doc_type must be one of {DOC_TYPES}")
    emb = embedder or get_embedder()
    repo = TenantScopedRepo(db, "kb_chunks", tenant_id)
    # sanitise on upload: neutralise fence tags; flag (not silently drop) injection-looking content
    clean = neutralise(text)
    flagged = injection_markers(clean)
    anonymised = bool(anonymise_names)
    if anonymise_names:
        clean = anonymise(clean, anonymise_names)
        title = anonymise(title, anonymise_names)
    chunks: list[Chunk] = chunk_report(clean) if doc_type == "report" else (
        [Chunk(0, title, clean)] if doc_type == "narrative" else chunk_prose(clean))
    repo.soft_delete({"doc_id": doc_id, "is_active": True})
    vectors = emb.embed([f"{title}\n{c.heading}\n{c.text}" for c in chunks])
    docs = []
    for c, v in zip(chunks, vectors, strict=True):
        content_hash = sha256_text(c.text)
        doc = {"chunk_id": f"ch_{sha256_text(f'{doc_id}:{c.index}:{content_hash}')[:20]}", "doc_id": doc_id,
               "doc_title": title, "heading": c.heading, "doc_type": doc_type, "brand_id": brand_id,
               "vertical": vertical, "text": c.text, "embedding": v, "embedder_id": emb.model_id,
               "content_hash": content_hash, "is_active": True, "anonymised": anonymised,
               "injection_markers": flagged, "date": (doc_date or utcnow().date()).isoformat(), "source": source,
               "created_at": utcnow().isoformat()}
        repo.update_one({"chunk_id": doc["chunk_id"]}, {"$set": doc}, upsert=True)
        docs.append(doc)
    return docs
