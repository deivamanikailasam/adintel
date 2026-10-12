"""Anomaly Detection agent — **no LLM** (ADR D-06, L-05).

For every campaign × metric series over 180 days:

1. Fit STL (weekly period, robust) on the history *before* the evaluation window, so the anomaly
   cannot contaminate its own baseline.
2. Expected value for each recent day = last trend level + that weekday's seasonal component.
3. Prediction band = expected ± 3 × robust sigma (1.4826 × MAD of residuals), at least ±5%.
4. An anomaly is ≥ 3 consecutive most-recent days outside the band in the harmful direction
   (2 days if the deviation is ≥ 50%). Ratio metrics use 3-day rolling sums for the band and the raw
   ratio over the anomalous days for the reported value.
5. An Isolation Forest (fixed seed) on residual z-scores confirms or questions the finding.
6. Severity combines deviation and money at risk (materiality); brand suppressions (procedural memory,
   human-approved) are applied last.

Same input → same output: fixed settings, fixed seed, pinned libraries. The band that triggered a flag
is stored with the anomaly, so it can be shown to the client.
"""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from statsmodels.tsa.seasonal import STL

from adintel.agents.base import AgentContext
from adintel.analytics.frames import campaign_daily, load_frame
from adintel.core.hashing import sha256_obj
from adintel.domain.enums import AgentName, DegradationCode, Metric, Platform, Severity
from adintel.domain.models import Anomaly, BrandRules
from adintel.domain.state import RunState
from adintel.harness.degradation import degrade

log = logging.getLogger(__name__)

MIN_HISTORY_DAYS = 28
RATIO_WINDOW = 3  # ratio metrics use 3-day rolling sums: daily CPA on 4 conversions is noise, not signal
MIN_DAILY_CONVERSIONS = 5.0
EVAL_WINDOW = 7
MIN_CONSECUTIVE = 2
SUSTAINED_DAYS = 3
SHORT_SPIKE_MIN_DEV_PCT = 50.0
BAND_SIGMAS = 3.0
MIN_BAND_REL = 0.05
SEED = 42

# metric -> (harmful direction, materiality weight)
METRICS: dict[Metric, tuple[str, float]] = {
    Metric.CPA: ("up", 1.0),
    Metric.ROAS: ("down", 1.0),
    Metric.CONVERSIONS: ("down", 0.8),
    Metric.CTR: ("down", 0.2),
    Metric.SPEND: ("both", 0.5),
}
_COLUMN = {Metric.CPA: "cpa", Metric.ROAS: "roas", Metric.CONVERSIONS: "conversions", Metric.CTR: "ctr",
           Metric.SPEND: "spend"}


def _robust_sigma(x: np.ndarray) -> float:
    med = float(np.median(x))
    return 1.4826 * float(np.median(np.abs(x - med)))


def severity_for(deviation_pct: float, spend_at_risk: float) -> Severity:
    dev = abs(deviation_pct)
    if dev >= 100 and spend_at_risk >= 1000:
        return Severity.CRITICAL
    if (dev >= 40 and spend_at_risk >= 500) or (dev >= 25 and spend_at_risk >= 1000):
        return Severity.HIGH
    if dev >= 20 and spend_at_risk >= 100:
        return Severity.MEDIUM
    return Severity.LOW


def detect_series(dates: list[date], values: np.ndarray, end: date) -> dict[str, Any] | None:
    """Return the band evaluation for the evaluation window, or None if history is too short."""
    s = pd.Series(values, index=pd.to_datetime(dates)).sort_index()
    s = s[~s.index.duplicated()].asfreq("D").interpolate(limit=3).dropna()
    if len(s) < MIN_HISTORY_DAYS + EVAL_WINDOW:
        return None
    hist, recent = s.iloc[:-EVAL_WINDOW], s.iloc[-EVAL_WINDOW:]
    res = STL(hist, period=7, robust=True).fit()
    resid = np.asarray(res.resid)
    sigma = max(_robust_sigma(resid), 1e-9)
    trend_level = float(np.mean(np.asarray(res.trend)[-7:]))
    seasonal = pd.Series(np.asarray(res.seasonal), index=hist.index)
    by_weekday = seasonal.iloc[-28:].groupby(seasonal.iloc[-28:].index.weekday).mean()
    expected = np.array([trend_level + float(by_weekday.get(d.weekday(), 0.0)) for d in recent.index])
    half = np.maximum(BAND_SIGMAS * sigma, MIN_BAND_REL * np.abs(expected))
    lower, upper = expected - half, expected + half
    obs = recent.to_numpy()
    z_recent = (obs - expected) / sigma
    forest = IsolationForest(n_estimators=100, contamination=0.02, random_state=SEED)
    z_hist = (resid / sigma).reshape(-1, 1)
    forest.fit(z_hist)
    iso = forest.predict(z_recent.reshape(-1, 1))
    return {"dates": list(recent.index.date), "observed": obs, "expected": expected, "lower": lower, "upper": upper,
            "iso": iso}


def _trailing_run(flags: list[bool]) -> int:
    n = 0
    for f in reversed(flags):
        if not f:
            break
        n += 1
    return n


def _suppressed(rules: BrandRules | None, metric: Metric, entity_id: str, month: int) -> str | None:
    if not rules:
        return None
    for sup in rules.suppressions:
        if (sup.metric in (None, metric) and sup.entity_id in (None, entity_id)
                and sup.month in (None, month)):
            return sup.rule_id
    return None


