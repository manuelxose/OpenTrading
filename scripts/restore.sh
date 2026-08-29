#!/usr/bin/env bash
# OpenTrading — restore from backups produced by scripts/backup.sh.
# See docs/DISASTER_RECOVERY.md. This script restores data only; it does not
# start or stop services, and it refuses to run against a non-empty database
# unless OT_RESTORE_FORCE=1.
#
# Usage:   OT_RESTORE_DUMP=/path/opentrading-YYYYmmdd-HHMMSS.dump \
#          OT_RESTORE_MINIO_SRC=/path/backups/minio/buckets ./scripts/restore.sh
#
# Environment:
#   OT_RESTORE_DUMP        path to the pg_dump custom-format file (required)
#   OT_RESTORE_MINIO_SRC   optional; when set, mirrors this dir into MinIO
#   PGPASSWORD / OT_POSTGRES_PASSWORD
#   OT_POSTGRES_HOST/PORT  default 127.0.0.1:5432
#   OT_POSTGRES_USER       default ot_app (DML role; needs DDL via migrator? no:
#                          pg_restore requires the same privileges the tables
#                          had — run as the postgres superuser role in practice)
#   OT_POSTGRES_DB         default opentrading
#   OT_MINIO_HOST / ACCESS_KEY / SECRET_KEY
#   OT_RESTORE_FORCE=1     allow restore into a non-empty database
set -euo pipefail

cd "$(dirname "$0")/.."

[ -f .env.prod ] && set -a && . ./.env.prod && set +a

DUMP="${OT_RESTORE_DUMP:-}"
if [ -z "$DUMP" ] || [ ! -f "$DUMP" ]; then
  echo "error: OT_RESTORE_DUMP must point to an existing pg_dump file" >&2
  exit 2
fi

export PGPASSWORD="${PGPASSWORD:-${OT_POSTGRES_PASSWORD:-}}"
PGHOST="${OT_POSTGRES_HOST:-127.0.0.1}"
PGPORT="${OT_POSTGRES_PORT:-5432}"
PGUSER="${OT_POSTGRES_USER:-ot_app}"
PGDB="${OT_POSTGRES_DB:-opentrading}"

PSQL=(psql --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$PGDB")

TABLE_COUNT="$("${PSQL[@]}" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")"
if [ "${TABLE_COUNT:-0}" -gt 0 ] && [ "${OT_RESTORE_FORCE:-0}" != "1" ]; then
  echo "error: target database is not empty ($TABLE_COUNT tables). " \
       "Set OT_RESTORE_FORCE=1 to overwrite (drops the schema first)." >&2
  exit 3
fi

echo "[restore] dropping existing public schema objects (OT_RESTORE_FORCE=${OT_RESTORE_FORCE:-0}) …"
"${PSQL[@]}" -v ON_ERROR_STOP=1 -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" \
  || { echo "error: schema reset failed — restore as a superuser role" >&2; exit 3; }

echo "[restore] restoring PostgreSQL from $DUMP …"
pg_restore --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" \
  --dbname="$PGDB" --no-owner --verbose --exit-on-error "$DUMP"

if [ -n "${OT_RESTORE_MINIO_SRC:-}" ]; then
  echo "[restore] mirroring MinIO from $OT_RESTORE_MINIO_SRC …"
  export MC_HOST_opentrading="http://${OT_MINIO_ACCESS_KEY:-}:${OT_MINIO_SECRET_KEY:-}@${OT_MINIO_HOST:-127.0.0.1:9000}"
  mc --insecure mirror --overwrite "$OT_RESTORE_MINIO_SRC" opentrading
fi

echo "[restore] applying migrations …"
uv run alembic upgrade head

echo "[restore] complete. Verify with: uv run python scripts/infra_health.py"
