# L-07: Notional pricing for free local models

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

Local inference has no bill, but the budget guard, per-tenant caps and the ±15% cost gate need a currency.

## Decision

Charge every attempt (including failures and repairs) at notional per-token prices mirroring the production model each tier stands in for.

## Consequences

Local dollar figures are estimates of production cost, not real spend; dashboards label them 'notional'.

## Alternatives rejected

Counting tokens only (no comparable budget); disabling cost controls locally (they'd be untested).

## Revisit when

Never — this is how cost controls stay tested.
