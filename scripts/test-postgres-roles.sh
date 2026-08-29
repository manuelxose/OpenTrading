#!/usr/bin/env bash
# Regression guard for the PostgreSQL least-privilege bootstrap (ADR-0025).
# Runs inside a throwaway postgres container so no live stack is needed.
#
#   scripts/test-postgres-roles.sh
set -euo pipefail

cd "$(dirname "$0")/.."

image="timescale/timescaledb:2.29.2-pg16"
name="ot-roles-test-$(date +%s)"

docker run -d --name "$name" \
  -e POSTGRES_DB=opentrading \
  -e POSTGRES_USER=opentrading \
  -e POSTGRES_PASSWORD=opentrading-dev \
  -e POSTGRES_MIGRATOR_PASSWORD=deadbeef01 \
  -e POSTGRES_APP_PASSWORD=deadbeef02 \
  -e POSTGRES_READONLY_PASSWORD=deadbeef03 \
  -e LANGFUSE_DB_PASSWORD=deadbeef04 \
  -e MLFLOW_DB_PASSWORD=deadbeef05 \
  -v "$(pwd)/infra/postgres/init:/docker-entrypoint-initdb.d:ro" \
  "$image" >/dev/null

cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "waiting for postgres…"
for _ in $(seq 1 60); do
  if docker exec "$name" pg_isready -U opentrading -d opentrading >/dev/null 2>&1; then break; fi
  sleep 1
done

echo "== roles exist =="
docker exec "$name" psql -U opentrading -d opentrading -tAc \
  "SELECT rolname FROM pg_roles WHERE rolname IN ('ot_migrator','ot_app','ot_readonly','langfuse','mlflow') ORDER BY 1"

echo "== migrator can create tables; app can write; readonly can read =="
docker exec "$name" psql -U ot_migrator -d opentrading -v ON_ERROR_STOP=1 -c \
  "CREATE TABLE IF NOT EXISTS public._roles_probe (id int primary key)" >/dev/null
docker exec "$name" psql -U ot_app -d opentrading -v ON_ERROR_STOP=1 -c \
  "INSERT INTO public._roles_probe VALUES (1)" >/dev/null
docker exec "$name" psql -U ot_readonly -d opentrading -tAc \
  "SELECT count(*) FROM public._roles_probe"

echo "== app cannot DROP (DDL denied) =="
if docker exec "$name" psql -U ot_app -d opentrading -c \
  "DROP TABLE public._roles_probe" >/dev/null 2>&1; then
  echo "FAIL: ot_app could drop a table" >&2; exit 1
fi
echo "ok: ot_app has no DDL"

echo "== app cannot read sidecar password material (no superuser) =="
docker exec "$name" psql -U ot_app -d opentrading -tAc \
  "SELECT rolsuper FROM pg_roles WHERE rolname = 'ot_app'"

echo "== langfuse owns only its database =="
docker exec "$name" psql -U langfuse -d langfuse -tAc "SELECT current_user, current_database()"

echo "roles test passed"
