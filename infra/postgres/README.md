# infra/postgres — PostgreSQL + TimescaleDB (transactional source of truth, INV-10)

- Image: `timescale/timescaledb:2.29.2-pg16` (pinned, external-lock.yaml).
- `init/001-init.sh` runs once on first volume init: enables the TimescaleDB
  extension and creates the `mlflow` / `langfuse` sidecar databases.
- Business tables are owned by Alembic migrations (repo-root `migrations/`),
  never by init scripts. See docs/runbooks/infrastructure.md.
