"""Data Quality agent: is this data trustworthy enough to reason over?

Seven deterministic checks decide the verdict. The small model only phrases the summary.
Zero conversions after months of daily conversions is a *successful* API call and *untrustworthy* data —
which is exactly why this agent is separate from ingestion.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd

from adintel.agents.base import AgentContext
from adintel.analytics.frames import load_frame
from adintel.domain.enums import AgentName, DegradationCode, DQVerdict, RunStatus
from adintel.domain.models import DQCheck, DQResult, PlatformFetch
from adintel.domain.state import RunState
from adintel.harness.degradation import degrade
from adintel.observability.alerts import Severity, raise_alert

log = logging.getLogger(__name__)

TRACKING_ZERO_DAYS = 3
TRACKING_MIN_BASELINE_CONV = 5.0
TRACKING_MIN_CLICK_RATIO = 0.5
RECONCILE_TOLERANCE = 0.01


def _completeness(df: pd.DataFrame, start: date, end: date, platforms: list[str]) -> DQCheck:
    expected = {start + timedelta(days=i) for i in range((end - start).days + 1)}
    missing: dict[str, int] = {}
    for p in platforms:
        have = set(df.loc[df["platform"] == p, "date"]) if not df.empty else set()
        n = len(expected - have)
        if n:
            missing[p] = n
    worst = max(missing.values(), default=0)
    return DQCheck(name="completeness", passed=worst == 0, critical=worst > 2,
                   detail="all days present" if not missing else f"missing days in period: {missing}")


def _freshness(df: pd.DataFrame, end: date, platforms: list[str]) -> DQCheck:
    stale = {}
    for p in platforms:
        dates = df.loc[df["platform"] == p, "date"] if not df.empty else []
        last = max(dates) if len(dates) else None
        if last is None or last < end:
            stale[p] = str(last)
    lag = max(((end - date.fromisoformat(v)).days if v != "None" else 99 for v in stale.values()), default=0)
    return DQCheck(name="freshness", passed=not stale, critical=lag > 1,
                   detail="data current to period end" if not stale else f"latest dates: {stale}")


def _tracking(df: pd.DataFrame, end: date) -> DQCheck:
    broken = []
    for p, g in df.groupby("platform") if not df.empty else []:
        daily = g.groupby("date")[["clicks", "conversions"]].sum().sort_index()
        recent = daily[daily.index > end - timedelta(days=TRACKING_ZERO_DAYS)]
        base = daily[(daily.index <= end - timedelta(days=TRACKING_ZERO_DAYS))
                     & (daily.index > end - timedelta(days=TRACKING_ZERO_DAYS + 28))]
        if len(recent) < TRACKING_ZERO_DAYS or base.empty:
            continue
        zero_run = 0
        for v in reversed(daily["conversions"].tolist()):
            if v == 0:
                zero_run += 1
            else:
                break
        clicks_ok = recent["clicks"].mean() >= TRACKING_MIN_CLICK_RATIO * base["clicks"].mean()
        if (zero_run >= TRACKING_ZERO_DAYS and base["conversions"].mean() >= TRACKING_MIN_BASELINE_CONV
                and clicks_ok):
            broken.append(f"{p}: conversions exactly 0 for {zero_run} days vs a "
                          f"{base['conversions'].mean():.0f}/day baseline while clicks look normal")
    return DQCheck(name="conversion_tracking", passed=not broken, critical=bool(broken),
                   detail="conversion tracking healthy" if not broken else "; ".join(broken))


def _sanity(df: pd.DataFrame) -> DQCheck:
    if df.empty:
        return DQCheck(name="value_sanity", passed=True, critical=False, detail="no rows")
    bad = df[(df["clicks"] > df["impressions"]) | (df["spend"] < 0) | (df["conversions"] < 0)
             | (df["revenue"] < 0)]
    frac = len(bad) / len(df)
    return DQCheck(name="value_sanity", passed=len(bad) == 0, critical=frac > 0.01,
                   detail=f"{len(bad)} impossible rows ({frac:.2%})")


def _duplicates(fetches: list[PlatformFetch]) -> DQCheck:
    d = {str(f.platform): f.duplicates for f in fetches if f.duplicates}
    return DQCheck(name="duplicates", passed=not d, critical=False,
                   detail="no duplicate rows" if not d else f"duplicate rows dropped: {d}")


def _currency(fetches: list[PlatformFetch]) -> DQCheck:
    mixed = {str(f.platform): f.currencies for f in fetches if len(f.currencies) > 1}
    return DQCheck(name="currency_consistency", passed=not mixed, critical=False,
                   detail="one currency per account" if not mixed else f"mixed currencies: {mixed}")


def _reconciliation(df: pd.DataFrame, fetches: list[PlatformFetch]) -> DQCheck:
    bad = {}
    for f in fetches:
        if not f.ok:
            continue
        stored = float(df.loc[df["platform"] == str(f.platform), "spend"].sum()) if not df.empty else 0.0
        if f.raw_spend_total_usd and abs(stored - f.raw_spend_total_usd) / f.raw_spend_total_usd > RECONCILE_TOLERANCE:
            bad[str(f.platform)] = (round(stored, 2), f.raw_spend_total_usd)
    return DQCheck(name="spend_reconciliation", passed=not bad, critical=bool(bad),
                   detail="stored spend matches platform totals" if not bad else f"stored vs platform: {bad}")


def evaluate(df: pd.DataFrame, fetches: list[PlatformFetch], start: date, end: date) -> tuple[DQVerdict, list[DQCheck]]:
    ok_platforms = [str(f.platform) for f in fetches if f.ok]
    checks = [_completeness(df, start, end, ok_platforms), _freshness(df, end, ok_platforms), _tracking(df, end),
              _sanity(df), _duplicates(fetches), _currency(fetches), _reconciliation(df, fetches)]
    if any(c.critical and not c.passed for c in checks):
        return DQVerdict.UNTRUSTWORTHY, checks
    if any(not c.passed for c in checks):
        return DQVerdict.DEGRADED, checks
    return DQVerdict.TRUSTWORTHY, checks


def _template_summary(verdict: DQVerdict, checks: list[DQCheck]) -> str:
    failed = [c for c in checks if not c.passed]
    if not failed:
        return f"All {len(checks)} data-quality checks passed; the data is trustworthy for tonight's analysis."
    what = "; ".join(f"{c.name}: {c.detail}" for c in failed)
    consequence = {DQVerdict.UNTRUSTWORTHY: "Analysis is stopped and the account team has been alerted.",
                   DQVerdict.DEGRADED: "Analysis continues with a disclosed caveat; no changes will be proposed.",
                   DQVerdict.TRUSTWORTHY: ""}[verdict]
    return f"Data-quality issues found ({what}). {consequence}".strip()


def run(state: RunState, ctx: AgentContext) -> dict[str, Any]:
    ref = state.metrics_ref or {}
    df = load_frame(ctx.repo("metrics_daily"), ctx.brand_id, date.fromisoformat(ref["start"]),
                    date.fromisoformat(ref["end"]), ref.get("platforms"))
    verdict, checks = evaluate(df, state.fetches, state.period_start, state.period_end)
    summary = _template_summary(verdict, checks)
    try:
        res = ctx.llm.text(agent="data_quality", prompt_id="dq_summary",
                           context={"verdict": verdict, "checks": [c.model_dump() for c in checks]})
        if res.text and len(res.text) < 800:
            summary = res.text
    except Exception as exc:  # noqa: BLE001 - phrasing is optional; the verdict is code
        log.info("dq_summary_template_used", extra={"reason": str(exc)[:120]})
    update: dict[str, Any] = {"dq": DQResult(verdict=verdict, checks=checks, summary=summary)}
    if verdict == DQVerdict.UNTRUSTWORTHY:
        update["status"] = RunStatus.ABORTED_DATA_QUALITY
        update["abort_reason"] = "; ".join(c.detail for c in checks if c.critical and not c.passed)
        raise_alert(Severity.P2, f"Reporting paused for {state.brand_name or state.brand_id}: untrustworthy data",
                    tenant_id=ctx.tenant_id, brand_id=ctx.brand_id,
                    details={"run_id": ctx.run_id, "reason": update["abort_reason"]},
                    audience="account_manager,tech_lead")
    elif verdict == DQVerdict.DEGRADED:
        failed = ", ".join(c.name for c in checks if not c.passed)
        update["degradations"] = [degrade(DegradationCode.DQ_WARNINGS, AgentName.DATA_QUALITY, failed)]
    return update
