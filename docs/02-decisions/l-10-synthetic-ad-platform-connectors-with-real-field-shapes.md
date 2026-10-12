# L-10: Synthetic ad-platform connectors with real field shapes

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

Local development and CI must not need live ad accounts, yet must exercise the messy parts: five different raw field shapes, currencies, micros, string numbers, outages and broken tracking.

## Decision

Seeded synthetic connectors produce raw payloads in each platform's native shape; the deterministic normaliser is the same code used with live connectors. Scenario overrides reproduce the three canonical brands.

## Consequences

Synthetic data hides some real messiness — which is why staging uses anonymised production data.

## Alternatives rejected

Recorded fixtures only (static); calling real sandboxes in unit tests (flaky).

## Revisit when

Nightly contract tests against real read-only sandbox accounts are wired up in production.
