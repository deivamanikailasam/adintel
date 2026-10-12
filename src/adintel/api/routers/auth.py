from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from adintel.api.deps import db, principal
from adintel.config import get_settings
from adintel.domain.models import User
from adintel.security.auth import Principal, issue_token
from adintel.storage.base import Database
from adintel.storage.tenant_repo import SystemRepo

router = APIRouter(tags=["auth"])


class DevLogin(BaseModel):
    email: str


@router.post("/auth/dev-login")
def dev_login(body: DevLogin, database: Database = Depends(db)) -> dict[str, Any]:
    """Local-only login by email (seeded users). Disabled outside local/test; production uses Cognito."""
    s = get_settings()
    if not s.dev_login_enabled or s.env not in ("local", "test"):
        raise HTTPException(404, "not found")
    doc = SystemRepo(database, "users", purpose="dev login").find_one({"email": body.email})
    if doc is None:
        raise HTTPException(401, "unknown user")
    user = User.from_doc(doc)
    return {"access_token": issue_token(user), "token_type": "bearer", "user": user.model_dump(mode="json")}


@router.get("/me")
def me(p: Principal = Depends(principal)) -> dict[str, Any]:
    return {
        "user_id": p.user_id,
        "tenant_id": p.tenant_id,
        "email": p.email,
        "roles": sorted(p.roles),
        "brand_ids": list(p.brand_ids),
        "senior": p.senior,
    }
