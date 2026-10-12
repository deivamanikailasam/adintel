"""Build mlx-lm chat-format training data for one tone cluster.

Sources, in order of preference:
  1. production: released reports with rating >= 4 (or approved without edits) for brands in the cluster
     (``--from-db``; requires ADINTEL_STORAGE=mongo);
  2. seed: findings from evals/datasets/report.jsonl rendered by the deterministic template and lightly
     restyled per tone — only to smoke-test the pipeline, never to ship an adapter.

Output: finetune/data/<tone>/{train,valid,test}.jsonl, 85% / 7.5% / 7.5%, each line
``{"messages": [system, user(findings JSON), assistant(report JSON)]}`` — the exact message shape the
Report agent sends at inference time, so train and serve match.

    python finetune/prepare_dataset.py --tone warm --from-db
    python finetune/prepare_dataset.py --tone neutral --seed-data
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

TONES = {
    "warm": ("Friendly and practical.", "Here's how your week went."),
    "energetic": ("Energetic and encouraging.", "Big week — let's dig in!"),
    "formal": ("Formal and precise.", "This report summarises performance for the period."),
    "neutral": ("Clear and neutral.", "Summary of the reporting period."),
}


def system_prompt() -> str:
    from adintel.agents.report import ReportOutput
    from adintel.llm.prompts import get_prompts

    return (
        get_prompts().get("report").text + "\n\nRespond with ONE JSON object only, no prose, matching this JSON "
        "Schema:\n" + json.dumps(ReportOutput.model_json_schema(), sort_keys=True) + "\n/no_think"
    )


def example(facts: dict[str, Any], report: dict[str, Any], tone: str) -> dict[str, Any]:
    ctx = {
        "findings": facts,
        "tone_cluster": tone,
        "voice_notes": TONES[tone][0],
        "required_sections": ["summary", "performance", "anomalies", "recommendations", "caveats", "next_steps"],
    }
    from adintel.core.hashing import canonical_json

    return {
        "messages": [
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": f"<context>\n{canonical_json(ctx)}\n</context>"},
            {"role": "assistant", "content": json.dumps(report, ensure_ascii=False)},
        ]
    }


def from_seed(tone: str) -> list[dict[str, Any]]:
    from adintel.agents.report import render_template

    rows = [json.loads(x) for x in (ROOT / "evals/datasets/report.jsonl").read_text().splitlines()]
    out = []
    for r in rows:
        rep = render_template(r["facts"]).model_dump()
        rep["sections"][0]["body"] = f"{TONES[tone][1]} " + rep["sections"][0]["body"]
        out.append(example(r["facts"], rep, tone))
    return out


def from_db(tone: str) -> list[dict[str, Any]]:
    from adintel.storage import get_database
    from adintel.storage.tenant_repo import SystemRepo

    db = get_database()
    brands = {
        (b["tenant_id"], b["brand_id"])
        for b in SystemRepo(db, "brands", purpose="fine-tune dataset").find()
        if (b.get("profile") or {}).get("tone_cluster") == tone
    }
    good = {
        f["report_id"]
        for f in SystemRepo(db, "feedback", purpose="fine-tune dataset").find(
            {"kind": "report_rating", "rating": {"$gte": 4}}
        )
    }
    out = []
    for rep in SystemRepo(db, "reports", purpose="fine-tune dataset").find({"status": "released"}):
        if (
            (rep["tenant_id"], rep["brand_id"]) in brands
            and rep["report_id"] in good
            and (rep.get("grounding") or {}).get("passed")
        ):
            out.append(
                example(
                    rep["facts"],
                    {
                        "title": rep["title"],
                        "sections": [
                            {"key": s["key"], "title": s["title"], "body": s["body"]} for s in rep["sections"]
                        ],
                    },
                    tone,
                )
            )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tone", choices=sorted(TONES), required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--from-db", action="store_true")
    g.add_argument("--seed-data", action="store_true")
    args = ap.parse_args()
    rows = from_db(args.tone) if args.from_db else from_seed(args.tone)
    if args.from_db and len(rows) < 50:
        print(f"only {len(rows)} approved reports for tone '{args.tone}': collect at least 50-100 before training")
    random.Random(20261012).shuffle(rows)
    n = len(rows)
    n_hold = max(2, round(n * 0.15))
    splits = {"train": rows[n_hold:], "valid": rows[: n_hold // 2], "test": rows[n_hold // 2 : n_hold]}
    out = ROOT / "finetune" / "data" / args.tone
    out.mkdir(parents=True, exist_ok=True)
    for name, items in splits.items():
        with (out / f"{name}.jsonl").open("w") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(json.dumps({k: len(v) for k, v in splits.items()}), "→", out)


if __name__ == "__main__":
    main()
