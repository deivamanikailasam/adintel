"""Run every eval suite and write ``evals/reports/latest.{json,md}``.

    python -m adintel.evals.runner --provider mock   # CI: deterministic, no models needed
    python -m adintel.evals.runner --provider mlx    # your local mlx-lm models
    python -m adintel.evals.runner --suites guardrail,rag --sample 2

Assertions are on **structure, not prose**: the right action on the right entity, the right verdict, the
right documents. Prose quality is judged separately (median of 3 judge runs).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from adintel.config import REPO_ROOT

DATASETS = REPO_ROOT / "evals" / "datasets"
END = date(2026, 10, 11)
START = END - timedelta(days=6)


def load(name: str, sample: int = 1) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in (DATASETS / f"{name}.jsonl").read_text().splitlines() if line.strip()]
    return rows[::sample]


def _rate(xs: list[bool]) -> float:
    return round(sum(xs) / len(xs), 4) if xs else 0.0


class Ctx:
    """Shared fixtures for all suites: one seeded in-memory database."""

    def __init__(self) -> None:
        from adintel.connectors.synthetic import reset_world
        from adintel.rag.retriever import clear_cache
        from adintel.seed.catalog import seed
        from adintel.storage import get_database

        reset_world()
        clear_cache()
        self.db = get_database()
        seed(self.db)

    def agent_ctx(self, brand_id: str, run_id: str = "eval") -> Any:
        from adintel.agents.base import AgentContext
        from adintel.domain.state import BudgetLimits, BudgetUsage
        from adintel.harness.budget import UsageMeter
        from adintel.llm.gateway import CallContext, LLMGateway

        meter = UsageMeter(BudgetLimits(), BudgetUsage())
        gw = LLMGateway(self.db, CallContext(tenant_id="brightwave", run_id=run_id, brand_id=brand_id), meter=meter)
        return AgentContext(self.db, "brightwave", brand_id, run_id, gw, meter)


# ----------------------------------------------------------------------------------------------------
def suite_orchestrator(c: Ctx, sample: int) -> dict[str, Any]:
    from adintel.agents import orchestrator
    from adintel.domain.enums import DQVerdict, Metric, Platform, Severity
    from adintel.domain.models import Anomaly, DQResult, Report, RootCause
    from adintel.domain.state import RunState

    by_cat: dict[str, list[bool]] = defaultdict(list)
    failures = []
    for case in load("orchestrator", sample):
        st = case["state"]
        anoms = [
            Anomaly(
                anomaly_id=f"a{i}",
                platform=Platform.META,
                entity_id="c",
                entity_name="C",
                campaign_id="c",
                metric=Metric.CPA,
                direction="up",
                observed=30,
                expected=20,
                lower=15,
                upper=25,
                deviation_pct=50,
                days=4,
                severity=Severity(sev),
                spend_at_risk_weekly=risk,
                iforest_confirmed=True,
            )
            for i, (sev, risk) in enumerate(st.get("anomalies", []))
        ]
        s = RunState(
            run_id="e",
            tenant_id="brightwave",
            brand_id="urban-roast",
            period_start=START,
            period_end=END,
            anomaly_pass_done=st.get("anomaly_pass_done", False),
            anomalies=anoms,
            frontier_available=st.get("frontier_available", True),
            dq=DQResult(verdict=DQVerdict(st.get("dq", "trustworthy")), checks=[], summary=""),
            root_causes=[RootCause(anomaly_id="a0", summary="x", confidence=st["root_cause"], hypotheses=[])]
            if st.get("root_cause")
            else [],
            analyst_done=bool(st.get("root_cause")),
            report=Report(title="r", sections=[], facts={}, model_tier="t") if st.get("report") else None,
        )
        out = orchestrator.run(s, c.agent_ctx("urban-roast"))
        ok = out["next_action"] == case["expected"]
        by_cat[case["category"]].append(ok)
        if not ok:
            failures.append({"id": case["id"], "expected": case["expected"], "got": out["next_action"]})
    allx = [x for v in by_cat.values() for x in v]
    rule_hops = len(by_cat["rule"])
    return {
        "metrics": {"exact_match": _rate(allx), "rule_share": round(rule_hops / max(1, len(allx)), 3)},
        "categories": {k: _rate(v) for k, v in by_cat.items()},
        "cases": len(allx),
        "failures": failures[:20],
    }


def _dq_frame(sc: dict[str, Any]) -> tuple[Any, list[Any]]:
    import numpy as np
    import pandas as pd

    from adintel.domain.enums import Platform
    from adintel.domain.models import PlatformFetch

    rng = np.random.default_rng(sc["seed"])
    rows = []
    days = [END - timedelta(days=i) for i in range(59, -1, -1)]
    for p in ("meta", "google_ads"):
        for d in days:
            clicks = int(rng.normal(1000, 60))
            conv = float(rng.poisson(40))
            if sc["kind"] == "zero_conversions" and (END - d).days < sc["days"]:
                conv = 0.0
            rows.append(
                {
                    "date": d,
                    "platform": p,
                    "campaign_id": "c",
                    "campaign_name": "C",
                    "entity_id": "e",
                    "entity_name": "E",
                    "impressions": clicks * 50,
                    "clicks": clicks,
                    "spend": round(clicks * 1.1, 2),
                    "conversions": conv,
                    "revenue": conv * 40,
                    "daily_budget": 1200,
                    "currency_original": "USD",
                }
            )
    df = pd.DataFrame(rows)
    if sc["kind"] == "missing_days":
        drop = {END - timedelta(days=i + 1) for i in range(sc["days"])}
        df = df[~((df["platform"] == "meta") & df["date"].isin(drop))]
    if sc["kind"] == "stale":
        df = df[~((df["platform"] == "meta") & (df["date"] > END - timedelta(days=sc["days"])))]
    if sc["kind"] == "impossible_values":
        idx = df.sample(frac=sc["fraction"], random_state=1).index
        df.loc[idx, "clicks"] = df.loc[idx, "impressions"] + 10
    fetches = []
    for p in ("meta", "google_ads"):
        total = float(df.loc[df["platform"] == p, "spend"].sum())
        if sc["kind"] == "reconciliation_mismatch" and p == "meta":
            total *= 1.05
        cur = ["USD", "EUR"] if sc["kind"] == "mixed_currency" and p == "meta" else ["USD"]
        fetches.append(
            PlatformFetch(
                platform=Platform(p), ok=True, rows=len(df), raw_spend_total_usd=round(total, 2), currencies=cur
            )
        )
    return df, fetches


def suite_data_quality(c: Ctx, sample: int) -> dict[str, Any]:
    from adintel.agents.data_quality import evaluate

    res, crit, failures = [], [], []
    for case in load("data_quality", sample):
        df, fetches = _dq_frame(case["scenario"])
        verdict, _ = evaluate(df, fetches, START, END)
        ok = str(verdict) == case["expected"]
        res.append(ok)
        if case["critical"]:
            crit.append(ok)
        if not ok:
            failures.append(
                {
                    "id": case["id"],
                    "expected": case["expected"],
                    "got": str(verdict),
                    "scenario": case["scenario"]["kind"],
                }
            )
    return {
        "metrics": {"accuracy": _rate(res), "critical_accuracy": _rate(crit)},
        "cases": len(res),
        "failures": failures[:20],
    }


def suite_anomaly(c: Ctx, sample: int) -> dict[str, Any]:
    import numpy as np

    from adintel.agents.anomaly import flag_series

    tp = fp = fn = tn = 0
    failures = []
    for case in load("anomaly", sample):
        s = case["series"]
        rng = np.random.default_rng(s["seed"])
        days = [END - timedelta(days=i) for i in range(179, -1, -1)]
        vals = np.array([s["base"] * (1 + s["weekly_amp"] * np.sin(2 * np.pi * d.weekday() / 7)) for d in days])
        vals = vals * rng.lognormal(0, s["noise"], len(days))
        if s["shift_days"]:
            vals[-s["shift_days"] :] *= 1 + s["shift_pct"] / 100
        detected, direction, _ = flag_series(days, vals, END)
        exp = case["expected"]
        if exp["detected"] and detected and direction == exp["direction"]:
            tp += 1
        elif exp["detected"]:
            fn += 1
            failures.append({"id": case["id"], "expected": exp, "got": [detected, direction]})
        elif detected:
            fp += 1
            failures.append({"id": case["id"], "expected": exp, "got": [detected, direction]})
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "metrics": {
            "f1": round(f1, 4),
            "false_positive_rate": round(fp / max(1, fp + tn), 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
        },
        "cases": tp + fp + fn + tn,
        "failures": failures[:20],
    }


def _through_analyst(c: Ctx, brand_id: str, world: dict[str, Any]) -> tuple[Any, Any]:
    from adintel.agents import analyst, anomaly, ingestion
    from adintel.domain.enums import DQVerdict
    from adintel.domain.models import DQResult
    from adintel.domain.state import RunState
    from adintel.evals.worlds import install

    platforms = install(c.db, brand_id, world)
    s = RunState(
        run_id=f"eval-{brand_id}",
        tenant_id="brightwave",
        brand_id=brand_id,
        period_start=START,
        period_end=END,
        platforms=platforms,
    )
    ctx = c.agent_ctx(brand_id, s.run_id)

    def apply(st: RunState, u: dict[str, Any]) -> RunState:
        data = st.model_dump()
        for k, v in u.items():
            data[k] = (
                (data.get(k, []) + [x.model_dump() for x in v])
                if k in ("degradations", "traces", "decisions")
                else (
                    v.model_dump()
                    if hasattr(v, "model_dump")
                    else [x.model_dump() if hasattr(x, "model_dump") else x for x in v]
                    if isinstance(v, list)
                    else v
                )
            )
        return RunState.model_validate(data)

    s = apply(s, ingestion.run(s, ctx))
    s = s.model_copy(update={"dq": DQResult(verdict=DQVerdict.TRUSTWORTHY, checks=[], summary="ok")})
    s = apply(s, anomaly.run(s, ctx))
    s = apply(s, analyst.run(s, ctx))
    return s, (ctx, apply)


def suite_analyst(c: Ctx, sample: int) -> dict[str, Any]:
    res, failures = [], []
    not_detected = 0
    for i, case in enumerate(load("analyst", sample)):
        s, _ = _through_analyst(c, f"eval-an-{i:03d}", case["world"])
        if not s.material_anomalies():
            not_detected += 1  # the Analyst never runs without an anomaly; detection has its own suite
            continue
        rc = s.root_causes[0] if s.root_causes else None
        confirmed = [h.name.lower() for h in rc.hypotheses if h.verdict == "confirmed"] if rc else []
        ok = any(case["expected_cause"] in h for h in confirmed)
        res.append(ok)
        if not ok:
            failures.append(
                {
                    "id": case["id"],
                    "expected": case["expected_cause"],
                    "got": confirmed,
                    "anomalies": len(s.material_anomalies()),
                }
            )
    return {
        "metrics": {
            "root_cause_accuracy": _rate(res),
            "detection_coverage": round(len(res) / max(1, len(res) + not_detected), 4),
        },
        "cases": len(res),
        "failures": failures[:20],
    }


def suite_optimizer(c: Ctx, sample: int) -> dict[str, Any]:
    from adintel.agents import optimizer
    from adintel.approvals import constraints
    from adintel.domain.enums import ActionType, Platform
    from adintel.domain.models import BrandRules

    acc, compliance, failures = [], [], []
    for i, case in enumerate(load("optimizer", sample)):
        brand_id = f"eval-op-{i:03d}"
        s, (ctx, apply) = _through_analyst(c, brand_id, case["world"])
        s = apply(s, optimizer.run(s, ctx))
        rules = BrandRules(tenant_id="brightwave", brand_id=brand_id)
        for r in s.recommendations:  # anything accepted must re-pass the constraints, always
            live = optimizer._live_entities(ctx, r.platform, [i for i in (r.source_entity_id, r.target_entity_id) if i])
            v = constraints.check(
                action=r.action_type,
                source=r.source_entity_id,
                target=r.target_entity_id,
                amount=r.amount_usd_per_day,
                rules=rules,
                entities=live,
                citations=[x.chunk_id for x in r.citations],
                retrieved_ids=[x.chunk_id for x in r.citations],
                now=r.created_at,
            )
            compliance.append(not v)
        if case.get("adversarial_proposal"):
            live = optimizer._live_entities(ctx, Platform.META, ["as_x_a", "as_x_b"])
            amount = live["as_x_b"]["daily_budget"] * 0.25 * case["adversarial_proposal"]["amount_multiplier"]
            v = constraints.check(
                action=ActionType.BUDGET_SHIFT,
                source="as_x_b",
                target="as_x_a",
                amount=amount,
                rules=rules,
                entities=live,
                citations=["x"],
                retrieved_ids=["x"],
                now=s.usage.started_at,
            )
            compliance.append(bool(v))
            continue
        exp = case["expected"]
        got = s.recommendations[0] if s.recommendations else None
        ok = bool(
            got
            and str(got.action_type) == exp["action_type"]
            and got.source_entity_id == exp["source"]
            and got.target_entity_id == exp["target"]
        )
        acc.append(ok)
        if not ok:
            failures.append(
                {
                    "id": case["id"],
                    "expected": exp,
                    "got": got.model_dump(include={"action_type", "source_entity_id", "target_entity_id"})
                    if got
                    else None,
                    "degradations": [str(d.code) for d in s.degradations],
                }
            )
    return {
        "metrics": {"action_accuracy": _rate(acc), "constraint_compliance": _rate(compliance) if compliance else 1.0},
        "cases": len(acc) + sum(1 for _ in compliance),
        "failures": failures[:20],
    }


def suite_report(c: Ctx, sample: int) -> dict[str, Any]:
    from adintel.agents.report import SECTION_KEYS, write
    from adintel.evals.judge import judge

    grounded: list[bool] = []
    structure: list[bool] = []
    tones: list[float] = []
    tiers: defaultdict[str, int] = defaultdict(int)
    failures: list[dict[str, Any]] = []
    ctx = c.agent_ctx("urban-roast")
    for case in load("report", sample):
        out = write(ctx, case["facts"], {"tone_cluster": "warm"})
        rep = out["report"]
        grounded.append(bool(rep.grounding and rep.grounding.passed))
        structure.append([s.key for s in rep.sections] == SECTION_KEYS)
        tiers[rep.model_tier] += 1
        caveat_ok = all(
            cv in next(s.body for s in rep.sections if s.key == "caveats") for cv in case["facts"]["caveats"]
        )
        if not caveat_ok:
            structure[-1] = False
        if not rep.deterministic_template:
            score = judge(
                ctx.llm,
                rubric="Tone match for a warm, practical brand voice; clarity; no hype (1-5).",
                output="\n".join(s.body for s in rep.sections),
            )
            if score is not None:
                tones.append(score)
        if not grounded[-1]:
            failures.append({"id": case["id"], "ungrounded": rep.grounding.ungrounded if rep.grounding else None})
    return {
        "metrics": {
            "grounding": _rate(grounded),
            "structure": _rate(structure),
            "tone": round(statistics.median(tones), 2) if tones else 0.0,
            "frontier_fallback_rate": round(tiers.get("frontier", 0) / max(1, len(grounded)), 3),
        },
        "tiers": dict(tiers),
        "cases": len(grounded),
        "failures": failures[:20],
    }


def suite_guardrail(c: Ctx, sample: int) -> dict[str, Any]:
    from adintel.agents import guardrail

    names = guardrail.other_client_names(c.db, "brightwave", "urban-roast")
    ctx = c.agent_ctx("urban-roast")
    blocked_when_should, false_blocks, failures = [], [], []
    for case in load("guardrail", sample):
        v = guardrail.review_text(ctx, case["text"], forbidden_names=names)
        if case["expected_block"]:
            blocked_when_should.append(not v.passed)
            if v.passed:
                failures.append({"id": case["id"], "text": case["text"], "category": case["category"]})
        else:
            false_blocks.append(not v.passed)
            if not v.passed:
                failures.append({"id": case["id"], "text": case["text"], "false_block": [f.check for f in v.findings]})
    return {
        "metrics": {"recall": _rate(blocked_when_should), "false_block_rate": _rate(false_blocks)},
        "cases": len(blocked_when_should) + len(false_blocks),
        "failures": failures[:20],
    }


def suite_rag(c: Ctx, sample: int) -> dict[str, Any]:
    from adintel.rag.retriever import Retriever, clear_cache

    clear_cache()
    precisions, recalls, leaks, failures = [], [], [], []
    r = Retriever(c.db, "brightwave")
    for case in load("rag", sample):
        res = r.search(case["query"], brand_id=case["brand_id"], vertical=case["vertical"], k=6, use_cache=False)
        docs = [ch.doc_id for ch in res.chunks]
        if case["kind"] == "leakage":
            leak = any(d in case["forbidden_doc_ids"] for d in docs)
            leaks.append(leak)
            if leak:
                failures.append({"id": case["id"], "leak": docs})
            continue
        rel = set(case["relevant_doc_ids"])
        hits, ap = 0, 0.0
        for rank, d in enumerate(docs, start=1):  # Ragas-style rank-weighted context precision
            if d in rel:
                hits += 1
                ap += hits / rank
        precisions.append(ap / hits if hits else 0.0)
        recalls.append(len(rel & set(docs)) / len(rel))
        if not hits:
            failures.append({"id": case["id"], "query": case["query"], "got": docs[:3]})
    return {
        "metrics": {
            "context_precision": round(statistics.mean(precisions), 4) if precisions else 0.0,
            "context_recall": round(statistics.mean(recalls), 4) if recalls else 0.0,
            "cross_tenant_leakage": _rate(leaks),
        },
        "cases": len(precisions) + len(leaks),
        "failures": failures[:20],
    }


def suite_injection(c: Ctx, sample: int) -> dict[str, Any]:
    from adintel.agents import guardrail
    from adintel.rag.indexer import index_document
    from adintel.security.fencing import fence, injection_markers

    ctx = c.agent_ctx("urban-roast")
    names = guardrail.other_client_names(c.db, "brightwave", "urban-roast")
    caught, failures = [], []
    for case in load("injection", sample):
        p, surface = case["payload"], case["surface"]
        if surface == "campaign_name":
            fenced = fence("meta_campaign_names", [p])
            ok = fenced.count("</untrusted_content>") == 1 and bool(injection_markers(p))
        elif surface == "kb_document":
            docs = index_document(
                c.db,
                "brightwave",
                doc_id=f"inj-{case['id']}",
                title="Uploaded note",
                text=f"## Note\n{p}",
                doc_type="guideline",
                brand_id="urban-roast",
            )
            ok = all(d["injection_markers"] for d in docs)
        elif surface == "chat_question":
            ok = bool(injection_markers(p))
        else:  # the model echoed the payload in its output: the guardrail must block it
            ok = not guardrail.review_text(ctx, f"Weekly summary. {p}", forbidden_names=names).passed
        caught.append(ok)
        if not ok:
            failures.append({"id": case["id"], "surface": surface, "payload": p})
    return {"metrics": {"block_rate": _rate(caught)}, "cases": len(caught), "failures": failures[:20]}


def suite_e2e(c: Ctx, sample: int) -> dict[str, Any]:
    from adintel.config import reset_settings_cache
    from adintel.evals.worlds import install
    from adintel.graph.engine import RunEngine
    from adintel.llm.providers import get_provider

    results, costs, failures = [], defaultdict(list), []
    for i, case in enumerate(load("e2e", sample)):
        brand_id = f"eval-e2e-{i:03d}"
        w = case["world"]
        install(c.db, brand_id, w)
        provider = get_provider("mock")
        down = w.get("frontier_down") and hasattr(provider, "take_down")
        if down:
            provider.take_down("frontier")  # type: ignore[attr-defined]
        if w.get("outage"):
            from adintel.connectors.synthetic import inject_failure
            from adintel.domain.enums import Platform

            inject_failure(brand_id, Platform(w["outage"]), "outage")
        if w.get("budget_usd"):
            os.environ["ADINTEL_RUN_MAX_COST_USD"] = str(w["budget_usd"])
            reset_settings_cache()
        try:
            s = RunEngine(c.db).run(
                tenant_id="brightwave",
                brand_id=brand_id,
                period_start=START,
                period_end=END,
                trigger="eval",
                schedule_date=END,
            )
        finally:
            if down:
                provider.restore("frontier")  # type: ignore[attr-defined]
            os.environ.pop("ADINTEL_RUN_MAX_COST_USD", None)
            reset_settings_cache()
        assert s is not None
        exp = case["expected"]
        from adintel.graph.finalize import path_of

        checks = []
        if "status" in exp:
            checks.append(str(s.status) == exp["status"])
        if "status_in" in exp:
            checks.append(str(s.status) in exp["status_in"])
        if "path" in exp:
            checks.append(path_of(s) == exp["path"])
        if "degradation" in exp:
            checks.append(s.has_degradation(exp["degradation"]))
        if exp.get("action_type"):
            r = s.recommendations[0] if s.recommendations else None
            checks.append(
                bool(
                    r
                    and str(r.action_type) == exp["action_type"]
                    and r.source_entity_id == exp["source"]
                    and r.target_entity_id == exp["target"]
                )
            )
        ok = all(checks)
        results.append(ok)
        costs[path_of(s)].append(s.usage.cost_usd)
        if not ok:
            failures.append(
                {
                    "id": case["id"],
                    "expected": exp,
                    "status": str(s.status),
                    "path": path_of(s),
                    "degradations": [str(d.code) for d in s.degradations],
                }
            )
    return {
        "metrics": {"pass_rate": _rate(results)},
        "cost_per_path": {k: round(statistics.mean(v), 6) for k, v in costs.items()},
        "cases": len(results),
        "failures": failures[:20],
    }


SUITES: dict[str, Callable[[Ctx, int], dict[str, Any]]] = {
    "orchestrator": suite_orchestrator,
    "data_quality": suite_data_quality,
    "anomaly": suite_anomaly,
    "analyst": suite_analyst,
    "optimizer": suite_optimizer,
    "report": suite_report,
    "guardrail": suite_guardrail,
    "rag": suite_rag,
    "injection": suite_injection,
    "e2e": suite_e2e,
}


def render_md(report: dict[str, Any]) -> str:
    lines = [
        f"# AdIntel eval report — {report['started_at']}",
        "",
        f"Provider: **{report['provider']}** · registry {report['model_registry']} · duration {report['duration_s']}s",
        "",
        "| Suite | Metric | Value | Cases |",
        "|---|---|---|---|",
    ]
    for name, r in report["suites"].items():
        for m, v in r.get("metrics", {}).items():
            lines.append(f"| {name} | {m} | {v} | {r.get('cases', '')} |")
    for name, r in report["suites"].items():
        if r.get("failures"):
            lines += ["", f"## {name}: first failures", "```json", json.dumps(r["failures"][:5], indent=1), "```"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> dict[str, Any]:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["mock", "mlx"], default="mock")
    ap.add_argument("--suites", default=",".join(SUITES))
    ap.add_argument("--sample", type=int, default=1, help="use every Nth case (quick runs)")
    ap.add_argument("--out", default=str(REPO_ROOT / "evals" / "reports"))
    args = ap.parse_args(argv)
    os.environ["ADINTEL_LLM_PROVIDER"] = "mock" if args.provider == "mock" else "openai_compat"
    os.environ.setdefault("ADINTEL_STORAGE", "memory")
    os.environ.setdefault("ADINTEL_LOG_LEVEL", "ERROR")
    # evals start hundreds of runs for one tenant in minutes: lift the production admission limits here only
    os.environ.setdefault("ADINTEL_TENANT_RUNS_PER_MINUTE", "1000000")
    os.environ.setdefault("ADINTEL_TENANT_DAILY_COST_CAP_USD", "1000000")
    from adintel.config import reset_settings_cache
    from adintel.llm.registry import get_registry, reset_registry
    from adintel.observability.logging import configure_logging

    reset_settings_cache()
    reset_registry()
    configure_logging("ERROR", False)
    t0 = time.time()
    c = Ctx()
    report: dict[str, Any] = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider": args.provider,
        "model_registry": get_registry().version,
        "models": {n: t.model_id for n, t in get_registry().tiers.items()},
        "suites": {},
    }
    for name in args.suites.split(","):
        ts = time.time()
        report["suites"][name] = {**SUITES[name](c, args.sample), "seconds": round(time.time() - ts, 1)}
        print(f"{name:<13} {report['suites'][name]['metrics']}  ({report['suites'][name]['seconds']}s)", flush=True)
    report["duration_s"] = round(time.time() - t0, 1)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "latest.json").write_text(json.dumps(report, indent=2, default=str))
    (out / "latest.md").write_text(render_md(report))
    (out / f"eval-{args.provider}-{report['started_at'].replace(':', '')}.json").write_text(
        json.dumps(report, indent=2, default=str)
    )
    return report


if __name__ == "__main__":
    main()
