# L-11: Signed approval records between api-service and executor

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

The executor must only act on a genuine human approval. Locally all processes share one database, so a database row alone is not proof.

## Decision

The api-service signs each approval (HMAC-SHA256 over the canonical approval record) with a key only it and the executor hold; the executor verifies the signature, expiry and snapshot hash before writing. In production this maps to KMS-signed records.

## Consequences

Key rotation must be coordinated between two services.

## Alternatives rejected

Trusting the database row; mTLS between services only.

## Revisit when

Moving to KMS asymmetric signing in production (recommended).
