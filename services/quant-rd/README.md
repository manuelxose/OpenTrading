# services/quant-rd — Quant R&D runtime (Python 3.11, Linux)

RD-Agent 0.8.0, Qlib 0.9.7, and MLflow 3.8.1 run here on Linux/Python 3.11
(INV-13: two runtimes, never merged). The runtime feeds canonical
`FactorCandidate` / `ModelCandidate` / `StrategyCandidate` / `ExperimentRun` records.

Run the official autonomous joint factor/model loop:

```bash
docker compose -f services/quant-rd/compose.yml run --rm quant-rd fin_quant
```

The container is non-root, read-only, capability-free, and attached only to an internal
research network with MLflow. It receives no production source mount, Docker socket,
broker/MT4 network, broker credentials, risk configuration, or operating-mode control.
Only `/workspace` and `/outputs` are writable. Adapter/workflow code lives in
`adapters/{rdagent,qlib}` and `services/quant_rd`; see
`docs/architecture/QUANT_RD_SPEC.md`.
