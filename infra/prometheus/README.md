# infra/prometheus — Prometheus (ops/trading observability, Phase 1)

- Image: `prom/prometheus:v3.14.0` (pinned); TSDB in volume `prometheus-data`.
- `prometheus.yml` scrapes postgres-exporter, redis-exporter, MinIO cluster
  metrics, MLflow, and the core API `/metrics` endpoint. The local core API is
  reached through Docker's `host-gateway`. Alert rules live in `rules/` and
  link to `docs/runbooks/observability-alerts.md`. UI on 127.0.0.1:9090.
- `/metrics` contains financial operational state (PnL, exposure, risk). It must
  remain reachable only from the private monitoring network; never publish it
  through the public API ingress. Production Compose publishes no ports.
