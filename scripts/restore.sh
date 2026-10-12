#!/usr/bin/env bash
# Restore a backup made by scripts/backup.sh into the running Docker Compose stack.
# DESTRUCTIVE: replaces MongoDB collections (mongorestore --drop) and the Redis dataset.
#
#   scripts/restore.sh backups/20261012T060000Z
set -euo pipefail
cd "$(dirname "$0")/.."
SRC="${1:?usage: scripts/restore.sh <backup-dir>}"
COMPOSE="docker compose -f deploy/docker-compose.yml"

( cd "$SRC" && sha256sum -c --quiet SHA256SUMS ) || { echo "✘ checksum mismatch — refusing to restore"; exit 1; }
read -r -p "This replaces the current MongoDB and Redis data. Type 'restore' to continue: " ok
[ "$ok" = "restore" ] || { echo "aborted"; exit 1; }

echo "→ MongoDB"
$COMPOSE exec -T mongo mongorestore --quiet --drop --archive --gzip < "$SRC/mongo.archive.gz"

echo "→ Redis"
$COMPOSE stop redis
$COMPOSE run --rm -T --no-deps --entrypoint sh redis -c 'rm -rf /data/* && tar -C /data -xf -' < "$SRC/redis-data.tar"
$COMPOSE start redis

[ -f "$SRC/secrets.tar" ] && tar -xf "$SRC/secrets.tar"
[ -f "$SRC/audit-archive.tar" ] && mkdir -p var && tar -xf "$SRC/audit-archive.tar" -C var

echo "→ verifying audit chains and the write-once archive"
.venv/bin/adintel verify-audit
.venv/bin/adintel audit-archive --verify
echo "✔ restore complete"
