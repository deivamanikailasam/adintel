# 0002 — Architecture, system design and decision records

**In one sentence:** before writing code we drew the blueprint and wrote down *why* every wall is
where it is, so nobody knocks one down without knowing it was load-bearing.

## What changed

- `docs/00-overview/what-is-adintel.md` — the business problem, targets, the six signed-off success
  criteria, what AdIntel deliberately does *not* do, and the "one night in production" story.
- `docs/01-architecture/` — the architecture (diagrams of the services and the agent graph), the
  harness (budgets, checkpoints, idempotency, kill switches, timeouts), the nine agents and why their
  boundaries sit where they do, the model strategy for your two mlx-lm models, RAG and memory, the
  data model and multi-tenancy, and a table that maps **every AWS service in the original design to
  its local replacement**.
- `docs/02-decisions/` — 24 architecture decision records (ADRs): the 12 original design decisions
  plus 12 decisions specific to running locally (for example: why the 27B dense model is the
  "frontier" tier and the 35B mixture-of-experts model is the fast tier). Each has a
  **"revisit when"** trigger.
- `docs/anti-patterns.md` and `docs/02-decisions/open-questions.md`.

## Why it matters (layman's terms)

The most expensive mistakes in AI systems are not bugs in the code, they are wrong decisions that
look right: letting an AI move money on its own, letting two clients' data share a cache, trusting a
number the AI wrote. Writing each decision down with the reason and the condition that would change
it is how a team keeps those decisions honest over time.

## The two models, in plain words

- **Qwen3.8-27B-8bit** is the careful senior analyst: slower, but the best judgement you have. It
  decides routing, explains root causes and proposes budget changes.
- **Qwen3.6-35B-A3B-4bit** is the fast junior: it only "wakes up" about 3B of its parameters per word,
  so it is quick. It writes reports (with a style adapter), answers simple chat questions and runs
  the safety check.
