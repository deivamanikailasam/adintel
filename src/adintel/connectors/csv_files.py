"""Bring-your-own-data connector: run AdIntel on CSV exports instead of live ad-platform APIs.

The local alternative for anyone without API access (no developer tokens, no OAuth app approval yet) or
who wants to try AdIntel on real history before connecting anything.

Layout (``ADINTEL_CSV_DIR``, default ``data/import``)::

    <tenant_id>/<brand_id>/<platform>.csv      daily rows in the template below (one file per platform)
    <tenant_id>/<brand_id>/budgets.json        written by the executor: approved budgets applied so far
    <tenant_id>/<brand_id>/outbox.jsonl        written by the executor: changes for a human to apply

Template columns (header row required; ``adintel csv-template`` prints it)::

    date,campaign_id,campaign_name,entity_id,entity_name,entity_type,impressions,clicks,spend,
    conversions,revenue,daily_budget,currency

Amounts are in the account currency (``currency`` column, converted to USD like every connector).

**Reads** behave like any platform (missing file = platform unavailable → visible degradation).
**Writes** are *manual execution*: the executor still runs every check (signature, snapshot hash,
blackout, replay), then appends the exact change to ``outbox.jsonl`` for a person to make in the ad
platform's UI, and records the new budget so the next run and the reconciliation see it. Nothing is ever
sent to an ad platform from this connector.
"""

from __future__ import annotations

import csv
import hashlib
import json
import threading
from datetime import date
from pathlib import Path
from typing import Any

from adintel.config import get_settings
from adintel.connectors.base import PlatformConnector, RawFetch
from adintel.connectors.normalize import CANONICAL_FORMAT, _canonical_row
from adintel.core.clock import utcnow
from adintel.core.errors import AuthError, PlatformUnavailable
from adintel.domain.enums import Platform
from adintel.security.secrets import Credential

TEMPLATE_COLUMNS = [
    "date",
    "campaign_id",
    "campaign_name",
    "entity_id",
    "entity_name",
    "entity_type",
    "impressions",
    "clicks",
    "spend",
    "conversions",
    "revenue",
    "daily_budget",
    "currency",
]
_lock = threading.Lock()


