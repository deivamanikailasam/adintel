# Disaster recovery (tested quarterly with a real restore)

| Scenario | RTO | RPO | How |
|----------|-----|-----|-----|
| Worker/task dies | seconds | 0 | Message becomes visible again; run resumes from its checkpoint (`tests/chaos`) |
| AZ failure | < 2 min | 0 | Multi-AZ everywhere (Fargate, Atlas, Redis) |
| Region failure | 4 h | 15 min | Atlas cross-region replica, Terraform into us-west-2, S3 replication |
| Data corruption or bad deploy | 1 h | 5 min | Atlas point-in-time restore to a new cluster, then cut over; blue/green rollback |
| Model provider outage | 0 (degraded) | 0 | Fallback chain in the validation wrapper |
| Accidental deletion | 1 h | 0 | S3 versioning + MFA delete; append-only audit log |

**Local equivalent:** `docker compose` volumes hold Mongo and Redis data; back up with
`docker exec adintel-mongo-1 mongodump --archive > backup.archive` and restore with `mongorestore`.
Redis runs with AOF (`appendfsync everysec`).
