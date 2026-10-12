# 0031 — The evaluation harness, and what it found

**In one sentence:** every agent now has its own exam with a pass mark, the safety and money exams require
100%, and running them for the first time found three real weaknesses that are now fixed.

## What changed

- `src/adintel/evals/generate.py` → `evals/datasets/*.jsonl` — deterministic seed golden sets:
  orchestrator 60, data quality 80, anomaly 50, analyst 45, optimizer 40 (10 adversarial), report 60,
  guardrail 120 (60 adversarial), RAG 200 (20 leakage probes), injection 200, end-to-end 40.
- `src/adintel/evals/runner.py` — runs every suite against the mock (CI) or your mlx-lm models; asserts on
  structure, never on prose; writes `evals/reports/latest.{json,md}`.
- `src/adintel/evals/judge.py` — LLM-as-judge, 3 runs, median (variance band).
- `src/adintel/evals/gate.py` + `evals/thresholds.yaml` + `evals/baseline.json` — the promotion gate: hard
  100% thresholds, per-category regression check, cost within ±15% of baseline.
- `tests/integration/` — real MongoDB Atlas Local (`$vectorSearch` pre-filter) and Redis (FIFO, visibility
  timeout, DLQ), plus mlx-lm smoke tests (`-m integration`, `-m mlx`).
- New unit tests for the mlx-lm/OpenAI-compatible provider (fake HTTP server: parsing, errors, circuit
  breaker, streaming) and the gate. Coverage gate: **89%** on the code unit tests can reach (the eval
  harness and the Mongo/Redis backends are covered by their own CI jobs).
- `docs/07-evaluation/` (evaluation, flywheel, promotion gate) and `docs/08-testing/testing-strategy.md`.

## What the first eval runs found (and the fixes)

| Finding | Root cause | Fix |
|---------|-----------|-----|
| RAG context precision 0.76 (target > 0.80): "how do I diagnose CPA inflation" missed the *Diagnosing CPA inflation* playbook | No stemming; the reranker never saw document titles | Light stemming + stop words in `rag/bm25.py` (also used by the offline embedder); rerank on title + heading + text → **0.96 precision, 1.00 recall, 0 leakage** |
| Anomaly detection: 12.5% false positives on clean synthetic worlds; short (3-day) spikes missed | A wiggly STL trend end-point biased the expected value; rolling sums made consecutive days correlated; one noisy in-band day reset the "consecutive days" count | Robust level (median of the de-seasonalised last 4 weeks, longer trend window), volume-adaptive ratio smoothing, and "3 of the last 4 days, still visible in the last 2" → **0/40 false positives, 37/40 detected** |
| E2E suite stopped at run 31 with `RateLimited` | The production admission limit (30 runs/minute/tenant) worked as designed | Evals lift the limit for their own process only |
| Evals took > 20 minutes | Memory backend scanned every document on every upsert (quadratic) | Hash-based unique indexes and (tenant, brand) buckets → ~4× faster |
| Two eval brands shared a display name, so their reports were *held* | The guardrail correctly treated the other brand's name as another client's | Unique eval brand names (the guardrail behaviour is right) |

## Current results (mock provider)

All ten suites pass; the gate passes. Orchestrator 1.00 · DQ 1.00 (critical 1.00) · anomaly F1 1.00 / FPR
0.00 · analyst 0.98 (93% detection coverage) · optimizer 1.00 / constraint compliance 1.00 · report
grounding 1.00 · guardrail recall 1.00 / false blocks 0.00 · RAG 0.96 / 1.00 / leakage 0 · injection 1.00 ·
E2E 1.00.

**Important:** mock-provider results prove the plumbing, the deterministic agents and the safety layers.
Run `make evals-mlx` to measure your actual Qwen models before trusting them with recommendations.

## Why it matters (layman's terms)

"It seems to work" is not evidence. This is the exam each part must keep passing — and it already caught
problems that a demo would never have shown.
