# Runbook — Local Development

How to start, verify and reset the OpenTrading local environment. Everything on
this page runs from the repository root with `make` and targets the **dev**
Compose stack in `infra/compose/docker-compose.yml`.

> On Windows with a real MT4 terminal involved, read
> `docs/runbooks/local-development-windows.md` instead — it covers the
> WSL2 + native-MT4-terminal topology and only points back here for the parts
> that are identical.

## Prerequisites

| Tool | Version | Check |
|---|---|---|
| Docker (with Compose v2 plugin) | ≥ 2.24 (`!reset` support) | `docker compose version` |
| uv | ≥ 0.5 | `uv --version` |
| Python | 3.12 (managed by uv) | `uv run python --version` |

## First-time setup

```bash
uv sync --all-groups          # Python toolchain + dependencies (once)
make up                      # one command: full dev environment
```

`make up` does three things, in order:

1. `docker compose up -d --build --wait` — starts every service and blocks
   until **all health checks are green**.
2. Creates the MinIO buckets (`raw`, `bronze`, `silver`, `gold`,
   `mlflow-artifacts`, `langfuse`, `posttrade-artifacts`).
3. `alembic upgrade head` — applies database migrations (platform tables).

On first run, Docker pulls the pinned images and builds the MLflow image, so it
can take a few minutes. If `.env` does not exist, it is created from
`.env.example` (dev-only placeholders, safe to commit; never commit a real
`.env`).

## Daily commands

| Command | What it does |
|---|---|
| `make up` | Start (or update) the full environment, buckets, migrations |
| `make down` | Stop containers (volumes survive) |
| `make ps` | Container status |
| `make logs` | Follow logs of all services (`make logs SERVICE=postgres` for one) |
| `make health` | Probe every service and print a pass/fail table |
| `make test` | Full pytest suite (unit + integration; integration skips when the stack is down) |
| `make test-unit` / `make test-integration` | Scoped suites (`test-integration` **fails** when the stack is down) |
| `make migrate` / `make migrate-down` | Alembic `upgrade head` / `downgrade -1` |
| `make init-buckets` | Re-run the MinIO bucket bootstrap |
| `make reset-dev` | ⚠️ **Destroys all volumes**, then rebuilds (asks for confirmation) |
| `make up-prod` | Production profile (requires `.env.prod`, see infrastructure runbook) |

## Endpoints (dev)

All host ports bind to `127.0.0.1` only — nothing is reachable from outside the
machine.

| Service | URL | Credentials (dev) |
|---|---|---|
| PostgreSQL (TimescaleDB) | `postgresql://127.0.0.1:5432/opentrading` | `opentrading` / `opentrading-dev` |
| Redis | `redis://127.0.0.1:6379` | password `opentrading-dev` |
| MinIO S3 API | `http://127.0.0.1:9000` | `opentrading` / `opentrading-dev` |
| MinIO Console | `http://127.0.0.1:9001` | same as S3 |
| FalkorDB | `redis://127.0.0.1:6380` | none (dev) |
| ClickHouse HTTP | `http://127.0.0.1:8123` | `clickhouse` / `clickhouse-dev` |
| Langfuse | `http://127.0.0.1:3000` | `admin@opentrading.local` / `opentrading-dev` |
| MLflow | `http://127.0.0.1:5000` | none |
| Prometheus | `http://127.0.0.1:9090` | none |
| Grafana | `http://127.0.0.1:3001` | `admin` / `admin-dev` |

All host ports are overridable via `OT_*_HOST_PORT` in `.env` (e.g.
`OT_POSTGRES_HOST_PORT=5433`). If you change a database port, update the
matching `OT_POSTGRES_DSN` / `OT_REDIS_URL` / `OT_FALKORDB_URL` setting too.

## Running the API against the stack

The API runs on the host (not in Compose yet):

```bash
cp .env.example .env   # if missing — dev defaults already point at the stack
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

- `GET http://127.0.0.1:8000/healthz` — liveness (always 200 while the process
  is up).
- `GET http://127.0.0.1:8000/readyz` — readiness; probes PostgreSQL, Redis,
  MinIO and FalkorDB. Returns **200** when all are reachable, **503** with a
  per-dependency breakdown otherwise.
- `GET http://127.0.0.1:8000/api/v1/contracts` — canonical contract catalog.

### Market data API (Phase 1)

- `GET /api/v1/market-data/instruments` — normalized instrument registry.
- `GET /api/v1/market-data/bars?instrument_id=&timeframe=&as_of=&dataset_version=`
  — point-in-time bars from a sealed gold dataset. `as_of` (timezone-aware ISO)
  and `dataset_version` are **required**; no bar with `available_time > as_of`
  is ever returned (INV-3).
- `GET /api/v1/market-data/snapshots/{instrument_id}?timeframe=&as_of=&dataset_version=`
  — point-in-time `MarketSnapshot` plus its deterministic `snapshot_hash`.

Error codes: missing dataset → 404, dataset not sealed → 409, naive timestamps
or missing required params → 422. See
`docs/architecture/PHASE1_DATA_PLATFORM.md` for the pipeline and DoD.

## Verifying the Definition of Done

```bash
make up         # 1. one command, everything healthy
make health     # 2. health checks green (table shows OK for every service)
docker compose --project-name opentrading-dev -f infra/compose/docker-compose.yml ps
                # 3. volumes listed in the compose file (persistent storage)
git check-ignore .env   # 4. secrets never committed (.env is ignored)
make test-integration   # 5. automated integration smoke tests pass
```

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `make up` times out | First pull is slow; re-run — it is idempotent. |
| Langfuse web unhealthy for a long time | Check `make logs SERVICE=langfuse-worker`; the worker applies its own DB/ClickHouse migrations on first boot. |
| Port conflict on 5432/6379/… | A local service already uses it. Stop it, or edit the port map in `docker-compose.yml` (and `.env` `OT_*` settings). |
| `/readyz` reports `unavailable` | `make health` to see which service failed, then `make logs SERVICE=<name>`. |
| Alembic error about missing extension | Run `make migrate` after the stack is healthy; `CREATE EXTENSION` needs the superuser role (`POSTGRES_USER`). |
| Stale data after schema changes | `make reset-dev` (destroys volumes) or `make migrate-down && make migrate`. |
