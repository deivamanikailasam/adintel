# Operating cadence

| How often | What | Owner | Automated by |
|-----------|------|-------|--------------|
| Daily (automated) | Execution reconciliation, audit hash-chain check, cost check, DLQ check, recommendation expiry, campaign narratives | System | `scheduler/jobs.py` |
| Daily | Outcome tracking (14-day actual vs predicted), automatic at 05:00 UTC | scheduler | `adintel outcomes` |
| Weekly | Eval triage meeting (60 min) from the auto-posted triage page, degradation review, cost by brand | ML lead | `adintel triage`, `docs/07-evaluation/flywheel.md` |
| Every two weeks | Ad-platform API changelog review | Tech lead | — |
| Monthly | Right-sizing, dependency updates, **chaos test against staging**, secret-rotation audit | Tech lead | `tests/chaos/` |
| Quarterly | Model refresh assessment (re-run evals with newer models), fine-tune retrain, **DR test with a real restore**, external red team, architecture review (revisit ADR triggers) | ML lead / Tech lead / Security | `docs/02-decisions/` |
| Annually | SOC 2 audit, full security review, roadmap reset | Sponsor | — |

On-call rotation and weekly handover: [on-call.md](on-call.md).
