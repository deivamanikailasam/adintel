# 0017 — Orchestrator, the agent graph and the run engine

**In one sentence:** the agents are now wired into one supervised team: a manager (the Orchestrator)
decides who works next, every step is time-limited, budgeted, saved and audited, and the whole night
can be replayed end to end in tests.

## What changed

- `agents/orchestrator.py` — **rules first** (e.g. "no anomaly pass yet → anomaly detection", "nothing
  material → straight to report", "confident root cause → Optimizer"); the frontier model is asked only
  for a genuine judgement ("is this worth an investigation?") and its answer must be one of the actions
  allowed at that moment. Loop protection is code: budgets, no-repeat rules, skipping the model when less
  than 25% of the budget remains.
- `graph/build.py` — the LangGraph supervisor graph: fixed start (Ingestion → Data Quality), a gate,
  the supervisor loop, a fixed end (Guardrail → Finalize). Resumed runs enter at the Orchestrator.
- `graph/nodes.py` — the harness around every agent: kill switches, budget and step limits, a per-agent
  timeout with the agent's degradation policy, frozen identity, usage merging and a trace event.
- `graph/finalize.py` — final status, persistence of anomalies/recommendations/reports, audit entries,
  notifications (approval needed, high-severity alerts, "reporting paused"), episodic memory, report
  indexing and metrics. Guardrail-blocked or injection-suspected output is **held and quarantined**.
- `graph/engine.py` — idempotent start, checkpoint after every step, progress events for the UI,
  resume after a crash, graceful stop on shutdown, clean failure on a corrupt checkpoint.
- `seed/` — two agencies, five brands, eight people with approval limits, brand rules and a small
  knowledge base (playbooks, guidelines, incidents, platform notes — plus another agency's confidential
  playbook that must never leak).
- Tests: `tests/e2e/test_one_night.py` replays the three-brand night; `tests/chaos/test_chaos.py` kills
  a worker mid-run, returns 503s, hangs the guardrail, corrupts a checkpoint, exhausts the budget, flips
  a kill switch and crashes an agent; `tests/unit/test_architecture.py` enforces that agents never touch
  the raw database, a provider SDK or write credentials.

## What the test night looks like (mock models)

| Brand | Path | Steps | Model routing calls |
|-------|------|-------|---------------------|
| Urban Roast | ingest → DQ → anomaly → **analyst** → optimizer → report → guardrail | 12 | 1 of 5 hops |
| Fitely | ingest → DQ → anomaly → report → guardrail | 8 | 0 of 3 hops |
| NorthPeak | ingest → DQ → **stop, page humans** | 2 | 0 |

## Why it matters (layman's terms)

This is what makes AdIntel *agentic* rather than a fixed pipeline: three brands on the same night take
three different paths, including the path of deliberately stopping. And because most routing decisions
are plain rules, the common paths are cheap and reproducible.
