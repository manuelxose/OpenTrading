# Quant R&D Runtime Specification

## Objective

Run autonomous factor and model research on Linux/Python 3.11 with RD-Agent, Qlib,
and MLflow while giving the research runtime zero authority over live capital.

## Capability map

| Module | Responsibility | Depends on |
|---|---|---|
| `research-contracts` | Canonical candidate and experiment lineage | core schemas |
| `upstream-adapters` | Translate RD-Agent/Qlib/MLflow data at the boundary | research-contracts |
| `research-workflows` | Hypothesis, implementation, testing, evaluation | upstream-adapters |
| `isolated-runtime` | Python 3.11 container and filesystem/network policy | research-workflows |

Build order: contracts -> adapters -> workflows -> isolated runtime.

## Stack and exact pins

- Linux / CPython 3.11
- Microsoft RD-Agent 0.8.0 (`274e274d5dbb72cc2ea139d1a7c93d73ce9b1198`)
- Microsoft Qlib 0.9.7 (`da920b7f954f48ab1bb64117c976710de198373e`)
- MLflow 3.8.1 (`4cc9d5bd7cd1962f7f34017e8d8f133f89ad8d69`)

The MLflow commit is recorded from its immutable upstream tag; container and Python
package versions are both pinned to 3.8.1.

## Commands

```bash
docker compose -f services/quant-rd/compose.yml build
docker compose -f services/quant-rd/compose.yml run --rm quant-rd
uv run pytest tests/unit/quant_rd
uv run ruff check core/schemas/research_factory.py adapters/qlib adapters/rdagent services/quant-rd tests/unit/quant_rd
uv run mypy core adapters/qlib adapters/rdagent
```

## Boundaries

- Always: use point-in-time datasets; store code SHA, dataset/config hashes, metrics,
  artifacts, dependency pins, seeds, and LLM metadata; record failed experiments.
- Ask first: expose a new service endpoint or change a canonical schema incompatibly.
- Never: import or mutate risk/execution/MT4 code; hold broker credentials; change an
  operating mode; create a live state; promote/deploy a candidate to production.

Generated code is confined to `/workspace`; canonical JSON records are append-only in
`/outputs`. The runtime has no production source mount, Docker socket, broker network,
or secret-store access. Its only optional network peer is MLflow.

## Success criteria

All seven requested workflow stages produce canonical `FactorCandidate`,
`ModelCandidate`, `StrategyCandidate`, and `ExperimentRun` records. Boundary tests prove
forbidden imports/actions are unavailable, and deterministic tests reproduce hashes and
metrics from the same inputs.
