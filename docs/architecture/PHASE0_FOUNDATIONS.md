# Phase 0 — Foundations: Implementation Record

- **Date:** 2026-08-26
- **Scope:** Milestone 1 / Phase 0 from `IMPLEMENTATION_ORDER.md` — monorepo,
  canonical domain contracts, virtual clock, event envelope, configuration, audit,
  CI, Docker Compose skeleton. **No trading intelligence implemented.**
- **Canonical source:** `docs/architecture.md` v1.0 §5–§32, frozen by
  `.ai/rules/architecture-invariants.md` and the 16 ADRs.

## 1. Definition of Done — evidence

| Criterion | Status | Evidence |
|---|---|---|
| Domain layer imports no external trading framework | ✅ | `core/` imports only stdlib + pydantic. Enforced by `tests/unit/domain/test_import_guard.py` (AST scan of every `core/**/*.py` for `nautilus_trader`, `qlib`, `graphiti`, `tradingagents`, `MetaTrader5`, `zmq`, …) |
| Core can be tested independently | ✅ | `uv run pytest tests/unit` — no external services required |
| Virtual clock exists | ✅ | `core/clock`: `Clock` protocol, `SystemClock`, `VirtualClock` (explicit advance/set, monotonic, UTC) |
| Canonical contracts exist | ✅ | `core/schemas` — 20 domain contracts + `DomainEvent` envelope, cataloged in `CANONICAL_CONTRACTS` |
| CI passes | ✅ | `.github/workflows/ci.yml` (Python 3.12, `uv sync --locked`, ruff check + format check, mypy strict, pytest). Local run 2026-08-26: **202 passed**, ruff clean, mypy clean |
| Architecture documentation reflects the implementation | ✅ | This document + `CURRENT_STATE.md` addendum + `.ai/context/repo-map.md` |

## 2. Module map (architecture §27 layout)

| Module | Phase 0 content |
|---|---|
| `core/domain/` | `enums.py` (operating modes, order/strategy lifecycles, sides, types, reason codes, memory layers…), `state_machines.py` (explicit transition DAGs, `assert_valid_*`) |
| `core/schemas/` | 20 canonical contracts + envelope; `base.py` (provenance, UTC discipline, deterministic JSON); registry `CANONICAL_CONTRACTS` |
| `core/events/` | `registry.py` (event name → payload contract), `upgrades.py` (payload version migration chains), `envelope.py` (build/serialize/deserialize) |
| `core/config/` | pydantic-settings `Settings` (`OT_` prefix, `.env.example`) |
| `core/clock/` | `SystemClock`, `VirtualClock` |
| `core/audit/` | `AuditEntry`, `AuditSink` protocol, `InMemoryAuditSink`, `AuditLogger` |
| `apps/api/` | FastAPI: `GET /healthz`, `GET /api/v1/contracts` (no trading endpoints) |
| `apps/worker/`, `apps/command-center/` | Structure + README only (worker: Phase 1+; Command Center: TypeScript, Phase 5+) |
| `engines/*` (5) | Importable packages, docstrings only — implemented in Phases 5/7/10 |
| `adapters/*` (7) | Importable packages, docstrings only — implemented in Phases 1–9 |
| `services/` | `core-runtime` (Py 3.12 — this repo), `quant-rd` (Py 3.11 — Phase 9) |
| `research/`, `infra/`, `mt4/`, `data/`, `prompts/`, `vault-trading/`, `tests/*` | §27 layout; `infra/compose/docker-compose.yml` boots the Phase 1 data platform (TimescaleDB, Redis, MinIO — pinned images) |

## 3. Canonical contracts (`core/schemas`)

All contracts share the `DomainObject` base:

- `schema_version` — pinned to the class constant `SCHEMA_VERSION` ("1.0.0"); a
  mismatched value fails validation.
- `trace_id: UUID | None` — end-to-end correlation (architecture §31).
- `produced_at` — **timezone-aware UTC required**; naive datetimes are rejected.
  No component calls `datetime.now()` for domain decisions — time comes from a
  `Clock`.
- `provenance` — producer, produced_at, code_version, source_ids, notes.
- Immutable (`frozen=True`), closed to extra fields (`extra="forbid"`).
- Deterministic serialization: `to_json()` / `from_json()` (Pydantic v2 JSON mode,
  field order fixed by class definition; Decimals/UUIDs/datetimes canonical forms).

The 20 contracts: `Instrument`, `MarketSnapshot`, `ResearchRequest`, `ResearchPacket`,
`QuantSignal`, `LLMSignal`, `FusedSignal`, `TradeProposal`, `RiskDecision`,
`OrderIntent`, `ExecutionReport`, `PositionSnapshot`, `TradeOutcome`,
`PostTradeReview`, `MemoryEpisode`, `FactorCandidate`, `ModelCandidate`,
`StrategyCandidate`, `ExperimentRun`, `PromotionDecision` — plus the `DomainEvent`
envelope. Cross-contract rules encoded as validators (INV-4 shapes for
`RiskDecision`; INV-8 transition checks in `PromotionDecision`; INV-3
`source_timestamp <= as_of` in `MarketSnapshot`; INV-16 weight checks in
`FusedSignal`; `OrderIntent` only in order-capable modes; …).

