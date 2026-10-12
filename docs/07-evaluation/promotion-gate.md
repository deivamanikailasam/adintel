# The promotion gate

Nothing reaches production without **all** of:

1. **No category regression offline** (`make gate` compares per-category scores with `evals/baseline.json`,
   tolerance 2 points).
2. **The E2E suite green** (40 golden runs, structured assertions).
3. **100% guardrail recall, 100% constraint compliance, 100% grounding, 100% critical DQ accuracy,
   100% injection block rate and zero leakage** (hard thresholds in `evals/thresholds.yaml`).
4. **Cost within ±15% of baseline** per run path (clean / investigation / abort).
5. **A 3-day shadow run on 20% of traffic** (staging/production; outputs compared, not released). Implemented
   by `llm/shadow.py`: add the candidate as a tier, set `shadow: { <champion tier>: { challenger: <tier>,
   sample_rate: 0.2 } }` in `config/models.yaml`, and after three days `adintel shadow-report` (or
   `GET /admin/shadow`) must say **ready** for every agent on that tier: ≥ 50 samples, ≥ 98 % schema
   validity, ≥ 85 % field agreement with the champion, and an acceptable p50 latency. The safety tier is
   never shadowed; challenger calls are never charged to a run's budget and never used.
6. **A named human sign-off** recorded in the decision log.

Model and adapter changes are additionally **canaried at 5% for 48 hours**; rollback is changing a
version pointer (`config/models.yaml` / adapter path), in seconds.

```bash
make evals && make gate                     # CI on every PR
python -m adintel.evals.gate --write-baseline  # after a reviewed, intentional improvement
```

Accepting a new baseline is itself a reviewed change: commit `evals/baseline.json` with the PR that
justified it.
