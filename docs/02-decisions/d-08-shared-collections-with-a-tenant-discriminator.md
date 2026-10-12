# D-08: Shared collections with a tenant discriminator

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

At 12–50 brands per agency, a database per tenant means 50 connection pools, 50 index sets and a fan-out for cross-client analytics the agency wants.

## Decision

Shared collections; every document carries tenant_id; TenantScopedRepo is the only data path; every index leads with tenant_id.

## Consequences

Isolation is enforced in code, so it is tested in code: an explicit unit test that querying another tenant raises, plus a zero-leakage eval gate.

## Alternatives rejected

Database per tenant; collection per tenant.

## Revisit when

A client contractually requires physical isolation.
