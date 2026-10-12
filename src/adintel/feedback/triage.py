"""Weekly triage: one page that tells the Head of Performance and the AI owner what to look at next.

It reads only what the system already records — runs, degradations, decisions, rejection reasons,
outcomes, ratings, guardrail blocks and cost — for one tenant over a window (default 7 days), and turns the
patterns into a short list of suggested actions. Nothing here calls a model.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any

from adintel.core.clock import utcnow
from adintel.storage.base import Database
from adintel.storage.tenant_repo import SystemRepo, TenantScopedRepo

REJECTION_ADVICE = {
    "wrong_diagnosis": "Analyst diagnoses are being rejected: review analyst prompts and the root-cause eval suite.",
    "right_diagnosis_wrong_action": "Diagnoses are accepted but actions are not: review Optimizer playbooks in the knowledge base.",
    "violates_unstated_preference": "Account managers have preferences the system doesn't know: capture them as brand rules.",
    "poorly_explained": "Recommendations are hard to follow: review rationale wording and the report tone adapter.",
    "stale": "Recommendations expire before review: check approval-queue notifications and staffing.",
}


def weekly_triage(db: Database, tenant_id: str, *, days: int = 7, today: date | None = None) -> dict[str, Any]:
    today = today or utcnow().date()
    since = (today - timedelta(days=days)).isoformat()

    def recent(coll: str, field: str = "created_at", extra: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return TenantScopedRepo(db, coll, tenant_id).find({field: {"$gte": since}, **(extra or {})})

    runs = recent("runs")
    degradations = Counter(code for r in runs for code in r.get("degradations", []))
    feedback = recent("feedback")
    decisions = Counter(
        f["kind"].removeprefix("recommendation_") for f in feedback if f["kind"].startswith("recommendation_")
    )
    rejections = Counter(f.get("category", "other") for f in feedback if f["kind"] == "recommendation_rejected")
    modified = [f for f in feedback if f["kind"] == "recommendation_modified" and f.get("original_amount")]
    mod_ratio = (
        round(sum(f["approved_amount"] / f["original_amount"] for f in modified) / len(modified), 2)
        if modified
        else None
    )
    ratings = [int(f["rating"]) for f in feedback if f["kind"] == "report_rating"]
    outcomes = Counter(o["verdict"] for o in recent("outcomes", "measured_at"))
    guardrail_blocks = len(recent("audit_log", "at", {"action": "guardrail.block"}))
    cost = round(sum(float(c.get("cost_usd", 0)) for c in recent("cost_events", "day")), 4)

    report: dict[str, Any] = {
        "tenant_id": tenant_id,
        "window": {"from": since, "to": today.isoformat(), "days": days},
        "runs": {"total": len(runs), "by_status": dict(Counter(str(r.get("status")) for r in runs))},
        "degradations": dict(degradations.most_common()),
        "decisions": dict(decisions),
        "rejection_reasons": dict(rejections.most_common()),
        "average_approved_to_proposed_ratio": mod_ratio,
        "report_ratings": {
            "count": len(ratings),
            "average": round(sum(ratings) / len(ratings), 2) if ratings else None,
            "low": sum(1 for r in ratings if r <= 2),
        },
        "outcomes": dict(outcomes),
        "guardrail_blocks": guardrail_blocks,
        "ai_cost_usd": cost,
    }
    report["actions"] = _actions(report)
    return report


def _actions(r: dict[str, Any]) -> list[str]:
    acts: list[str] = []
    total = r["runs"]["total"]
    failed = r["runs"]["by_status"].get("failed", 0)
    if total and failed / total > 0.05:
        acts.append(f"{failed} of {total} runs failed: check the reliability dashboard and dead-letter queues.")
    for code, n in r["degradations"].items():
        if total and n / total >= 0.2:
            acts.append(f"Degradation '{code}' hit {n} of {total} runs: see the degradation runbook.")
    if r["rejection_reasons"]:
        top = next(iter(r["rejection_reasons"]))
        acts.append(REJECTION_ADVICE.get(top, f"Most common rejection reason: {top}. Read the notes."))
    if r["average_approved_to_proposed_ratio"] is not None and r["average_approved_to_proposed_ratio"] < 0.8:
        acts.append("Approvers routinely cut proposed amounts: consider lowering max_single_change_pct.")
    o = r["outcomes"]
    graded = sum(v for k, v in o.items() if k != "insufficient_data")
    if graded and o.get("worsened", 0) / graded > 0.2:
        acts.append("More than 20% of measured changes made CPA worse: pause the optimizer flag and review.")
    if r["report_ratings"]["low"]:
        acts.append(f"{r['report_ratings']['low']} report(s) rated 2 or lower: read them before next week's runs.")
    if r["guardrail_blocks"]:
        acts.append(f"Guardrail blocked {r['guardrail_blocks']} output(s): confirm each block was correct.")
    return acts or ["Nothing needs attention this week."]


def render_markdown(r: dict[str, Any]) -> str:
    def table(d: dict[str, Any]) -> str:
        return "\n".join(f"| {k} | {v} |" for k, v in d.items()) or "| — | 0 |"

    w = r["window"]
    rt = r["report_ratings"]
    return "\n".join(
        [
            f"# AdIntel weekly triage — {r['tenant_id']} ({w['from']} → {w['to']})",
            "",
            "## Suggested actions",
            *[f"- {a}" for a in r["actions"]],
            "",
            f"## Runs ({r['runs']['total']})",
            "| Status | Count |\n|---|---|",
            table(r["runs"]["by_status"]),
            "",
            "## Degradations",
            "| Code | Runs |\n|---|---|",
            table(r["degradations"]),
            "",
            "## Human decisions",
            "| Decision | Count |\n|---|---|",
            table(r["decisions"]),
            "",
            "## Rejection reasons",
            "| Reason | Count |\n|---|---|",
            table(r["rejection_reasons"]),
            "",
            "## Outcomes of executed changes (14 days later)",
            "| Verdict | Count |\n|---|---|",
            table(r["outcomes"]),
            "",
            "## Other signals",
            f"- Report ratings: {rt['count']} (average {rt['average']}, {rt['low']} rated ≤ 2)",
            f"- Approved ÷ proposed amount: {r['average_approved_to_proposed_ratio']}",
            f"- Guardrail blocks: {r['guardrail_blocks']}",
            f"- AI cost: ${r['ai_cost_usd']:.2f}",
            "",
        ]
    )


def triage_job(db: Database, *, today: date | None = None) -> int:
    """Weekly: post each tenant's triage as a notification for the Head of Performance."""
    n = 0
    for t in SystemRepo(db, "tenants", purpose="weekly triage").find():
        r = weekly_triage(db, t["tenant_id"], today=today)
        TenantScopedRepo(db, "notifications", t["tenant_id"]).insert(
            {
                "kind": "weekly_triage",
                "audience": "head_of_performance",
                "title": "Weekly AI triage",
                "detail": " ".join(r["actions"]),
                "triage": r,
                "created_at": utcnow().isoformat(),
            }
        )
        n += 1
    return n
