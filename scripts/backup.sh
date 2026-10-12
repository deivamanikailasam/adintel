#!/usr/bin/env bash
# Native backup of the Docker Compose stack: MongoDB (mongodump), Redis (RDB snapshot + AOF), local
# secrets, and the audit archive. Writes backups/<UTC timestamp>/ with a SHA-256 manifest.
#
#   scripts/backup.sh                 # → backups/20261012T060000Z/
#   BACKUP_ROOT=/Volumes/ext scripts/backup.sh
#
# Backend-independent alternative (also works with ADINTEL_STORAGE=memory): `adintel backup`.
set -euo pipefail
cd "$(dirname "$0")/.."
COMPOSE="docker compose -f deploy/docker-compose.yml"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="${BACKUP_ROOT:-backups}/$STAMP"
mkdir -p "$OUT"

echo "→ MongoDB"
$COMPOSE exec -T mongo mongodump --quiet --archive --gzip > "$OUT/mongo.archive.gz"

echo "→ Redis"
$COMPOSE exec -T redis redis-cli BGSAVE >/dev/null
sleep 2
$COMPOSE exec -T redis sh -c 'tar -C /data -cf - .' > "$OUT/redis-data.tar"

echo "→ secrets (local platform credentials — keep this backup encrypted)"
[ -d secrets ] && tar -cf "$OUT/secrets.tar" secrets || echo "  (no secrets directory)"

echo "→ audit archive"
[ -d var/audit-archive ] && tar -cf "$OUT/audit-archive.tar" -C var audit-archive || echo "  (no archive yet)"

( cd "$OUT" && sha256sum -- * > SHA256SUMS )
echo "✔ backup written to $OUT"
echo "  verify later with: (cd $OUT && sha256sum -c SHA256SUMS)"
