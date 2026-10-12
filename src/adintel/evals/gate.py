"""Promotion gate. Nothing reaches production without (docs/07-evaluation/promotion-gate.md):

* every **hard** threshold met (100% guardrail recall, 100% constraint compliance, 100% grounding,
  100% critical DQ accuracy, zero leakage, 100% injection block rate, E2E suite green);
* every quality threshold met (with the judge's variance band);
* **no category regression** versus the baseline beyond tolerance;
* cost within ±15% of the baseline per run path;
* (outside this script) a 3-day shadow run on 20% of traffic and a named human sign-off.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from adintel.config import REPO_ROOT

COST_TOLERANCE = 0.15


def evaluate(report: dict[str, Any], thresholds: dict[str, Any], baseline: dict[str, Any] | None) -> list[str]:
    problems: list[str] = []
    for suite, rules in thresholds["suites"].items():
        r = report["suites"].get(suite)
        if r is None:
            problems.append(f"{suite}: suite missing from report")
            continue
        for metric, rule in rules.items():
            v = r["metrics"].get(metric)
            if v is None:
                problems.append(f"{suite}.{metric}: missing")
                continue
            band = rule.get("band", 0.0)
            if "min" in rule and v < rule["min"] - band:
                problems.append(f"{suite}.{metric} = {v} < {rule['min']}{' (hard)' if rule.get('hard') else ''}")
            if "max" in rule and v > rule["max"] + band:
                problems.append(f"{suite}.{metric} = {v} > {rule['max']}{' (hard)' if rule.get('hard') else ''}")
        if baseline and suite in baseline.get("suites", {}):
            for cat, v in r.get("categories", {}).items():
                b = baseline["suites"][suite].get("categories", {}).get(cat)
                if b is not None and v < b - thresholds.get("category_regression_tolerance", 0.02):
                    problems.append(f"{suite}/{cat}: category regression {b} → {v}")
    if baseline:
        for path, cost in report["suites"].get("e2e", {}).get("cost_per_path", {}).items():
            b = baseline["suites"].get("e2e", {}).get("cost_per_path", {}).get(path)
            if b and abs(cost - b) / b > COST_TOLERANCE:
                problems.append(f"e2e cost for '{path}' path {cost:.6f} vs baseline {b:.6f} (outside ±15%)")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=str(REPO_ROOT / "evals" / "reports" / "latest.json"))
    ap.add_argument("--baseline", default=str(REPO_ROOT / "evals" / "baseline.json"))
    ap.add_argument("--thresholds", default=str(REPO_ROOT / "evals" / "thresholds.yaml"))
    ap.add_argument("--write-baseline", action="store_true", help="accept this report as the new baseline")
    args = ap.parse_args(argv)
    report = json.loads(Path(args.report).read_text())
    thresholds = yaml.safe_load(Path(args.thresholds).read_text())
    bpath = Path(args.baseline)
    baseline = json.loads(bpath.read_text()) if bpath.exists() else None
    problems = evaluate(report, thresholds, baseline)
    if problems:
        print("PROMOTION GATE: FAIL")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print(
        "PROMOTION GATE: PASS (remaining steps: 3-day shadow on 20% traffic → `adintel shadow-report` ready, named sign-off)"
    )
    if args.write_baseline:
        bpath.write_text(
            json.dumps(
                {
                    "suites": {
                        k: {kk: vv for kk, vv in v.items() if kk != "failures"} for k, v in report["suites"].items()
                    },
                    "provider": report["provider"],
                    "accepted_from": report["started_at"],
                },
                indent=2,
            )
        )
        print(f"baseline written to {bpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
