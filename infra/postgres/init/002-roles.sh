#!/bin/sh
# OpenTrading PostgreSQL least-privilege roles (ADR-0025, runs after 001-init.sh).
#
# Roles:
#   ot_migrator  — DDL only: owns schema public, runs Alembic migrations.
#   ot_app       — DML only: SELECT/INSERT/UPDATE/DELETE on business tables.
#   ot_readonly  — SELECT only: Grafana datasources and exporters (pg_monitor).
#   langfuse     — owns ONLY the langfuse database.
#   mlflow       — owns ONLY the mlflow database.
#
# Passwords come from environment with dev placeholders as fallback; production
# requires real values via docker-compose.prod.yml `${VAR:?message}`. Only hex
# values are supported (quotes in passwords would break the SQL below).
set -e

MIGRATOR_PASSWORD="${POSTGRES_MIGRATOR_PASSWORD:-opentrading-dev}"
APP_PASSWORD="${POSTGRES_APP_PASSWORD:-opentrading-dev}"
READONLY_PASSWORD="${POSTGRES_READONLY_PASSWORD:-opentrading-dev}"
LANGFUSE_DB_PASSWORD="${LANGFUSE_DB_PASSWORD:-opentrading-dev}"
MLFLOW_DB_PASSWORD="${MLFLOW_DB_PASSWORD:-opentrading-dev}"

for pw in "$MIGRATOR_PASSWORD" "$APP_PASSWORD" "$READONLY_PASSWORD" \
          "$LANGFUSE_DB_PASSWORD" "$MLFLOW_DB_PASSWORD"; do
    case "$pw" in
        *"'"*|*'\\'*) echo "error: role passwords must be hex-only (no quotes/backslashes)" >&2; exit 1 ;;
    esac
done

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
-- ── Roles (idempotent) ─────────────────────────────────────────────────────
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ot_migrator') THEN
        CREATE ROLE ot_migrator LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ot_app') THEN
        CREATE ROLE ot_app LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ot_readonly') THEN
        CREATE ROLE ot_readonly LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'langfuse') THEN
        CREATE ROLE langfuse LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mlflow') THEN
        CREATE ROLE mlflow LOGIN;
    END IF;
END
\$\$;

ALTER ROLE ot_migrator WITH LOGIN PASSWORD '${MIGRATOR_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE;
ALTER ROLE ot_app WITH LOGIN PASSWORD '${APP_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE;
ALTER ROLE ot_readonly WITH LOGIN PASSWORD '${READONLY_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE;
ALTER ROLE langfuse WITH LOGIN PASSWORD '${LANGFUSE_DB_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE;
ALTER ROLE mlflow WITH LOGIN PASSWORD '${MLFLOW_DB_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE;

-- Read-only monitoring (pg_stat_* views) for exporters / Grafana.
GRANT pg_monitor TO ot_readonly;

-- ── Platform database (opentrading) ────────────────────────────────────────
-- migrator owns the schema so Alembic-created objects are migrator-owned and
-- covered by the default privileges below.
ALTER SCHEMA public OWNER TO ot_migrator;
GRANT CREATE, USAGE ON SCHEMA public TO ot_migrator;
GRANT USAGE ON SCHEMA public TO ot_app, ot_readonly;

ALTER DEFAULT PRIVILEGES FOR ROLE ot_migrator IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ot_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ot_migrator IN SCHEMA public
    GRANT SELECT ON TABLES TO ot_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE ot_migrator IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO ot_app;

-- Existing objects (dev databases created before this hardening): bring them
-- under the same least-privilege grants.
DO \$\$
DECLARE
    r record;
BEGIN
    FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.%I TO ot_app', r.tablename);
        EXECUTE format('GRANT SELECT ON TABLE public.%I TO ot_readonly', r.tablename);
    END LOOP;
    FOR r IN SELECT sequence_name FROM information_schema.sequences WHERE sequence_schema = 'public' LOOP
        EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE public.%I TO ot_app', r.sequence_name);
    END LOOP;
END
\$\$;
EOSQL

# ── Sidecar databases: each service owns only its own database ─────────────
for spec in "langfuse:${LANGFUSE_DB_PASSWORD}" "mlflow:${MLFLOW_DB_PASSWORD}"; do
    db="${spec%%:*}"
    pw="${spec#*:}"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
        -c "ALTER DATABASE \"$db\" OWNER TO \"$db\""
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" <<EOSQL
        ALTER SCHEMA public OWNER TO "${db}";
        GRANT ALL ON SCHEMA public TO "${db}";
        ALTER ROLE "${db}" WITH LOGIN PASSWORD '${pw}';
EOSQL
done

echo "postgres roles ready: ot_migrator (DDL), ot_app (DML), ot_readonly (SELECT), langfuse, mlflow"
