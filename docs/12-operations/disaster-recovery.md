# Disaster recovery (tested quarterly with a real restore)

| Scenario | RTO | RPO | How |
|----------|-----|-----|-----|
| Worker/task dies | seconds | 0 | Message becomes visible again; run resumes from its checkpoint (`tests/chaos`) |
| AZ failure | < 2 min | 0 | Multi-AZ everywhere (Fargate, Atlas, Redis) |
| Region failure | 4 h | 15 min | Atlas cross-region replica, Terraform into us-west-2, S3 replication |
| Data corruption or bad deploy | 1 h | 5 min | Atlas point-in-time restore to a new cluster, then cut over; blue/green rollback |
| Model provider outage | 0 (degraded) | 0 | Fallback chain in the validation wrapper |
| Accidental deletion | 1 h | 0 | S3 versioning + MFA delete; append-only audit log |

## Local backups and restores

| Tool | Covers | Use when |
|------|--------|----------|
| `scripts/backup.sh` / `scripts/restore.sh` | MongoDB (`mongodump --gzip`), Redis data (RDB + AOF), `secrets/`, audit archive; `SHA256SUMS` manifest | Docker Compose stack; fastest for real data volumes |
| `adintel backup --out backups/` | Every catalogued collection as JSONL + SHA-256 manifest, **followed automatically by a restore drill** | Any backend (memory or Mongo); portable; what the tests exercise |
| `adintel restore <dir> [--force]` | Verifies checksums, refuses a non-empty database without `--force`, recreates indexes, then verifies every audit chain | Recovering into a fresh or wiped database |
| `adintel restore-drill <dir>` | Restores into a scratch in-memory database and compares counts and chains — touches nothing live | Proving a backup is good (run weekly locally, quarterly in prod against Atlas PITR) |

Suggested local schedule (cron/launchd): `scripts/backup.sh` nightly, keep 14; `adintel restore-drill` on
the newest weekly. Keep backups that include `secrets.tar` on an encrypted volume. Redis runs with AOF
(`appendfsync everysec`), so queue contents survive a container restart without a restore.
