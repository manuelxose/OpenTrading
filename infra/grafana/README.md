# infra/grafana — Grafana (ops/trading dashboards, Phase 1)

- Image: `grafana/grafana:13.0.7` (pinned); state in volume `grafana-data`.
- Provisioned: Prometheus datasource plus System, Trading, Risk, Execution and
  Agents dashboards (alongside the infrastructure overview).
- UI on 127.0.0.1:3001 (Langfuse owns 3000). Admin credentials via
  `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD`.
