# Anti-patterns avoided (and the rule we follow instead)

## Architecture

| Anti-pattern | Rule AdIntel follows | Where it is enforced |
|--------------|----------------------|----------------------|
| The agent that should have been a function | If you can write the assertion, write the function | Ingestion, DQ verdict, anomaly, constraints, grounding are code |
| The workflow in an agent costume | If no real input takes a different path, build a workflow | ADR D-01 revisit trigger; path-diversity metric |
| The agent mesh | Use a supervisor | `graph/build.py`: specialists only return to the Orchestrator |
| Agent proliferation | Boundaries follow responsibilities, not steps | 9 agents, each with its own golden set |
| State in the prompt | State is a typed object in a database; the prompt shows a view of it | `RunState` + `run_checkpoints` |
| The god prompt | Decompose and evaluate each piece | One prompt per agent in `prompts/`, versioned |

## Reliability

| Anti-pattern | Rule | Where |
|--------------|------|-------|
| The unbounded loop | Hard limits in the harness, not instructions in the prompt | `harness/budget.py` |
| Optimistic parsing (`json.loads` with no schema) | Everything through the validation wrapper | `llm/gateway.py` |
| The retrying safety check | Zero retries; fail closed | `agents/guardrail.py` |
| Failing when you could degrade, or degrading silently | Degrade, and disclose it | `harness/degradation.py` → report caveats |
| Timeout inversion | Strictly decreasing timeouts down the stack | `harness/timeouts.py` + test |

## Quality

| Anti-pattern | Rule |
|--------------|------|
| Vibes-based evaluation | Build the eval harness before the second agent (`evals/`) |
| Testing prose | Assert on structure; judge prose separately with a variance band |
| Prompt engineering first | Try knowledge and rules before prompts (the four fixes, in order) |
| Fine-tuning to fix reasoning | Fine-tune for *how it says things*, not what it knows or how well it thinks |
| Unmeasured RAG | Measure retrieval separately from generation (`evals/datasets/rag.jsonl`) |
| Embedding numbers | Summarise to narrative; fetch numbers from the database |

## Cost

| Anti-pattern | Rule |
|--------------|------|
| Frontier by default | Cheapest model that passes its eval |
| The forfeited prompt cache | Stable prefix first; alarm on cache hit rate |
| Not charging failed calls | Every attempt is charged, so dashboards match the invoice |
| Optimising the wrong 2% | At launch scale, optimise infrastructure, not tokens |

## Safety and governance

| Anti-pattern | Rule |
|--------------|------|
| Prompt-based security | Enforce in the query; the model never receives data it shouldn't see |
| The rubber-stamp gate | Make approval fast and evidence-rich; reserve friction for high exposure |
| Autonomous execution "just for low-risk actions" | The category always grows, and "low risk" is defined by the builders, not the people whose money it is |
| An editable audit log | Append-only, hash-chained, verified daily |
| Trusting your own data source | API field values are user-controlled free text: fence everything external |

## Delivery

Demo-driven development; no baseline; building in a sandbox; becoming a dependency; and
**under-scoping production concerns**. The agents are about 30% of the work; timeouts, degradation,
observability, security, governance and cost are the other 70%.