## 4. Enums and state machines (`core/domain`)

- `OperatingMode`: exactly `RESEARCH | BACKTEST | PAPER | LIVE_GATED | LIVE_AUTO`
  (INV-8), with `allows_order_submission` / `is_live_mode` helpers.
- `OrderState`: the 13 canonical order states (INV-6).
- `StrategyState`: the 10 canonical strategy states (INV-8; no RD-Agent → LIVE edge).
- `RiskReasonCode`: canonical rejection codes from architecture §7.
- `state_machines.py` is the single authority for valid transitions; engines must
  call `assert_valid_*_transition` rather than hard-coding adjacency.

## 5. Clock semantics (`core/clock`)

- `SystemClock.now()` is the only sanctioned read of the wall clock.
- `VirtualClock`: explicit time. `advance(delta > 0)` and `set(moment)`; moving
  backwards is refused. Repeated `now()` calls return the identical instant, so two
  clocks driven by the same call sequence observe an identical timeline
  (determinism tested). All times are timezone-aware UTC.

## 6. Event bus contract (`core/events`)

- Standard envelope (`DomainEvent`, architecture §14): `schema_version`, `event_id`,
  `trace_id`, `event_time`, `ingested_at`, `producer`, `event_name`, `payload`,
  `provenance`. `event_name` was added to the envelope as the routing key and is
  documented here as the single deliberate addition.
- `CANONICAL_EVENT_PAYLOAD_SCHEMAS` maps every §14 event name to its payload
  contract (`order.submitted … order.rejected` carry `ExecutionReport`).
  `system.safe_mode.*` gets a payload with the Risk Engine (Phase 5).
- Event versioning: `upgrades.py` registers linear payload-migration chains per
  event name. Phase 0 ships the real example
  `market.snapshot.created: 0.9.0 → 0.10.0 → 1.0.0`; `deserialize_event` upgrades
  old payloads before validating against the current contract.
- Redis Streams transport lands in Phase 1; the layer above is transport-agnostic.

## 7. Configuration and audit

- `Settings` reads `OT_*` env vars (`.env.example` committed; `.env` git-ignored,
  INV-9). Invalid `OT_OPERATING_MODE` fails at startup.
- `core/audit` produces immutable, clock-stamped `AuditEntry` records through
  pluggable `AuditSink`s (PostgreSQL sink in Phase 1).

## 8. Schema evolution procedure

When a contract must change:

1. Bump the class `SCHEMA_VERSION` constant **and** its `schema_version` field
   default (e.g. to "1.1.0") — the base validator pins them together.
2. Register a `PayloadUpgrader` chain for every affected event name in
   `core/events/upgrades.py` (old version → new version).
3. Update fixtures/tests; keep the old-version upgrade tests green.
4. Note the change in the ADR/changelog; domain values themselves only change via
   ADR (INV-12).

## 9. Tests (202 passed, 2026-08-26)

| Area | Tests |
|---|---|
| Schema validation | construction of all 21 contracts; unknown fields; version tampering; naive timestamps; per-contract invariants (risk shapes, order modes, PIT, fusion weights, promotion transitions…) |
| Serialization | lossless round-trip and byte-determinism for every contract; UTC ISO forms |
| Event versioning | upgrade chain, current passthrough, missing version, missing path, legacy envelope deserialization |
| Virtual clock | determinism across instances, monotonic advance/set, backward rejection, UTC normalization |
| State machines | canonical order + strategy chains, invalid transitions raise, terminal states |
| Import guard | `core/` imports no external trading framework (AST scan) |
| Config | defaults, `OT_` prefix, invalid mode rejected, cached singleton |
| Audit | entries stamped by injected clock, trace/actor/metadata propagation |
| API | `/healthz`, contract catalog |

## 10. Explicitly NOT implemented (phase gates)

Phases 1–12: data platform, TradingAgents, Graphiti, Nautilus, Risk Engine, MT4
bridge (no `.mq4` code), paper/LIVE pipelines, Quant Factory, promotion. The
directories exist with phase documentation only — no stub code, no TODO placeholders
in live paths (`.ai/rules/definition-of-done.md` rule 9).

## 11. Local verification commands

```bash
make setup        # uv sync --all-groups
make lint         # ruff check .
make typecheck    # mypy core apps engines adapters
make test         # pytest (202 passed)
make ci           # all gates
uv lock --check   # lock consistency (CI uses uv sync --locked)
```
