# 0032 — The documentation front door

**In one sentence:** anyone opening the repository now finds, on one page, what AdIntel is, how to try it
in 30 seconds, and exactly which document answers their question.

## What changed

- `README.md` — what AdIntel is, local vs production at a glance, the 30-second demo, a system diagram,
  what's inside, quality gates, documentation map and the five principles.
- `docs/README.md` — a "start here" table by role (new reader, installer, production owner, design
  reviewer, risk/legal/security approver, operator), every section with links, and a repository map.
- `docs/00-overview/glossary.md` — ~35 terms in plain words (harness, checkpoint, fencing, fail closed,
  typed exposure, four-eyes, snapshot hash, MoE/A3B, LoRA, RRF…).
- `docs/00-overview/faq.md` — the questions people actually ask, answered in two or three sentences.

## Why it matters (layman's terms)

Good documentation is part of governance: a system is only controllable if the people responsible for it
can understand it without the people who built it.
