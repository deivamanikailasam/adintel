# Cost, tokens and latency

> Locally, model inference is free — AdIntel charges **notional** prices that mirror the production model
> each tier stands in for (ADR L-07), so budgets, caps and the ±15% cost gate stay meaningful.

## Reference production cost model (12 brands)

| Run type | Share of runs | Cost per run |
|----------|---------------|--------------|
| A. Clean weekly run | ~55% | $0.0076 |
| B. Anomaly with full analysis | ~30% | $0.1192 |
| C. Aborted on data quality | ~5% | $0.0009 |
| D. Chat question, blended | ~10% of interactions | $0.0083 |

In a type-B run the Analyst ($0.0570) and Optimizer ($0.0396) are most of the cost. Chat splits into 18%
cache hits (free), 47% simple lookups ($0.0004) and 35% complex RAG + frontier ($0.0231).

| Monthly line (12 brands) | Monthly |
|--------------------------|---------|
| All model spend | $21.93 |
| MongoDB Atlas M30 + Search Nodes | $610 |
| SageMaker endpoints (3) | $302 |
| Fargate (api, worker, executor) | $186 |
| ElastiCache, S3, CloudFront, NAT, misc | $174 |
| Langfuse self-hosted | $48 |
| **Total** | **~$1,342** — model tokens are 1.6% |

**The finding that changes priorities:** at launch scale, optimise infrastructure, not tokens. Squeezing
30% out of tokens saves $6.60/month; right-sizing Atlas or merging SageMaker endpoints saves hundreds.

| Brands | Total / month | Per brand per day | Model share |
|--------|---------------|-------------------|-------------|
| 12 | $1,342 | $3.73 | 1.6% |
| 50 | $1,971 | $1.31 | 4.6% |
| 200 | $3,765 | $0.63 | 9.7% |
| 1,000 | $11,025 | $0.37 | 16.6% |

**Honest note:** the success criterion said "< $0.60 per brand per day at 12 brands"; the cost model only
reaches ~$0.63 at about 200 brands. Infrastructure is fixed cost that amortises with scale.

**Local deployment:** infrastructure is your laptop; model cost is electricity. The notional dashboard
(`Grafana → AdIntel — Models & cost`) shows what the same workload would cost in production.

## Cost controls (all code)

Hard $2.00 cap per run; per-tenant daily cap with a P3 alert at 80% and a soft stop at 100%; cost anomaly
alert on a 2× day-over-day jump; every attempt charged (failures included); weekly cost review by brand and
agent.

## Token discipline

Prompt caching (stable prefix first; system prompts are static by registry rule) · RAG top-k discipline
(fetch 25, rerank, pass 6) · structured output · data by reference and pre-computed facts (no 40k-token
tables) · deterministic pre-emption (~70% of orchestration hops use zero tokens) · hard per-agent token
budgets in `config/models.yaml` · truncation with disclosure.

## Latency: two different problems

- **Batch (nightly):** finish by 08:00 — optimise throughput and cost; parallel ingestion; 90-minute stagger.
- **Interactive (chat):** first token matters — SSE streaming (the biggest single win), semantic cache,
  routing ~half of questions to the fast model, prompt caching, nightly pre-computation.

Local note: on Apple Silicon the 27B frontier tier is the latency bottleneck; that is why chat lookups go
to the MoE model (~3B active parameters per token).
