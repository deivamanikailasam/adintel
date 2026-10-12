# D-01: Agentic (LangGraph) over a fixed workflow

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

Three brands on one night need three different jobs: a full investigation, a straight-to-report run and a deliberate stop. A fixed DAG handles that with nested conditionals that multiply and still cannot handle the case nobody designed for. Pipelines are built to complete, so they are structurally bad at deciding to stop.

## Decision

Use a LangGraph supervisor graph where a model (with rules first) decides at runtime which specialist runs next and when the job is done.

## Consequences

Less predictable and harder to test than a DAG, so: deterministic rules pre-empt the model on common paths (~70% of hops), every agent has a golden dataset, and the budget guard bounds cost.

## Alternatives rejected

Step Functions / Airflow (fixed DAGs); CrewAI (process model closer to a scripted pipeline); a raw while-loop (would mean rebuilding checkpointing, interrupts and tracing).

## Revisit when

Six months of data show more than 90% of runs take one identical path — then collapse to a workflow.
