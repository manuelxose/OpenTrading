# infra/ — Infrastructure (architecture §27, INV-10)

Local infrastructure for the OpenTrading platform (Phase 1 Data Platform):

| Directory | What |
|---|---|
| `compose/` | `docker-compose.yml` (dev) + `docker-compose.prod.yml` (prod overrides) |
| `postgres/` | PostgreSQL + TimescaleDB bootstrap (`init/001-init.sh`) |
| `redis/` | Redis (cache, locks, streams) |
| `minio/` | MinIO + bucket bootstrap (`raw/bronze/silver/gold`, `mlflow-artifacts`, `langfuse`) |
| `falkordb/` | FalkorDB graph store (Graphiti lands in Phase 3) |
| `mlflow/` | MLflow image (tracking server + Postgres/S3 drivers) |
| `langfuse/` | Langfuse v4 (web + worker, ClickHouse analytics) |
| `prometheus/` | Prometheus scrape config |
| `grafana/` | Grafana provisioning (datasource + dashboards) |

Run it:

```bash
make up        # start everything (health-checked), buckets, migrations
make health    # probe every service
make down      # stop (volumes survive)
```

Operational details: `docs/runbooks/local-development.md` and
`docs/runbooks/infrastructure.md`.