def detect(df: pd.DataFrame, end: date, rules: BrandRules | None = None) -> tuple[list[Anomaly], int, list[str]]:
    """Return (anomalies, series_evaluated, suppressed_rule_ids)."""
    daily = campaign_daily(df)
    out: list[Anomaly] = []
    evaluated = 0
    suppressed: list[str] = []
    if daily.empty:
        return out, 0, suppressed
    for (platform, campaign_id, campaign_name), g in daily.groupby(["platform", "campaign_id", "campaign_name"]):
        g = g[g["date"] <= end].sort_values("date").reset_index(drop=True)
        roll = g[["spend", "conversions", "revenue", "clicks", "impressions"]].rolling(RATIO_WINDOW,
                                                                                       min_periods=RATIO_WINDOW).sum()
        with np.errstate(divide="ignore", invalid="ignore"):
            g["cpa"] = np.where(roll["conversions"] > 0, roll["spend"] / roll["conversions"], np.nan)
            g["roas"] = np.where(roll["spend"] > 0, roll["revenue"] / roll["spend"], np.nan)
            g["ctr"] = np.where(roll["impressions"] > 0, roll["clicks"] / roll["impressions"], np.nan)
        low_volume = float(g["conversions"].median()) < MIN_DAILY_CONVERSIONS
        weekly_spend = float(g[g["date"] > end - timedelta(days=7)]["spend"].sum())
        for metric, (direction, weight) in METRICS.items():
            if low_volume and metric in (Metric.CPA, Metric.ROAS):
                continue  # not statistically meaningful at this volume
            series = g[["date", _COLUMN[metric]]].dropna()
            if series.empty:
                continue
            band = detect_series(list(series["date"]), series[_COLUMN[metric]].to_numpy(dtype=float), end)
            if band is None:
                continue
            evaluated += 1
            obs, lo, hi = band["observed"], band["lower"], band["upper"]
            above = [bool(o > h) for o, h in zip(obs, hi, strict=True)]
            below = [bool(o < lw) for o, lw in zip(obs, lo, strict=True)]
            k_up, k_down = _trailing_run(above), _trailing_run(below)
            if direction == "up":
                k, d = k_up, "up"
            elif direction == "down":
                k, d = k_down, "down"
            else:
                k, d = (k_up, "up") if k_up >= k_down else (k_down, "down")
            if k < MIN_CONSECUTIVE:
                continue
            o = float(np.mean(obs[-k:]))
            if metric in (Metric.CPA, Metric.ROAS, Metric.CTR):
                # report the ratio over the anomalous days themselves (un-smoothed), e.g. CPA = spend / conversions
                tail = g.tail(k)
                num, den = {Metric.CPA: ("spend", "conversions"), Metric.ROAS: ("revenue", "spend"),
                            Metric.CTR: ("clicks", "impressions")}[metric]
                if float(tail[den].sum()) > 0:
                    o = float(tail[num].sum()) / float(tail[den].sum())
            e = float(np.mean(band["expected"][-k:]))
            if e == 0 or not math.isfinite(e):
                continue
            dev = 100 * (o - e) / abs(e)
            if k < SUSTAINED_DAYS and abs(dev) < SHORT_SPIKE_MIN_DEV_PCT:
                continue  # a two-day wobble needs to be large to matter
            at_risk = round(weekly_spend * min(abs(dev) / 100, 1.5) * weight, 2)
            sev = severity_for(dev, at_risk)
            rule = _suppressed(rules, metric, campaign_id, end.month)
            if rule:
                suppressed.append(rule)
                continue
            out.append(Anomaly(
                anomaly_id=f"anom_{sha256_obj([platform, campaign_id, metric, end])[:16]}",
                platform=Platform(platform), entity_id=str(campaign_id), entity_name=str(campaign_name),
                campaign_id=str(campaign_id), metric=metric, direction=d, observed=round(o, 4), expected=round(e, 4),
                lower=round(float(np.mean(lo[-k:])), 4), upper=round(float(np.mean(hi[-k:])), 4),
                deviation_pct=round(dev, 1), days=k, severity=sev, spend_at_risk_weekly=at_risk,
                iforest_confirmed=bool(np.sum(band["iso"][-k:] == -1) * 2 >= k),
                series_hash=sha256_obj([float(x) for x in series[_COLUMN[metric]].tolist()]),
            ))
    out.sort(key=lambda a: (-a.severity.rank, -a.spend_at_risk_weekly, a.anomaly_id))
    return out, evaluated, suppressed


def run(state: RunState, ctx: AgentContext) -> dict[str, Any]:
    ref = state.metrics_ref or {}
    df = load_frame(ctx.repo("metrics_daily"), ctx.brand_id, date.fromisoformat(ref["start"]), state.period_end,
                    ref.get("platforms"))
    days = df["date"].nunique() if not df.empty else 0
    update: dict[str, Any] = {"anomaly_pass_done": True}
    if days < MIN_HISTORY_DAYS + EVAL_WINDOW:
        update["degradations"] = [degrade(DegradationCode.INSUFFICIENT_HISTORY, AgentName.ANOMALY, f"{days} days")]
        return update
    rules_doc = ctx.repo("brand_rules").find_one({"brand_id": ctx.brand_id})
    rules = BrandRules.from_doc(rules_doc) if rules_doc else None
    anomalies, evaluated, suppressed = detect(df, state.period_end, rules)
    log.info("anomaly_pass", extra={"series": evaluated, "found": len(anomalies), "suppressed": len(suppressed),
                                    "material": sum(1 for a in anomalies if a.severity.rank >= 1)})
    update["anomalies"] = anomalies
    return update
