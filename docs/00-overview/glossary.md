# Glossary (plain words)

| Term | Meaning |
|------|---------|
| **Agent** | A component where a model makes a decision at runtime. AdIntel has nine. |
| **Orchestrator / supervisor** | The "manager" agent that picks which specialist works next. Specialists never call each other. |
| **Harness** | Everything around model calls: state, routing, budgets, retries, timeouts, checkpoints, tracing. |
| **RunState** | The typed "case file" for one brand's run, saved after every step. |
| **Checkpoint** | A saved copy of RunState with a fingerprint, so a crashed run resumes instead of restarting. |
| **Idempotency key** | A fingerprint of "which brand, which period, which goal" so a duplicate trigger maps to the same run. |
| **Budget guard** | Hard limits per run (25 steps, 400k tokens, $2.00, 900 s) enforced in code. |
| **Kill switch** | An emergency stop for everything, one agency, one brand or one agent. |
| **Degradation** | A disclosed partial result (e.g. "TikTok data was unavailable tonight"). |
| **Tier** | A class of model: frontier (careful, slow), small (fast), report (small + style adapter), safety. |
| **mlx-lm** | Apple's library for running language models on Apple Silicon; serves an OpenAI-compatible API. |
| **MoE / A3B** | Mixture-of-experts; "A3B" means about 3 billion parameters are active per token, so it's fast. |
| **LoRA / QLoRA** | A small add-on trained on top of a frozen model to change its style; QLoRA does it on a 4-bit base. |
| **RAG** | Retrieval-augmented generation: look things up first, then answer from what you found. |
| **Hybrid search / RRF** | Combining meaning-based and keyword search, merged by reciprocal rank fusion. |
| **Reranker / cross-encoder** | A slower, more accurate model that re-orders the best search results. |
| **Grounding** | Checking every number in generated text against the database. |
| **Fencing** | Wrapping external text in tags that tell the model "this is data, not instructions". |
| **Prompt injection** | Text that tries to give the model instructions (e.g. hidden in a campaign name). |
| **Guardrail** | The final safety check; blocks, never edits; fails closed. |
| **Fail closed** | When a safety check can't run, the answer is "block", not "allow". |
| **Tenant** | An agency (customer of AdIntel). Brands belong to tenants. |
| **Executor** | The one non-AI service allowed to change ad accounts, only with a signed human approval. |
| **Typed exposure** | Approvers type the exact daily dollar amount, so approval is never a blind click. |
| **Four-eyes** | Two different senior people must approve high-risk or large changes. |
| **Snapshot hash** | A fingerprint of the live ad set when the recommendation was made; if it changed, approval is refused. |
| **Hash chain** | Each audit entry includes the previous entry's fingerprint, so edits are detectable. |
| **STL** | Seasonal-trend decomposition — separates the weekly rhythm from the trend and the noise. |
| **Isolation Forest** | An outlier detector used as a second opinion on anomalies. |
| **Golden dataset** | Labelled test cases an agent must keep passing. |
| **LLM-as-judge** | Using a model to grade prose quality, run 3 times and take the median. |
| **Promotion gate** | The checklist (automated + human) a change must pass to reach production. |
| **Shadow mode** | Running the new version alongside without releasing its output, to compare. |
| **Notional cost** | A pretend price for free local models, so budgets work as they would in production. |
