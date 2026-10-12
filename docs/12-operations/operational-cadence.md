# Operating cadence

| How often | What | Owner | Automated by |
|-----------|------|-------|--------------|
| Daily (automated) | Execution reconciliation, audit hash-chain check, cost check, DLQ check, recommendation expiry, campaign narratives | System | `scheduler/jobs.py` |
| Weekly | Eval triage meeting (60 min), degradation review, cost by brand | ML lead | `docs/07-evaluation/flywheel.md` |
| Every two weeks | Ad-platform API changelog review | Tech lead | — |
| Monthly | Right-sizing, dependency updates, **chaos test against staging**, secret-rotation audit | Tech lead | `tests/chaos/` |
| Quarterly | Model refresh assessment (re-run evals with newer models), fine-tune retrain, **DR test with a real restore**, external red team, architecture review (revisit ADR triggers) | ML lead / Tech lead / Security | `docs/02-decisions/` |
| Annually | SOC 2 audit, full security review, roadmap reset | Sponsor | — |
