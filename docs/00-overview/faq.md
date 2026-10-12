# FAQ

**Why agentic and not a workflow?** Three brands on one night needed three different jobs, and the
broken-tracking brand needed the system to *stop*. The clean path costs a fraction of the full path because
the Orchestrator skips unneeded work. If six months of data show 90% of runs take one path, collapse to a
workflow (ADR D-01).

**When would you *not* build multi-agent?** If no real input takes a different path, no step needs
judgement on ambiguous evidence, and being wrong isn't expensive — use a workflow, or three SQL queries and a
dashboard.

**How do you stop an agent loop?** Four layers, none a prompt: the hard budget guard; a no-repeat rule in
routing code; rules that skip the model when < 25% of the budget remains; a best-effort finalize instead of
failure.

**A model returns malformed JSON — what happens?** The wrapper validates against the Pydantic schema, sends a
repair turn with the exact error, at most twice, charging the budget every attempt; then the fallback model;
then the agent's degradation policy.

**What if a worker dies mid-run?** State is checkpointed after every step; the message becomes visible again
and another worker resumes from the last checkpoint. The idempotency key stops duplicate triggers creating a
second run.

**Malicious campaign name?** Fenced and flagged — but the real defence is that any output must pass schema
checks, code constraints (25% max change), the guardrail and a human typing the exposure, and the Optimizer
has no execution tool.

**An attacker gets into the agent worker?** They can call models (cost alerts catch that). They can't spend
money: write credentials and the executor role are disjoint, and execution needs a signed approval plus a
snapshot check.

**Why human approval — isn't that slow?** Autonomy saves hours; one wrong autonomous budget change can lose
a client. The gate is fast and evidence-rich so it isn't rubber-stamped.

**How do you know it's working?** Recommendation approval rate is the best proxy; predicted vs actual impact
14 days later is the only objective signal; plus per-agent golden sets and the weekly triage.

**Costs doubled overnight?** In order: a lost prompt cache from a prompt-order change; a repair-loop spike
after a schema change; loops hitting step limits; one tenant triggering many runs.

**Why is the 27B model "frontier" and the 35B model "small"?** The 35B is a mixture-of-experts with ~3B
active parameters per token — fast and cheap per call. The dense 27B at 8-bit uses all its parameters on
every token and keeps more precision — slower, but better judgement (ADR L-02).

**Can I run it with one model?** Yes — point both tiers at one server (`docs/13-setup/local-setup.md` §3b).

**Does any data leave my machine locally?** No. Models run in mlx-lm on your Mac; Langfuse, Mongo and Redis
run in local containers; synthetic ad platforms are in-process.
