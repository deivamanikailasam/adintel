# D-03: MongoDB for operational and vector data

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

Recommendations need operational data, time series and vector search with tenant filters. Two stores mean a sync job, a second failure domain and a second place to enforce tenant isolation — the second store is where the leak happens.

## Decision

MongoDB (Atlas in production, Atlas Local in development) holds operational data, time-series metrics and vectors. Filter plus vector search run in one query.

## Consequences

Search tuning is Atlas-specific; the in-memory backend reproduces semantics (pre-filter, deterministic ties) for tests.

## Alternatives rejected

Pinecone/Weaviate (second system to sync and secure); pgvector (fights heterogeneous ad-platform JSON); Timestream/InfluxDB (better TS engines but a third datastore).

## Revisit when

Corpus exceeds ~10M vectors and Search Nodes can't absorb the contention.
