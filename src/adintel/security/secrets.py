"""Secret store with per-process scope (local stand-in for AWS Secrets Manager + IAM task roles).

* Platform credentials have two scopes: ``read`` (ingestion, live-state checks) and ``write``
  (ad-platform mutations).
* The **process role** (``ADINTEL_PROCESS_ROLE``) decides what may be read: only the ``executor`` can
  read ``write`` credentials. The agent worker can call models but cannot read write-credentials, so a
  compromised worker (e.g. via prompt injection) still cannot spend a client's money.
* Agents never hold credentials; connectors fetch them at the boundary. Every access is logged.

Files: ``secrets/<tenant_id>/<platform>.<scope>.json``. In synthetic-connector mode a missing file is
replaced by a synthetic credential — **the scope policy is still enforced**.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from adintel.config import get_settings
from adintel.core.clock import utcnow
from adintel.core.errors import AuthError

log = logging.getLogger(__name__)

POLICY: dict[str, set[str]] = {
    "api": {"read"},  # approval-time live-state re-check (check 7); never write
    "worker": {"read"},
    "executor": {"read", "write"},
    "scheduler": set(),
    "cli": {"read", "write"},  # operator tooling (seed, demo); audited
    "test": {"read", "write"},
}


def process_role() -> str:
    return os.environ.get("ADINTEL_PROCESS_ROLE", "cli" if get_settings().env in ("local", "test") else "api")


@dataclass(frozen=True)
class Credential:
    tenant_id: str
    platform: str
    scope: str
    secret_ref: str
    values: dict[str, str]
    synthetic: bool = False

    def __repr__(self) -> str:  # never print secret values
        return f"Credential({self.tenant_id}/{self.platform}/{self.scope}, synthetic={self.synthetic})"


class SecretStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or get_settings().secrets_dir)

    def _log(self, tenant_id: str, ref: str, scope: str, allowed: bool) -> None:
        try:
            from adintel.storage import get_database
            from adintel.storage.tenant_repo import SystemRepo

            SystemRepo(get_database(), "secret_access_log", purpose="secret access audit").insert(
                {"tenant_id": tenant_id, "secret_ref": ref, "scope": scope, "role": process_role(),
                 "allowed": allowed, "at": utcnow().isoformat()})
        except Exception:  # noqa: BLE001
            log.exception("secret_access_log_failed")

    def get(self, tenant_id: str, platform: str, scope: str) -> Credential:
        role = process_role()
        ref = f"adintel/{tenant_id}/{platform}/{scope}"
        if scope not in POLICY.get(role, set()):
            self._log(tenant_id, ref, scope, False)
            log.error("secret_access_denied", extra={"role": role, "secret_ref": ref})
            raise AuthError(f"process role {role!r} may not read {scope!r} credentials")
        path = self.root / tenant_id / f"{platform}.{scope}.json"
        self._log(tenant_id, ref, scope, True)
        if path.exists():
            return Credential(tenant_id, platform, scope, ref, json.loads(path.read_text()))
        if get_settings().connectors == "synthetic":
            return Credential(tenant_id, platform, scope, ref, {"token": f"synthetic-{scope}"}, synthetic=True)
        raise AuthError(f"no {scope} credential for {tenant_id}/{platform}")
