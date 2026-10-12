# The agent team

Nine agents plus one deliberately dumb executor. Each agent owns a **responsibility**, not a step,
and **none of them can write to an ad platform.**

| # | Agent | What it owns, in plain words | Model tier (local) | Can it change anything outside? | Code |
|---|-------|------------------------------|--------------------|---------------------------------|------|
| 1 | Orchestrator (supervisor) | Decides what happens next and when the run is done | Rules first; frontier (`Qwen3.8-27B-8bit`, temp 0) for real decisions | No, delegates only | `agents/orchestrator.py` |
| 2 | Ingestion | Gets correct, normalised data from 5 ad platforms | Deterministic code; small model only *proposes* mappings for unknown fields | Read-only | `agents/ingestion.py` |
| 3 | Data Quality | Decides whether the data is trustworthy enough to reason over | Deterministic rules; small model phrases the summary | No | `agents/data_quality.py` |
| 4 | Anomaly Detection | Statistically finds what changed | **No LLM**: STL seasonal decomposition + Isolation Forest | No | `agents/anomaly.py` |
| 5 | Analyst | Explains *why* it changed | Frontier + sandboxed pandas execution | No | `agents/analyst.py` |
| 6 | Optimization | Proposes what to do about it | Frontier + RAG | No, proposes only | `agents/optimizer.py` |
| 7 | Report | Writes the client-facing report in brand voice | Small model + LoRA adapter (fine-tuned), temp 0.2 | No | `agents/report.py` |
| 8 | Chat | Answers ad-hoc account-manager questions | Routed: deterministic lookup → small → frontier | No | `agents/chat.py` |
| 9 | Guardrail | Decides whether an output is safe to release | Deterministic checks + small-model safety classifier | No, blocks only | `agents/guardrail.py` |
| — | Action Executor (*not an agent*) | Calls ad-platform write APIs after approval | **No LLM at all** | Yes, only with a valid, signed approval record | `executor/` |

## Why the boundaries are where they are

- **Data Quality is separate from Ingestion.** Ingestion asks "did the API call work and did I map
  fields right?". Data Quality asks "does this data make sense?". Zero conversions after six months
  of daily conversions is a *successful* API call and *untrustworthy* data. Merge them and bad data
  flows silently into analysis.
- **Anomaly Detection has no LLM.** LLMs are poor at precise time-series detection, vary run to run
  and can't give a confidence interval. STL + Isolation Forest is deterministic, ~1,000× cheaper and
  auditable: you can show the client the exact seasonal band that triggered the flag.
- **Analyst and Optimizer are separate.** Diagnosis and prescription are different skills. Separated,
  a bad recommendation can be traced to either a wrong diagnosis or a wrong prescription.
- **Report is small and fine-tuned.** One narrow job, done hundreds of times a week, in a consistent
  style — exactly where a fine-tuned small model wins.
- **Guardrail is a hybrid.** Most checks are code (PII regex, other-tenant names, banned claims,
  numeric re-check), and they run first and can't be bypassed. A classifier handles the semantic tail.
- **The Executor is dumb on purpose.** Keeping money-moving code free of any model means no prompt
  can ever turn into a spend.

## Why nine agents, not three or twenty?

An agent boundary follows a *responsibility* boundary, not a step boundary. Fetching and normalising
were not split, because normalising is deterministic code inside ingestion. Every boundary adds
latency, failure surface and a state hand-off, so twenty agents would be "step boundaries wearing
agent costumes". The payoff of nine: **each agent has its own golden dataset** in `evals/datasets/`,
so a quality regression can be traced to one agent.

## Contract every agent follows

```python
def run(state: RunState, ctx: AgentContext) -> dict:   # returns a partial state update
```

- Agents are **stateless functions of `RunState`**. Everything they need is in state or fetched
  through `ctx` (tenant-scoped repositories, the LLM gateway, the retriever).
- Agents never receive the raw database handle. `ctx.repo(...)` is always tenant-scoped.
- Agents never call a model SDK directly. They call `ctx.llm.structured(...)` (the validation
  wrapper), which enforces schema, repair, retries, timeouts, budget charging, fallback, fencing,
  PII redaction and hashing.
- Agents never return `tenant_id` or `brand_id`; the harness rejects any update that tries.
