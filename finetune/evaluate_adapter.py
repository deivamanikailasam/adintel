"""Base vs fine-tuned vs frontier on the report suite (the table you need before promoting an adapter).

    python finetune/evaluate_adapter.py --adapter-url http://127.0.0.1:8082/v1 --sample 3

Columns: tone match (judge, median of 3), structure compliance, numeric grounding, latency p95,
notional cost per report. Also writes finetune/blind_test.jsonl (shuffled, unlabeled outputs) for human
raters — the blind preference test is what decides.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter-url", required=True, help="mlx_lm.server started with --adapter-path")
    ap.add_argument("--sample", type=int, default=1)
    args = ap.parse_args()
    from adintel.agents.report import SECTION_KEYS, ReportOutput
    from adintel.evals.judge import judge
    from adintel.llm.gateway import CallContext, LLMGateway
    from adintel.llm.registry import get_registry
    from adintel.rag.grounding import check_grounding
    from adintel.storage import get_database

    reg = get_registry()
    reg.tiers["report_adapter"] = replace(reg.tiers["report"], name="report_adapter", base_url=args.adapter_url)
    rows = [json.loads(x) for x in (ROOT / "evals/datasets/report.jsonl").read_text().splitlines()][:: args.sample]
    gw = LLMGateway(get_database(), CallContext(tenant_id="eval"), registry=reg)
    results: dict[str, dict[str, list[float]]] = {}
    blind = []
    for tier in ("report", "report_adapter", "frontier"):
        m: dict[str, list[float]] = {"tone": [], "structure": [], "grounding": [], "latency": [], "cost": []}
        for r in rows:
            t0 = time.perf_counter()
            try:
                out = gw.structured(
                    agent="report",
                    prompt_id="report",
                    schema=ReportOutput,
                    tier_override=tier,
                    allow_fallback=False,
                    context={"findings": r["facts"], "tone_cluster": "warm", "required_sections": SECTION_KEYS},
                )
            except Exception:
                m["structure"].append(0.0)
                continue
            text = "\n".join(s.body for s in out.value.sections)
            m["latency"].append(time.perf_counter() - t0)
            m["cost"].append(out.cost_usd)
            m["structure"].append(1.0)
            m["grounding"].append(1.0 if check_grounding(text, r["facts"]).passed else 0.0)
            score = judge(gw, rubric="Tone match for a warm, practical brand voice (1-5).", output=text)
            if score:
                m["tone"].append(score)
            blind.append({"case": r["id"], "variant": tier, "text": text})
        results[tier] = m

    def p95(xs: list[float]) -> float:
        return round(sorted(xs)[int(0.95 * (len(xs) - 1))], 2) if xs else 0.0

    print(f"{'metric':<22}{'base':>12}{'fine-tuned':>12}{'frontier':>12}")
    for metric, fn in [
        ("tone (1-5)", lambda x: round(statistics.median(x), 2) if x else 0),
        ("structure", lambda x: f"{100 * statistics.mean(x):.0f}%" if x else "-"),
        ("grounding", lambda x: f"{100 * statistics.mean(x):.0f}%" if x else "-"),
        ("latency p95 (s)", p95),
        ("cost/report ($)", lambda x: round(statistics.mean(x), 5) if x else 0),
    ]:
        key = {
            "tone (1-5)": "tone",
            "structure": "structure",
            "grounding": "grounding",
            "latency p95 (s)": "latency",
            "cost/report ($)": "cost",
        }[metric]
        print(
            f"{metric:<22}" + "".join(f"{fn(results[t][key])!s:>12}" for t in ("report", "report_adapter", "frontier"))
        )
    random.Random(7).shuffle(blind)
    (ROOT / "finetune" / "blind_test.jsonl").write_text(
        "\n".join(json.dumps({"case": b["case"], "sample_id": i, "text": b["text"]}) for i, b in enumerate(blind))
    )
    (ROOT / "finetune" / "blind_test_key.json").write_text(json.dumps({i: b["variant"] for i, b in enumerate(blind)}))
    print("\nblind test written: finetune/blind_test.jsonl (key kept separately in blind_test_key.json)")


if __name__ == "__main__":
    main()
