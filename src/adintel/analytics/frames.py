"""Load metrics into pandas and compute the facts that agents and reports are allowed to use."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from adintel.storage.tenant_repo import TenantScopedRepo

COLUMNS = ["date", "platform", "campaign_id", "campaign_name", "entity_id", "entity_name", "impressions", "clicks",
           "spend", "conversions", "revenue", "daily_budget", "currency_original"]


def load_frame(repo: TenantScopedRepo, brand_id: str, start: date, end: date,
               platforms: list[str] | None = None) -> pd.DataFrame:
    flt: dict[str, Any] = {"brand_id": brand_id, "date": {"$gte": start.isoformat(), "$lte": end.isoformat()}}
    if platforms:
        flt["platform"] = {"$in": platforms}
    rows = repo.find(flt, sort=[("date", 1), ("platform", 1), ("entity_id", 1)])
    df = pd.DataFrame(rows, columns=COLUMNS) if rows else pd.DataFrame(columns=COLUMNS)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
        for c in ("impressions", "clicks", "spend", "conversions", "revenue"):
            df[c] = pd.to_numeric(df[c])
    return df


def ratios(spend: float, clicks: float, impressions: float, conversions: float, revenue: float) -> dict[str, Any]:
    return {
        "cpa": round(spend / conversions, 2) if conversions else None,
        "roas": round(revenue / spend, 2) if spend else None,
        "ctr_pct": round(100 * clicks / impressions, 2) if impressions else None,
        "cpc": round(spend / clicks, 2) if clicks else None,
    }


def totals(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {"spend": 0.0, "clicks": 0, "impressions": 0, "conversions": 0.0, "revenue": 0.0,
                "cpa": None, "roas": None, "ctr_pct": None, "cpc": None}
    s = float(df["spend"].sum())
    c = float(df["clicks"].sum())
    i = float(df["impressions"].sum())
    v = float(df["conversions"].sum())
    r = float(df["revenue"].sum())
    return {"spend": round(s, 2), "clicks": int(c), "impressions": int(i), "conversions": round(v, 1),
            "revenue": round(r, 2), **ratios(s, c, i, v, r)}


def pct_change(new: float | None, old: float | None) -> float | None:
    if new is None or old in (None, 0):
        return None
    return round(100 * (new - old) / old, 1)


def period_summary(df: pd.DataFrame, start: date, end: date) -> dict[str, Any]:
    """Totals for the period, the prior period of equal length, and per platform."""
    length = (end - start).days + 1
    prev_start, prev_end = start - timedelta(days=length), start - timedelta(days=1)
    cur = df[(df["date"] >= start) & (df["date"] <= end)] if not df.empty else df
    prev = df[(df["date"] >= prev_start) & (df["date"] <= prev_end)] if not df.empty else df
    t_cur, t_prev = totals(cur), totals(prev)
    changes = {f"{k}_change_pct": pct_change(t_cur[k], t_prev[k]) for k in ("spend", "conversions", "revenue", "cpa",
                                                                            "roas")}
    by_platform = {}
    if not cur.empty:
        for p, g in cur.groupby("platform"):
            by_platform[str(p)] = totals(g)
    return {"period_start": start.isoformat(), "period_end": end.isoformat(), "current": t_cur,
            "previous": t_prev, "changes": changes, "by_platform": by_platform}


def campaign_daily(df: pd.DataFrame) -> pd.DataFrame:
    """Daily campaign-level aggregates with derived metrics (the anomaly detector's input)."""
    if df.empty:
        return df
    g = (df.groupby(["platform", "campaign_id", "campaign_name", "date"], as_index=False)
         [["impressions", "clicks", "spend", "conversions", "revenue"]].sum())
    with np.errstate(divide="ignore", invalid="ignore"):
        g["cpa"] = np.where(g["conversions"] > 0, g["spend"] / g["conversions"], np.nan)
        g["roas"] = np.where(g["spend"] > 0, g["revenue"] / g["spend"], np.nan)
        g["ctr"] = np.where(g["impressions"] > 0, g["clicks"] / g["impressions"], np.nan)
    return g.sort_values(["platform", "campaign_id", "date"]).reset_index(drop=True)
