# L-13: Forward-only data migrations with expand/contract

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

MongoDB has no schema, so nothing forces old documents to match new code. Blue/green deploys run old and
new code against the same database for up to 30 minutes. Indexes are already created idempotently at
startup; what was missing is a controlled way to change the *shape* of existing documents exactly once
per environment.

## Decision

- Migrations live in `src/adintel/storage/migrations/versions.py`, ordered, append-only, each idempotent.
- `adintel migrate` applies pending ones under a lock and records id, checksum, duration and result in
  `schema_migrations`; `--status` reports drift if applied code is later edited; `--check` fails CI/deploys
  when anything is pending.
- **Forward-only:** no down-migrations. The rollback is the logical backup taken just before
  (`--backup-dir`) and `adintel restore`.
- **Expand/contract:** a release may only *add* fields or collections; removals ship in a later release
  once no running code reads them. Readers tolerate documents both before and after a migration.
- The release pipeline runs migrations as a one-off ECS task (`scripts/ecs_migrate.sh`).

## Consequences

Easier: deploys never need a maintenance window; a failed migration leaves an exact record and releases
its lock. Harder: two-step removals take two releases; developers must write tolerant readers (reviewed in
PRs; `Model.from_doc` already ignores unknown fields).

## Alternatives rejected

- **Down-migrations** — rarely tested, and wrong after data has changed under the new code; a verified
  backup is a more honest rollback.
- **Migrate on application start** — N replicas race; a slow migration blocks health checks and triggers a
  rollback mid-migration.
- **A schema tool (e.g. Mongock, migrate-mongo)** — adds a JVM/Node runtime to a Python service for a
  feature that is ~150 lines here and must also work on the memory backend.

## Revisit when

A single migration takes longer than 10 minutes on production data (then: batched background migrations
with progress checkpoints), or the team adopts a relational store.
