# D-07: L2 autonomy: a human approves all execution

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

Autonomous execution saves a few hours. One wrong autonomous budget change can lose a client. The asymmetry is not close. The sponsor signed this as a business decision.

## Decision

AI proposes with evidence, a named human approves (typing the exact exposure), the system executes. The approval matrix and seven server-side checks are code.

## Consequences

The gate must be fast and evidence-rich or it gets rubber-stamped; the UI keeps evidence one click away and low-exposure changes one tap.

## Alternatives rejected

L3 (execute, human can override afterwards) — considered for low-risk actions only, not committed; L4 full autonomy — explicitly rejected.

## Revisit when

Only with 12 months of calibration data and explicit client opt-in.
