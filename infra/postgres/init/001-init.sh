#!/bin/sh
# OpenTrading PostgreSQL bootstrap (runs once, on first volume init).
#
# - Enables the TimescaleDB extension in the platform database.
# - Creates the dedicated databases used by sidecar services (MLflow, Langfuse).
#   Business-logic tables are NOT created here: they are owned by Alembic
#   migrations (see migrations/versions/).
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-'EOSQL'
    CREATE EXTENSION IF NOT EXISTS timescaledb;
EOSQL

for db in mlflow langfuse; do
    exists=$(psql -tAc "SELECT 1 FROM pg_database WHERE datname = '$db'" \
        --username "$POSTGRES_USER" --dbname "$POSTGRES_DB")
    if [ "$exists" != "1" ]; then
        psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
            -c "CREATE DATABASE \"$db\""
        echo "created database: $db"
    fi
done