class CsvConnector(PlatformConnector):
    def __init__(self, platform: Platform, root: Path | None = None) -> None:
        self.platform = platform
        self.root = Path(root or get_settings().csv_dir)

    def _dir(self, tenant_id: str, brand_id: str) -> Path:
        return self.root / tenant_id / brand_id

    def _rows(self, tenant_id: str, brand_id: str) -> list[dict[str, str]]:
        path = self._dir(tenant_id, brand_id) / f"{self.platform}.csv"
        if not path.exists():
            raise PlatformUnavailable(f"{self.platform}: no CSV export at {path}")
        with path.open(newline="", encoding="utf-8-sig") as f:  # -sig: Excel's BOM
            return list(csv.DictReader(f))

    def fetch(self, cred: Credential, brand_id: str, start: date, end: date) -> RawFetch:
        rows = [
            r for r in self._rows(cred.tenant_id, brand_id) if start.isoformat() <= r["date"].strip() <= end.isoformat()
        ]
        currencies = {(r.get("currency") or "USD").strip() or "USD" for r in rows}
        if len(currencies) > 1:
            raise PlatformUnavailable(f"{self.platform}: mixed currencies in one export {sorted(currencies)}")
        return RawFetch(
            platform=self.platform,
            rows=rows,
            account_currency=currencies.pop() if currencies else "USD",
            api_version=CANONICAL_FORMAT,
            meta={"source": "csv"},
        )

    def _budgets_path(self, tenant_id: str, brand_id: str) -> Path:
        return self._dir(tenant_id, brand_id) / "budgets.json"

    def _applied(self, tenant_id: str, brand_id: str) -> dict[str, Any]:
        p = self._budgets_path(tenant_id, brand_id)
        return json.loads(p.read_text()) if p.exists() else {}

    def get_entity(self, cred: Credential, brand_id: str, entity_id: str) -> dict[str, Any]:
        from adintel.connectors.scenarios import FX_TO_USD

        latest = None
        for r in self._rows(cred.tenant_id, brand_id):
            if r["entity_id"].strip() == entity_id and (latest is None or r["date"] > latest["date"]):
                latest = r
        if latest is None:
            raise PlatformUnavailable(f"{self.platform}: entity {entity_id} not in the CSV export")
        row = _canonical_row(latest)
        fx = FX_TO_USD.get((latest.get("currency") or "USD").strip() or "USD", 1.0)
        state = {
            "entity_id": entity_id,
            "name": row["entity_name"],
            "campaign_id": row["campaign_id"],
            "daily_budget": round((row["daily_budget"] or 0.0) * fx, 2),
            "status": "ACTIVE",
            "version": 1,
        }
        override = self._applied(cred.tenant_id, brand_id).get(f"{self.platform}/{entity_id}")
        return {**state, **override} if override else state

    def apply_change(self, cred: Credential, brand_id: str, change: dict[str, Any]) -> dict[str, Any]:
        if cred.scope != "write":
            raise AuthError("apply_change requires a write-scope credential")
        state = self.get_entity(cred, brand_id, change["entity_id"])
        new: dict[str, Any]
        if change["op"] == "set_daily_budget":
            new = {"daily_budget": round(float(change["daily_budget"]), 2)}
        elif change["op"] == "pause":
            new = {"status": "PAUSED"}
        else:
            raise ValueError(f"unsupported op {change['op']}")
        new["version"] = state["version"] + 1
        d = self._dir(cred.tenant_id, brand_id)
        request_id = hashlib.sha256(repr(change).encode()).hexdigest()[:16]
        with _lock:
            applied = self._applied(cred.tenant_id, brand_id)
            applied[f"{self.platform}/{change['entity_id']}"] = {
                **applied.get(f"{self.platform}/{change['entity_id']}", {}),
                **new,
            }
            self._budgets_path(cred.tenant_id, brand_id).write_text(json.dumps(applied, indent=2, sort_keys=True))
            with (d / "outbox.jsonl").open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "request_id": request_id,
                            "platform": str(self.platform),
                            "entity": state["name"],
                            **change,
                            "instruction": _instruction(state, change),
                            "at": utcnow().isoformat(),
                        }
                    )
                    + "\n"
                )
        return {
            "ok": True,
            "entity_id": change["entity_id"],
            "manual": True,
            "new_state": {**state, **new},
            "request_id": request_id,
        }


def _instruction(state: dict[str, Any], change: dict[str, Any]) -> str:
    if change["op"] == "pause":
        return f"Pause '{state['name']}' ({change['entity_id']})."
    return (
        f"Set the daily budget of '{state['name']}' ({change['entity_id']}) from "
        f"{change.get('previous')} to {change['daily_budget']} (USD; convert if the account uses another currency)."
    )


def export_sample(tenant_id: str, brand_id: str, start: date, end: date, out_root: Path) -> list[Path]:
    """Write the synthetic world for one brand as template CSVs — a working example of the format."""
    from adintel.connectors.normalize import normalise
    from adintel.connectors.scenarios import world_for
    from adintel.connectors.synthetic import SyntheticConnector

    cred = Credential(tenant_id, "any", "read", "sample", {}, synthetic=True)
    written = []
    out = out_root / tenant_id / brand_id
    out.mkdir(parents=True, exist_ok=True)
    for platform in world_for(brand_id).entities:
        conn = SyntheticConnector(platform)
        raw = conn.fetch(cred, brand_id, start, end)
        rows, _ = normalise(raw, tenant_id=tenant_id, brand_id=brand_id)
        path = out / f"{platform}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=TEMPLATE_COLUMNS)
            w.writeheader()
            for r in rows:
                live = conn.get_entity(cred, brand_id, r.entity_id)
                w.writerow(
                    {
                        **{k: getattr(r, k) for k in TEMPLATE_COLUMNS if k not in ("currency", "daily_budget")},
                        "date": r.date.isoformat(),
                        "daily_budget": r.daily_budget if r.daily_budget is not None else live["daily_budget"],
                        "currency": "USD",
                    }
                )
        written.append(path)
    return written
