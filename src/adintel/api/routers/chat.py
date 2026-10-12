from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from adintel.agents.chat import ChatService
from adintel.api.deps import ANY_STAFF, check_brand, db, require
from adintel.api.sse import sse
from adintel.security.auth import Principal
from adintel.storage.base import Database

router = APIRouter(tags=["chat"])


class ChatBody(BaseModel):
    brand_id: str
    session_id: str = Field(min_length=4, max_length=64)
    question: str = Field(min_length=1, max_length=2000)


@router.post("/chat")
def chat(
    body: ChatBody, p: Principal = Depends(require(*ANY_STAFF)), database: Database = Depends(db)
) -> StreamingResponse:
    check_brand(p, body.brand_id)
    svc = ChatService(database, p.tenant_id, body.brand_id, p.user_id)
    session = f"{p.user_id}:{body.session_id}"

    def gen() -> Iterator[str]:
        for ev in svc.ask(body.question, session):
            yield sse(ev, event=str(ev["type"]))

    return StreamingResponse(
        gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
