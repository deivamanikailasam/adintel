# 0038 — Changing the shape of stored data, safely and exactly once

**In one sentence:** when a new release needs existing records changed (a new field filled in, say),
there is now one tool that applies those changes in order, once per environment, with a record of what ran.

## What changed

- `storage/migrations/` — `Migration(id, description, up)`, runner with a lock (a second runner is
  refused; a lock older than 30 minutes can be taken over with `--break-stale-lock`), a
  `schema_migrations` record per migration (checksum, duration, result) and drift detection.
- First migrations: `0001_baseline_indexes`, `0002_brand_profile_defaults`, `0003_tenant_active_flag`.
- CLI: `adintel migrate [--status | --check | --dry-run | --backup-dir backups]`.
- Release pipeline: `scripts/ecs_migrate.sh` runs `adintel migrate` as a one-off ECS task in staging and
  production; the job fails if the task does not exit 0.
- ADR [L-13](../02-decisions/l-13-forward-only-data-migrations.md): forward-only, expand/contract, backup
  as the rollback.
- Tests: `tests/unit/test_migrations.py` (order, idempotence, dry run, lock, failure leaves nothing
  recorded and releases the lock, drift, CLI gate).

## Why it matters (layman's terms)

Moving house with a checklist: each box is ticked when it's moved, two people can't move the same box at
once, and if a box breaks you know exactly which one. "Forward-only" means we don't try to un-move boxes;
we take a photo of the old house first (a backup) so we can put everything back if we must.
