# AI system card — AdIntel

A plain description of what the AI does and doesn't do, for customers, auditors and the people using it.

## Intended use

Nightly monitoring of paid-advertising performance for agencies: detect material anomalies, investigate
likely causes, propose budget changes, draft the weekly client report, answer staff questions.
**Users:** trained agency staff (account managers, heads of performance). **Not** consumer-facing.

## Out of scope / prohibited

Autonomous spending; decisions about individual people (credit, employment, eligibility); targeting based
on special-category data; use without a named human approver; use on data the agency has no right to process.

## Human oversight (autonomy level L2)

Agents analyse and propose; only code executes, and only after a named person with sufficient authority
types the exact daily exposure and approves. Four-eyes above the senior limit. Kill switches at four levels
and per-agent feature flags. This is a design invariant enforced by architecture tests, not a setting.

## Models

| Role | Local | Production | Notes |
|------|-------|-----------|-------|
| Judgement (orchestrator, analyst, optimizer, complex chat) | Qwen3.8-27B-8bit | Frontier model on Bedrock | Pinned id; promotion gate |
| Volume (mapping, summaries, simple chat), report writing (+ per-tone LoRA), safety classifier | Qwen3.6-35B-A3B-4bit | Smaller hosted model + adapters, Llama Guard | Safety tier fails closed |

Model ids, adapters (SHA-256), weights licences and data terms are in `config/models.yaml`.

## Data

Advertising aggregates per entity and day; agency knowledge-base documents; staff decisions. Inputs are
fenced as untrusted and PII-redacted before model calls. Customer data is never used to train shared
models; brand-voice adapters are per customer.

## Evaluation

Ten suites (~1,100 cases) gate every model, prompt or server change: safety and money-moving behaviours
must score 100% (injection block rate, constraint compliance, cross-tenant leakage 0); a 14-day
outcome check grades executed recommendations against their predictions in production.
Current results: `evals/baseline.json`.

## Known limitations

- Causal analysis is probabilistic; root causes are hypotheses with confidence, shown with evidence.
- Predictions of impact are ranges and are graded after the fact; a high "worsened" rate pauses the optimizer.
- Local models are slower and less capable than production models; the same gates apply to both.
- Report language is checked for numbers, not for every qualitative claim (unsupported claims are flagged).

## Transparency to end clients

Agencies are given a [client disclosure](../client-disclosure.md) for their advertisers. Every released report
carries a signed AI-assistance disclosure and an Ed25519 signature that anyone can verify (report provenance).

## Regulatory position (our assessment — confirm with counsel)

Not a prohibited practice and, on our reading, not an Annex III high-risk use under the EU AI Act: it does
not evaluate natural persons. Transparency duties are met by the disclosure above and by labelling
AI-drafted content. Re-assess if the system is ever used to make decisions about individuals.

## Contact

Model owner: ML lead · Safety owner: Security · Product owner: see `.github/CODEOWNERS`.
