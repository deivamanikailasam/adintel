# The graph and the harness

> **In plain words:** the *harness* is everything around the model calls — state, routing, budgets,
> retries, tracing and pauses. Production agent systems are won or lost here, not in the prompts.

## Run lifecycle

Every run follows the same eight steps (`src/adintel/graph/engine.py`):

1. **Trigger** — a scheduler job, an API call (`POST /runs`) or a chat message.
2. **Admission** — check the tenant, quota and kill switches; compute the idempotency key; assign a run ID.
3. **State init** — build the `RunState` and save checkpoint v0.
4. **Loop until done** — the Orchestrator picks the next action, the budget guard checks it,
   the specialist runs, its result merges into state, a checkpoint is saved and a progress event
   is published (streamed to the UI over SSE).
5. **Guardrail** — the final output always goes through the Guardrail Agent. It can't be skipped.
6. **Persist** — save the report, recommendations and audit records.
7. **Notify** — completion events, alerts, approval-queue entries.
8. **Teardown** — emit the trace, cost record and metrics.

## The shared state (`RunState`)

One typed Pydantic object holds everything (`src/adintel/domain/state.py`) and is checkpointed after
every step. Agents are stateless functions of that state.

- **Identity is frozen.** `tenant_id` and `brand_id` are set once. The harness rejects any node
  update that tries to change them, and data access always reads them from state — never from model
  output — so an agent can't talk its way into another tenant's data.
- **Big data by reference.** Raw metric rows live in `metrics_daily`; state holds a pointer
  (`metrics_ref`) and small pre-computed summaries. Inlining a 40,000-row table would make every
  checkpoint expensive.
- **Safe parallel writes.** List fields like `traces` and `degradations` use LangGraph reducers
  (`operator.add`) so parallel agents append rather than overwrite.
- **Explicit statuses.** `pending, running, awaiting_approval, completed, failed, degraded,
  aborted_data_quality, killed`. Data quality has three verdicts: `trustworthy`, `degraded`
  (usable with a disclosed caveat) and `untrustworthy` (hard stop).

## Three harness controls

| Control | What it does | Why it matters | Code |
|---------|--------------|----------------|------|
| **Budget guard** | Before every dispatch, checks steps (25), tokens (400k), cost ($2.00) and wall clock (900 s) | A hard gate in code, not a request to the model. When hit, the run doesn't fail: it produces a best-effort deterministic report marked DEGRADED. It is also the loop protection. | `harness/budget.py` |
| **Checkpointing** | State saved after every step, keyed by run ID, with a content hash | A run that touched paid APIs must resume, not restart. A corrupt checkpoint fails cleanly instead of resuming from garbage. | `harness/checkpoint.py` |
| **Idempotency key** | `sha256(tenant, brand, period, goal, schedule_date)` with a unique index | Schedulers deliver at least once and people double-click. A duplicate trigger maps to the existing run. | `harness/idempotency.py` |

## How resume works

The graph's entry is conditional: if the restored state already has a data-quality verdict, the
graph enters at the Orchestrator instead of re-ingesting. The Orchestrator then picks up exactly
where the run left off, because "what has been done" is recorded in state, not in the call stack.

## Stopping an agent loop — four layers, none of them a prompt

1. The hard budget guard (steps, tokens, time, dollars).
2. A no-repeat rule in routing code (each specialist has a maximum number of visits).
3. Rules that skip the model entirely when less than 25% of the budget remains.
4. A best-effort finalize instead of a failure.

## Timeouts nest, and each one is a decision

Each inner timeout is strictly shorter than the one around it, otherwise the outer layer gives up
while the inner one is still working and still being billed:

```
run 900 s → per-step dispatch 300 s → agent 45–240 s → LLM call 30–90 s → HTTP client 25–85 s → TCP connect 5 s
```

`harness/timeouts.py` defines these values and a unit test asserts the ordering, so a config change
can never invert them.

## Kill switches

Four levels — `global`, `tenant`, `brand`, `agent` — stored in the `kill_switches` collection and
checked at admission **and before every dispatch**. Flipping one takes effect on the next hop of
every in-flight run. `POST /admin/kill-switches` (role `admin`) manages them.

## Concurrency

Ingestion fetches all platforms in parallel, each with its own timeout and circuit breaker. One slow
platform can't block the run, and a failed platform becomes a *disclosed degradation*, not a failure.
