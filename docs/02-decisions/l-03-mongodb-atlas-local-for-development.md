# L-03: MongoDB Atlas Local for development

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

Plain MongoDB Community lacks $vectorSearch; developing against a different retrieval engine than production hides bugs.

## Decision

Use the mongodb/mongodb-atlas-local image (Docker), which supports Atlas Search and Vector Search. An in-memory backend with identical semantics backs unit tests and the zero-dependency demo.

## Consequences

Docker is required for the full local stack.

## Alternatives rejected

Mongo Community + brute-force vectors only; a separate local vector DB.

## Revisit when

Atlas Local diverges from Atlas behaviour.
