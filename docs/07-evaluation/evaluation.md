# Evaluation

Each agent has its own golden dataset and threshold. The safety-critical thresholds are 100% or the
build fails, and a weekly flywheel turns every production mistake into a permanent test.

```bash
make evals        # every suite, mock provider (deterministic, CI)
make evals-mlx    # every suite against your local Qwen models on mlx-lm
make gate         # promotion gate against evals/baseline.json
python -m adintel.evals.runner --provider mlx --suites report,guardrail --sample 3   # quick slice
```

Results land in `evals/reports/latest.json` and `latest.md` (plus a timestamped copy).

## Per-agent golden datasets (`evals/datasets/*.jsonl`)

| Suite | Cases | What is checked | Threshold |
|-------|-------|-----------------|-----------|
| orchestrator | 60 states (40 rule, 20 model) | Correct next action | ≥ 95% exact match |
| data_quality | 80 | Correct verdict | ≥ 95%; **100% on critical cases** |
| anomaly | 50 series | Detected or not, direction | ≥ 0.90 F1, ≤ 5% false positives |
| analyst | 45 incidents | Confirmed hypothesis matches the label | ≥ 80% |
| optimizer | 40 scenarios (10 adversarial) | Right action and entities; constraints respected | ≥ 85% action; **100% constraint compliance** |
| report | 60 payloads | Grounding, structure, caveats, tone (judge) | **100% grounding**; ≥ 99% structure; ≥ 4.0/5 tone |
| guardrail | 120 (60 adversarial) | Blocks what should be blocked | **100% recall**; ≤ 10% false blocks |
| rag | 200 queries (20 leakage probes) | Rank-weighted context precision, recall@6, leakage | > 0.80, > 0.85, **0.00 leakage** |
| injection | 200 payloads × 4 surfaces | Fenced, flagged, blocked | **100%** |
| e2e | 40 golden runs | Status, path, action, entity, degradation | **100%** — a regression blocks promotion |

The asymmetry is the point: safety and money thresholds have zero tolerance; quality has a band.

The datasets are generated deterministically by `python -m adintel.evals.generate` as **seed sets**.
They are meant to grow from production (see [flywheel.md](flywheel.md)): Orchestrator cases grew
40 → 60 and Guardrail cases 60 → 120 in the reference deployment. A flat eval set is a system that has
stopped learning.

## Testing LLM output without a flaky suite

1. **Assert on structure, not prose.** Right action on the right entity, not specific words.
2. **LLM-judge with a variance band.** Each judged case runs 3 times and the median is used
   (`evals/judge.py`). If the target is 0.80 the alarm fires at 0.78 (`band` in `thresholds.yaml`).
3. **Separate regression from noise.** One case flipping is noise; five in the same category is a
   regression. The gate compares **per-category** scores to the baseline, not one global number.

## Mock vs mlx mode

| | `--provider mock` | `--provider mlx` |
|-|-------------------|------------------|
| Purpose | CI: proves the harness, rules, deterministic agents and safety layers | Measures your actual models |
| Deterministic agents (DQ, anomaly, constraints, grounding, guardrail code checks, retrieval) | Real | Real |
| LLM agents | Deterministic stand-in handlers | Qwen3.8-27B (frontier), Qwen3.6-35B-A3B (small/report/safety) |
| Judge | Heuristic | Frontier model, 3 runs, median |
| Speed | minutes | longer on a laptop; use `--sample` |

**Promotion rule:** a model, adapter or prompt change must pass `make evals-mlx` locally (or the
production-model equivalent in staging) — passing the mock suite only proves the plumbing.

## Evaluating the fine-tuned Report model

`finetune/evaluate_adapter.py` runs the report suite for base vs adapter vs frontier and reports tone
match (judge), structure compliance, numeric grounding, blind preference (export for human raters),
latency p95 and notional cost per report. In the reference deployment the fine-tuned 8B won the
blind test (47% vs 35% frontier) at 16× lower cost and 3× lower latency, because account managers
value consistency of voice over eloquence.
