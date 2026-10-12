# 0037 — A tamper-proof copy of the audit log, and backups you have actually restored

**In one sentence:** every night the audit history is copied to storage that cannot be changed and
compared with the live database, and there are now one-command backups that prove themselves restorable.

## What changed

- `audit/archive.py` — incremental nightly segments (`<tenant>/<from>-<to>.jsonl` + `.sha256`, files made
  read-only), optional upload with Object Lock retention, `verify_archive` (re-checks the chain from the
  archive alone) and `compare_with_database` (finds entries rewritten after archiving). Scheduler 03:45 UTC,
  P1 on mismatch; CLI `adintel audit-archive [--verify]`.
- Docker Compose: `minio` + `minio-init` create bucket `adintel-audit` with Object Lock (GOVERNANCE, 30
  days locally); the app containers upload to it. Production: S3, COMPLIANCE, 2,557 days — same code.
  The image now installs the `aws` extra (boto3).
- `ops/backup.py` — logical backup of every collection, restore (verifies checksums, refuses a non-empty
  target without `--force`, recreates indexes, verifies audit chains) and a restore drill into a scratch
  database. CLI `backup` (drill runs automatically), `restore`, `restore-drill`.
- `scripts/backup.sh` / `scripts/restore.sh` — native `mongodump`/Redis/secrets/archive backup with
  `SHA256SUMS`; restore checks sums and asks for confirmation.
- Docs: audit, disaster recovery, runbook, security controls, local setup, promotion checklist.
- Tests: `tests/unit/test_archive_backup.py` — including the attack the hash chain alone cannot catch.

## Why it matters (layman's terms)

A hash chain is like numbered, sealed pages in a ledger: you can't quietly change one page. But a
determined insider could rewrite the whole ledger from page 50 onwards with new seals. The archive is a
photocopy of each night's pages locked in a safe nobody can open; if the ledger and the photocopies ever
disagree, the alarm goes off. And a backup you've never restored is a hope, not a backup — so every backup
now restores itself into a scratch copy and checks that everything came back.
