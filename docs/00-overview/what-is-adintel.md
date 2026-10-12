# What AdIntel is (start here)

AdIntel is a team of AI agents that watches paid-ad performance for a marketing agency every night,
spots problems, works out why they happened, suggests fixes, and writes the client report.
**A human must approve anything that would spend client money.**

- **Customer (reference scenario):** BrightWave Media, an agency running ads for 12+ client brands on
  Google Ads, Meta, TikTok, LinkedIn and Amazon Ads.
- **This repository:** a local-first build — Python 3.12 agents on LangGraph, an Angular 18 frontend,
  MongoDB (Atlas Local) for operational data plus vector search, Redis for queues and caches, and two
  models you run yourself with `mlx-lm`: **Qwen3.8-27B-8bit** for judgement and
  **Qwen3.6-35B-A3B-4bit** for volume work.

## The business problem

Five analysts were spending about 60% of their week on mechanical work, and problems were caught
5–9 days late, when wasted spend could no longer be recovered.

| Pain | Before AdIntel | Cost to the business |
|------|----------------|----------------------|
| Reconciling data from 5 platforms | ~8 hrs per analyst per week | ~$104k/yr of analyst time |
| Late anomaly detection | 5–9 day median lag | ~$18k–$40k/yr wasted client spend |
| Writing reports by hand | 3–4 hrs per client per week | ~$96k/yr |
| Inconsistent report quality | Client complaints, ~1 churn a year | ~$120k ARR at risk |
| Knowledge in senior heads | 3 months to onboard an analyst | A ceiling on growth |

## Targets agreed before building

| Measure | From | To |
|---------|------|----|
| Analyst time on mechanical reporting | 60% of the week | 15% |
| Time to detect an anomaly | 5–9 days | under 24 hours |
| Report turnaround | 3–4 hrs per client per week | under 10 minutes |

## The six success criteria (signed off up front)

1. Every brand gets a data-complete report by 8 AM Monday, without human help, in 95%+ of weeks.
2. Any CPA or ROAS anomaly over threshold reaches an account manager within 24 hours.
3. Every recommendation cites the historical evidence behind it.
4. Zero cross-tenant data leakage. This is binary.
5. No budget change ever runs without a named human approving it.
6. All-in AI cost per brand per day under $0.60, scaling sub-linearly to 50 brands.
   (Honest note: the detailed cost model only reaches this at about 200 brands — see
   `docs/11-cost/cost-model.md`.)

Each criterion maps to an automated check: criteria 1–2 are SLOs (`docs/06-reliability/slos.md`),
3 is enforced by the Optimizer's citation requirement, 4 is a zero-tolerance eval gate, 5 is the
approval gate + executor design, and 6 is tracked by `cost_events` and the cost dashboard.

## What it deliberately does not do

No creative generation, no media buying, no cross-channel attribution model, and **never autonomous
spend control**. The last one is a product principle, not a v1 limitation.

## One night in production — the story to tell

At 02:00 the scheduler starts each brand's run, staggered over 90 minutes. Each run gets a budget:
25 steps, $2.00 (notional locally) and 900 seconds. The bundled synthetic data reproduces the three
canonical brands so you can watch this locally (`adintel demo`):

| Brand | What happened | Path |
|-------|---------------|------|
| Urban Roast Coffee | Meta CPA ≈ +58% vs expected for 4 days on a retargeting ad set | Full investigation → recommendation pending approval → alert |
| Fitely Activewear | Nothing above low severity | Straight to report |
| NorthPeak Outdoor | Conversions exactly zero since Tuesday vs a 40–70/day baseline | **Stopped**, humans paged, "Reporting paused" |

> The most valuable thing the system did that night was **refuse to produce a deliverable** for
> NorthPeak. A pipeline would have told the client their ROAS collapsed 100% and advised pausing
> their best campaigns.

## How it was delivered (the lifecycle this repo mirrors)

1. **Qualify** — is agentic AI the right shape, or would a dashboard and three SQL queries do?
2. **Discover** — shadow analysts; split mechanical from judgement work; collect past reports.
3. **Shape** — workflow vs agentic, agent boundaries, model tiers, human approval gates.
4. **Thin slice** — one brand, one platform, ingest → anomaly → report, **eval harness built first**.
5. **Harden** — timeouts, degradation, observability, security, cost controls, runbooks
   (60–70% of the engineering effort).
6. **Roll out** — brand by brand, starting in shadow mode.
7. **Prove value and hand over** — same baseline, runbooks, on-call and the decision log.
