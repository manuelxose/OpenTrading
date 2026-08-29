#!/usr/bin/env bash
# OpenTrading — automated backup (PostgreSQL + MinIO). See docs/DISASTER_RECOVERY.md.
#
# Usage:   OT_BACKUP_DIR=/var/backups/opentrading ./scripts/backup.sh
#
# Environment (all read from .env.prod when present):
#   OT_BACKUP_DIR        destination root (default: ./backups — mount/override in prod)
#   OT_BACKUP_RETENTION  how many daily PostgreSQL dumps to keep (default 14)
#   PGPASSWORD           Postgres password (or use OT_POSTGRES_PASSWORD below)
#   OT_POSTGRES_PASSWORD fallback for PGPASSWORD
#   OT_POSTGRES_HOST     default 127.0.0.1
#   OT_POSTGRES_PORT     default 5432
#   OT_POSTGRES_USER     default ot_readonly (SELECT-only role; pg_dump works)
#   OT_POSTGRES_DB       default opentrading
#   OT_MINIO_HOST        default 127.0.0.1:9000
#   OT_MINIO_ACCESS_KEY / OT_MINIO_SECRET_KEY
#
# Exit codes: 0 ok, 1 dump failed, 2 mirror failed, 3 retention cleanup failed.
set -euo pipefail

cd "$(dirname "$0")/.."

[ -f .env.prod ] && set -a && . ./.env.prod && set +a

STAMP="$(date -u +%Y%m%d-%H%M%S)"
BACKUP_ROOT="${OT_BACKUP_DIR:-./backups}"
PG_DIR="$BACKUP_ROOT/postgres"
MINIO_DIR="$BACKUP_ROOT/minio"
RETENTION="${OT_BACKUP_RETENTION:-14}"

mkdir -p "$PG_DIR" "$MINIO_DIR"

export PGPASSWORD="${PGPASSWORD:-${OT_POSTGRES_PASSWORD:-}}"
PGHOST="${OT_POSTGRES_HOST:-127.0.0.1}"
PGPORT="${OT_POSTGRES_PORT:-5432}"
PGUSER="${OT_POSTGRES_USER:-ot_readonly}"
PGDB="${OT_POSTGRES_DB:-opentrading}"

echo "[backup] dumping PostgreSQL $PGDB @ $PGHOST:$PGPORT as $PGUSER …"
pg_dump --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" \
  --format=custom --no-owner --verbose \
  --file="$PG_DIR/opentrading-$STAMP.dump" "$PGDB"
echo "[backup] PostgreSQL dump complete."

echo "[backup] mirroring MinIO buckets …"
if command -v mc >/dev/null 2>&1; then
  export MC_HOST_opentrading="http://${OT_MINIO_ACCESS_KEY:-}:${OT_MINIO_SECRET_KEY:-}@${OT_MINIO_HOST:-127.0.0.1:9000}"
  mc --insecure mirror --overwrite --remove opentrading "$MINIO_DIR/buckets"
else
  echo "[backup] WARNING: 'mc' not installed — MinIO mirror skipped." >&2
  exit 2
fi
echo "[backup] MinIO mirror complete."

echo "[backup] applying retention (keep $RETENTION PostgreSQL dumps) …"
ls -1t "$PG_DIR"/opentrading-*.dump 2>/dev/null | tail -n +"$((RETENTION + 1))" \
  | xargs -r rm -v || exit 3

echo "[backup] done: $PG_DIR / $MINIO_DIR"
