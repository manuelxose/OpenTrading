# Graph Report - OpenTrading  (2026-08-29)

## Corpus Check
- 539 files · ~230,259 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 6599 nodes · 18285 edges · 352 communities (276 shown, 76 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 1674 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `01462f84`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- WireMessage
- Clock
- DomainEvent
- InMemoryStreamBus
- TradeLifecycle
- make_market_snapshot
- OrderType
- TradeProposal
- mapping.py
- test_hashing.py
- tradingagents/client.py
- bootstrap.py
- enums.py
- FusionInputs
- evaluate
- Memory
- mapper.py
- test_export.py
- OrderRecord
- market_data/pipeline.py
- Stack
- normalization.py
- PaperLedger
- make_record
- Timeframe
- graphiti/memory.py
- OrderState
- ExperimentRun
- main.py
- factories.py
- StrategyCandidate
- assert_valid_trade_transition
- devDependencies
- make_order_intent
- schemas/__init__.py
- HumanApprovalGate
- quality.py
- stages/posttrade.py
- test_memory.py
- worker_helpers.py
- test_paper_ledger.py
- MinioArtifactStore
- test_client.py
- NautilusPaperExecutor
- NautilusRouterStrategy
- StrategyState
- LiveAutoRegistry
- MemoryRecord
- test_command_center_api.py
- calibration.py
- risk/engine.py
- domain/__init__.py
- EmergencyControlState
- make_bar
- App.tsx
- _sizing_probe.py
- TestBlockingInvariants
- MarketSnapshot
- ScriptedRedis
- evaluate_cases
- CalibrationStore
- make_risk_policy
- Target Architecture — Autonomous Quantitative Trading & Research Platform
- Settings
- test_workflows.py
- architecture.md
- make_memory_episode
- risk_helpers.py
- 5. Scenario playbooks
- OperatingMode
- worker/ledger.py
- ConnectionMonitor
- PositionSnapshot
- DomainObject
- 32. Roadmap definitivo
- Mt4ExecutionClient
- Instrument
- TokenUsageCollector
- ._require_calibrated_version
- redact
- backtest/conftest.py
- nautilus/engine.py
- compilerOptions
- test_execution_boundary.py
- compute_trade_metrics
- strategy.py
- PortfolioState
- Agent details
- 3. Classification against the requested axes
- test_resize.py
- test_live_infra_restart.py
- test_registry.py
- GraphitiConfig
- 5. Controls
- RiskPolicy
- Architecture Invariants
- VirtualClock
- LangfuseTracer
- synthetic_dataset
- test_posttrade_metrics.py
- Operations Manual — OpenTrading
- test_live_auto_api.py
- Known Limitations — OpenTrading
- QlibAdapter
- _build_platform_with_poison
- StageWorker
- OrderRejectionSim
- NativeRDAgentQlibBackend
- SignalDirection
- Any
- test_paper_executor.py
- Phase 0 — Foundations: Implementation Record
- Runbook — Infrastructure
- window_blind_store
- producers.py
- Domain Glossary (OpenTrading)
- Detail
- Product
- NautilusBacktestRunner
- Self
- SequenceTracker
- ensure_utc
- Task Routing Workflow
- Observability alert runbook
- mt4/protocol — MT4 execution protocol v1.0 (ADR-0020, §34.18)
- Agent: AI Trading Systems
- Agent: Backend Platform
- Agent: Command Center / Frontend
- Agent: Execution / MT4
- Agent: Infrastructure & SRE
- Agent: Market Data
- Agent: Principal Architect
- Agent: Quant Research
- Agent: Risk
- Agent: Security
- Agent: Trading & Backtest
- Agent: Verification
- Production Readiness — OpenTrading
- ADR/README.md
- 26. Command Center
- 1. What was built
- Phase 5 — Deterministic Risk & Policy Engine (implementation record)
- Runbook — Local Development
- FakeGraph
- 19. Validation Factory
- Bar
- .ai — Canonical AI Engineering Layer (OpenTrading)
- LLM Agent Evaluation
- ADR Management
- Architecture Review
- Domain Boundary Review
- Event Contract Design
- State Machine Review
- API Contract Review
- Dead Code Detection
- Debugging
- Performance Profiling
- Refactoring
- Test Generation
- Docker Review
- Incident Analysis
- Observability Review
- Production Readiness
- Backtest Validation
- Experiment Reproducibility
- Factor Evaluation
- Model Evaluation
- Point-in-Time Validation
- Walk-Forward Validation
- Change Impact Analysis
- Dependency Tracing
- Graphify Context
- Repository Navigation
- Dependency Security
- Privilege Boundary Review
- Secret Scan
- Threat Model
- Execution Safety
- Order Lifecycle Review
- Portfolio Risk Review
- Reconciliation Review
- Trading Cost Validation
- compilerOptions
- Runbook — Secrets management (SOPS + age)
- _validate_lineage
- brier_error
- allows_order_submission
- Quant R&D Runtime Specification
- Postmortem — EURUSD LONG
- env.py
- test_serialization.py
- adapters/graphiti — temporal semantic memory (Phase 3)
- adapters/tradingagents — TradingAgents behind a strict boundary (ADR-0004)
- .store
- TestResizeShape
- ADR-0001: Python as the quantitative backend language
- ADR-0002: TypeScript for the Command Center
- ADR-0003: MQL4 exists only in the MT4 execution bridge
- ADR-0004: TradingAgents as the LLM research committee
- ADR-0005: Qlib as the quantitative research platform
- ADR-0006: RD-Agent as the autonomous R&D factory (offline)
- ADR-0007: NautilusTrader as the event-driven backtest/paper engine
- ADR-0008: Graphiti as the temporal trading memory
- ADR-0009: Graphify as development context tooling only
- ADR-0010: PostgreSQL as the transactional source of truth
- ADR-0011: MinIO + Parquet for large historical datasets
- ADR-0012: Redis Streams as the initial event bus
- ADR-0013: Langfuse for AI observability
- ADR-0014: Prometheus + Grafana for operational observability
- ADR-0015: Deterministic Risk Engine (no LLM authority over capital)
- ADR-0016: MT4 as execution venue only
- ADR-0017: Point-in-time market data semantics (medallion pipeline)
- ADR-0018: Risk Engine — RESIZE decision and exposure denomination
- ADR-0019: Signal Fusion Engine — calibrated weights, signed components, regime-specific models
- ADR-0020: MT4 execution protocol v1.0 (versioned ZeroMQ, emulator-first)
- Context Strategy — OpenTrading
- 30. Testing
- Gap Analysis — Current vs Target Architecture
- Implementation Order — OpenTrading
- Phase 7 — Autonomous PAPER pipeline
- Runbook — Autonomous PAPER pipeline
- engines/signal_fusion — Signal Fusion Engine (Phase 7, INV-16)
- OpenTrading — GitHub Copilot instructions
- test_reject.py
- ._check_low_high
- adapters/mt4 — MT4 execution protocol (Phase 6, ADR-0020)
- adapters/nautilus — NautilusTrader event-driven backtest engine (ADR-0007)
- Research context — $instrument_id @ $as_of
- AGENTS.md — OpenTrading (Codex & generic agent adapters)
- Repository Map (OpenTrading)
- Definition of Done
- TestApprovedRiskInvariant
- Routing Rules — OpenTrading
- 10. Kill switch y Dead Man Switch
- Inspiración FinMem
- 13. Arquitectura de datos
- 6. Los cinco modos operativos
- 8. MetaTrader 4: solamente capa de ejecución
- Phase 7 — Execution state: broker reconciliation & Safe Mode (implemented)
- engines/risk — Deterministic Risk & Policy Engine (Phase 5)
- OpenTrading — Autonomous Quantitative Trading & Research Platform
- SafeModeViolation
- RDAgentBackend
- test_import_guard.py
- Trade — 2c7c2d4f-fec5-5bdb-a428-4ebde0e0f237
- Cross-Review Rules
- apps/worker — Autonomous PAPER pipeline (Phase 7, ADR-0022)
- CLAUDE.md — OpenTrading (Claude Code adapter)
- 0009_audit_trail_immutability.py
- ._check_envelope
- ADR-0022: Autonomous PAPER pipeline — Redis Streams stages, idempotent run ledger, recovery semantics
- ADR-0023: Post-trade analysis & learning engine — deterministic postmortems with four sinks
- ADR-0024: Emergency control system — kill switches and dead man switch
- 7. Risk Engine: componente más importante
- Phase 7 — Post-trade analysis & learning engine (ADR-0023)
- engines/posttrade — Post-trade analysis & learning engine (Phase 7, ADR-0023)
- mt4/ — MetaTrader 4 execution-only layer (Phase 6, INV-5)
- WireGuard — private transport for remote Windows MT4 deployments
- Context Usage Rules
- ADR Template
- backup.sh
- Routing Validation — OpenTrading
- Strategy Validation Factory
- Agent Output Standard
- Verification Review Report
- tsconfig.json
- restore.sh
- ADR-0026 — LIVE_AUTO governance: automated live trading, disabled by default
- 29. Seguridad
- 4. Qlib + RD-Agent: fábrica cuantitativa autónoma
- 5. NautilusTrader: columna vertebral del trading
- adapters/__init__.py
- rating_scale.md
- tradingagents/prompts/README.md
- adr-workflow.md
- verification-workflow.md
- api/__init__.py
- api/README.md
- eslint.config.js
- command-center/README.md
- apps/__init__.py
- worker/__init__.py
- catalogs/README.md
- eval/tradingagents/README.md
- fixtures/README.md
- data/README.md
- schemas/README.md
- engines/execution/README.md
- engines/__init__.py
- portfolio/__init__.py
- portfolio/README.md
- promotion/README.md
- falkordb/README.md
- grafana/README.md
- langfuse/README.md
- minio/README.md
- mlflow/README.md
- 001-init.sh
- postgres/README.md
- prometheus/README.md
- infra/README.md
- redis/README.md
- Experts/README.md
- Include/README.md
- tests/README.md
- analysts/README.md
- evaluators/README.md
- prompts/README.md
- researchers/README.md
- trader/README.md
- baselines/README.md
- factors/README.md
- models/README.md
- notebooks/README.md
- research/README.md
- strategies/README.md
- core-runtime/README.md
- services/__init__.py
- quant-rd/README.md
- backtest/README.md
- tests/chaos — dedicated chaos/recovery suite
- tests/execution/README.md
- integration/README.md
- leakage/README.md
- replay/README.md
- tests/risk/README.md
- security/README.md
- unit/README.md
- unit/signal_fusion/README.md
- vault-trading/README.md
- opentrading
- opentrading-quant-rd
- ADR-0025 — Security hardening milestone: trust zones, least privilege, secret lifecycle
- PortfolioExposure
- ExecutionService
- test-postgres-roles.sh
- 002-roles.sh
- entrypoint-acl.sh
- infra_health.py
- .canonical_dict

## God Nodes (most connected - your core abstractions)
1. `VirtualClock` - 172 edges
2. `Stack` - 158 edges
3. `SignalDirection` - 134 edges
4. `evaluate()` - 134 edges
5. `Clock` - 105 edges
6. `OrderType` - 99 edges
7. `DomainEvent` - 97 edges
8. `Mt4ExecutionClient` - 95 edges
9. `OrderSide` - 95 edges
10. `Timeframe` - 95 edges

## Surprising Connections (you probably didn't know these)
- `test_partial_fill_status_never_claimed_for_single_fill_orders()` --uses--> `ExecutionState`  [INFERRED]
  tests/backtest/test_costs.py → core/domain/enums.py
- `test_trade_outcomes_are_internally_consistent()` --uses--> `SignalDirection`  [INFERRED]
  tests/backtest/test_position_accounting.py → core/domain/enums.py
- `TestSearchResolution` --uses--> `GraphitiSearchError`  [INFERRED]
  tests/unit/graphiti/test_live_store.py → adapters/graphiti/errors.py
- `TestIngest` --uses--> `OntologyError`  [INFERRED]
  tests/unit/graphiti/test_memory.py → adapters/graphiti/errors.py
- `TestDefenseInDepth` --uses--> `FutureMemoryLeakageError`  [INFERRED]
  tests/unit/graphiti/test_memory.py → adapters/graphiti/errors.py

## Import Cycles
- None detected.

## Communities (352 total, 76 thin omitted)

### Community 0 - "WireMessage"
Cohesion: 0.04
Nodes (77): Poll one pushed event (non-blocking by default)., Collect all currently queued events (used by lifecycle tests)., Python MT4 emulator — the bridge's stand-in before real MetaTrader (Phase 6).…, is_retryable(), Mt4ErrorCode, Mt4ProtocolError, ProtocolErrorDetail, BaseModel (+69 more)

### Community 1 - "Clock"
Cohesion: 0.03
Nodes (94): get_mt4_settings(), Mt4Settings, BaseSettings, MT4 execution settings (OT_MT4_* environment variables). Mirrors the pattern of…, Process-wide MT4 settings singleton (matching core get_settings)., build_emergency_router(), EmergencyBody, APIRouter (+86 more)

### Community 2 - "DomainEvent"
Cohesion: 0.04
Nodes (78): new_trace_id(), UUID, Redis Streams event bus for the autonomous pipeline (INV-15, architecture §14).…, Convenience accessor for envelope correlation., trace_id_of(), Any, UUID, Trade lifecycle transition helpers (Phase 7). All lifecycle mutations flow… (+70 more)

### Community 3 - "InMemoryStreamBus"
Cohesion: 0.04
Nodes (38): BusUnavailableError, _connection_factory(), InMemoryStreamBus, PendingMessage, Any, Protocol, RuntimeError, Redis Streams bus with reconnect and recovery semantics. (+30 more)

### Community 4 - "TradeLifecycle"
Cohesion: 0.03
Nodes (59): _account_from_row(), _account_values(), _context_from_row(), InMemoryPipelineStore, _lifecycle_from_row(), _lifecycle_values(), PipelineStore, PostgresPipelineStore (+51 more)

### Community 5 - "make_market_snapshot"
Cohesion: 0.12
Nodes (41): Translate a canonical request into the upstream ``propagate`` surface., request_to_upstream_input(), default_mock_scenario(), MockTradingAgentsAdapter, The built-in fallback: a balanced, evidence-carrying HOLD decision., Scenario-driven stand-in for the upstream committee. Scenario lookup: exact…, MockScenario, Deterministic scenario played back by :class:`MockTradingAgentsAdapter`. (+33 more)

### Community 6 - "OrderType"
Cohesion: 0.04
Nodes (93): BrokerOutcome, AccountState, datetime, Decimal, model_validator, UUID, _quote(), QuoteEngine (+85 more)

### Community 7 - "TradeProposal"
Cohesion: 0.18
Nodes (21): Point-in-time strategy configuration snapshot. ``allowed_instruments=None``…, StrategyConfiguration, What the intelligence layer proposes. LLM sizing/stop values are advisory only…, TradeProposal, _broker_disconnected(), _daily_loss_reached(), _drawdown_reached(), _heartbeat_lost() (+13 more)

### Community 8 - "mapping.py"
Cohesion: 0.08
Nodes (41): Domain-side position accounting that mirrors the Nautilus venue ledger.…, _decimal(), provenance(), datetime, OrderAccepted, OrderDenied, OrderFilled, OrderRejected (+33 more)

### Community 9 - "test_hashing.py"
Cohesion: 0.11
Nodes (32): bar_checksum(), bar_row_key(), canonical_bar_bytes(), canonical_decimal(), canonical_timestamp(), dataset_hash(), _hash_stream(), partition_hash() (+24 more)

### Community 10 - "tradingagents/client.py"
Cohesion: 0.07
Nodes (21): _installed_version(), _installed_version_safely(), _load_graph_class(), _load_graph_class_safely(), datetime, UUID, Live TradingAgents adapter — the ONLY module allowed to import upstream.…, Execute the upstream committee for ``request`` and return a signal. Fails… (+13 more)

### Community 11 - "bootstrap.py"
Cohesion: 0.07
Nodes (31): Validate untrusted upstream output before it enters a workflow., RDAgentAdapter, PermissionError, assert_runtime_version(), main(), Any, Fail-closed executable composition for autonomous canonical Quant R&D., INV-13: Quant R&D runs on Python 3.11 — the two runtimes are never merged. The… (+23 more)

### Community 12 - "enums.py"
Cohesion: 0.08
Nodes (38): Catalog, MemoryCatalog, PostgresCatalog, datetime, Protocol, UUID, Market data catalog: PostgreSQL-backed (ADR-0010) or in-memory. The catalog…, Deterministic in-memory catalog (unit and leakage tests). (+30 more)

### Community 13 - "FusionInputs"
Cohesion: 0.04
Nodes (85): paper_fusion_config(), Default calibrated fusion config for the paper pipeline. Equal weights over the…, _default_fusion(), FusionInputs, Signal Fusion input contracts (INV-16, Phase 7). The fusion engine fuses up to…, All fusion inputs for one instrument at one point in time. Any input may be…, Names of the inputs that are present, in canonical engine order., FusedSignal (+77 more)

### Community 14 - "evaluate"
Cohesion: 0.05
Nodes (15): evaluate(), Evaluate a proposal against the baseline inputs with dict overrides.…, TestApproveVariants, TestBaselineApprove, For each soft limit: an adversarial proposal never bypasses the limit. Every…, approved quantity <= configured maximum (policy and instrument)., TestApprovedQuantityInvariant, TestDecisionShape (+7 more)

### Community 15 - "Memory"
Cohesion: 0.08
Nodes (35): LiveGraphitiStore, Close the underlying graph driver (idempotent)., Graphiti storage backed by FalkorDB (ADR-0008: FalkorDB first). Requires…, GraphitiIngestError, GraphitiUnavailableError, GraphitiVersionError, Upstream Graphiti (or FalkorDB) could not be reached or imported., The installed graphiti-core distribution does not match the pin (INV-14). (+27 more)

### Community 16 - "mapper.py"
Cohesion: 0.06
Nodes (60): Exception, TradingAgents adapter errors. Concrete error types so callers can distinguish…, Base class for every TradingAgents adapter error., The installed upstream version violates the pinned version/commit., The upstream run exceeded the adapter's timeout budget., A domain input could not be translated to upstream, or an upstream output could…, TradingAgentsError, TradingAgentsMappingError (+52 more)

### Community 17 - "test_export.py"
Cohesion: 0.05
Nodes (47): _canonical_id(), ensure_secret_free(), initialize_vault(), MirroringEventBus, _note_path(), ObsidianExporter, Any, Path (+39 more)

### Community 18 - "OrderRecord"
Cohesion: 0.07
Nodes (29): OrderRecord, The single authoritative persisted record for one ``order_intent_id``. Keyed by…, OrderStateApplier, datetime, Decimal, UUID, Persist the canonical crossing object (INV-2) as ORDER_INTENT., Persist SUBMITTED **before** the wire send (crash-after-submit safety). (+21 more)

### Community 19 - "market_data/pipeline.py"
Cohesion: 0.06
Nodes (36): _group_bars(), MarketDataPipeline, _merge_gold_rows(), datetime, Medallion ingestion pipeline: RAW → BRONZE → SILVER → GOLD. -…, Deterministic cross-run merge for gold: one row per bar identity. Identity:…, Deterministic raw→bronze→silver→gold pipeline (Phase 1 DoD)., Ingest one batch: raw storage, bronze normalization, silver quality. A single… (+28 more)

### Community 20 - "Stack"
Cohesion: 0.04
Nodes (120): DeadManSwitchReason, EmergencyLevel, The four emergency-control levels (INV-7, architecture §10). Semantics frozen…, Why the dead man switch engaged (INV-7, architecture §10)., ExecutionDivergenceError, RuntimeError, A venue report contradicts authoritative state in a capital-relevant way., EmergencyPolicy (+112 more)

### Community 21 - "normalization.py"
Cohesion: 0.07
Nodes (24): NormalizationError, A raw payload could not be mapped to a normalized record., BarPayloadMapper, build_bar_from_payload(), _epoch_to_utc(), normalize_timestamp(), parse_timeframe(), Any (+16 more)

### Community 22 - "PaperLedger"
Cohesion: 0.12
Nodes (13): LedgerPosition, PaperLedger, AccountState, datetime, Decimal, UUID, Canonical position snapshots with current marks (portfolio state)., Apply one FILLED/partial fill report; net the position; close on sign flip.… (+5 more)

### Community 23 - "make_record"
Cohesion: 0.06
Nodes (27): Temporal window pushed down to the store as an optimization. The authoritative…, Temporal validity interval [``valid_from``, ``valid_until``].…, Duration in seconds, or None when open-ended., SearchWindow, Validity, InMemoryStore, Deterministic in-memory backend — same window semantics as the live store.…, _tokens() (+19 more)

### Community 24 - "Timeframe"
Cohesion: 0.10
Nodes (37): Timeframe, Leakage tests: future information must be impossible to retrieve (INV-3). Phase…, DoD: (instrument X, dataset version Y, as_of T) → same hash, always., TestDeterministicDoD, TestImmutabilityLeakage, ingest_and_seal(), make_minute_raw_records(), Platform (+29 more)

### Community 25 - "graphiti/memory.py"
Cohesion: 0.07
Nodes (33): _installed_version(), Live Graphiti-over-FalkorDB store — the ONLY module allowed to import upstream.…, Distribution version of the installed upstream, or None if absent., FutureMemoryLeakageError, GraphitiError, GraphitiResolutionError, GraphitiSearchError, Exception (+25 more)

### Community 26 - "OrderState"
Cohesion: 0.05
Nodes (89): DiscrepancyCode, OrderState, PositionSide, StrEnum, Canonical order lifecycle (INV-6, architecture §8)., Broker reconciliation discrepancy codes (INV-6, architecture §9). Severity is…, ExecutionContract, ExecutionPosition (+81 more)

### Community 27 - "ExperimentRun"
Cohesion: 0.11
Nodes (26): RD-Agent translation seam for the isolated Python 3.11 service., Typed boundary around Microsoft RD-Agent (offline research only)., Hypothesis, Implementation, BaseModel, Adapter-owned values; no RD-Agent class crosses this module boundary., CandidateStatus, ExperimentRun (+18 more)

### Community 28 - "main.py"
Cohesion: 0.08
Nodes (37): check_falkordb(), check_minio(), check_postgres(), check_redis(), HealthCheckResult, CheckFunc, Dependency readiness checks backing ``GET /readyz`` (§31 observability). Each…, Run one probe with a hard timeout; never raise. (+29 more)

### Community 29 - "factories.py"
Cohesion: 0.06
Nodes (72): A Risk Decision is never a bare boolean (INV-4, architecture §7). ``RESIZE``…, Canonical decision reason codes (architecture §7 controls, ADR-0018). Used both…, RiskDecisionType, RiskReasonCode, Payload for ``system.safe_mode.entered`` / ``system.safe_mode.exited``., SafeModeEvent, EvidenceRef, Pointer to an evidence source (document, memory episode, dataset, artifact). (+64 more)

### Community 30 - "StrategyCandidate"
Cohesion: 0.13
Nodes (20): ExperimentStatus, A strategy under the INV-8 lifecycle. No RD-Agent -> LIVE edge exists., StrategyCandidate, Strategy promotion pipeline — deterministic validation gate (INV-8)., ExperimentRecorder, Any, datetime, Exception (+12 more)

### Community 32 - "devDependencies"
Cohesion: 0.04
Nodes (47): dependencies, lucide-react, react, react-dom, typescript, vite, @vitejs/plugin-react, devDependencies (+39 more)

### Community 33 - "make_order_intent"
Cohesion: 0.08
Nodes (32): instrument_to_nautilus(), order_intent_to_order(), CurrencyPair, Venue, Map the canonical domain ``Instrument`` to a Nautilus spot ``CurrencyPair``.…, Map the canonical ``OrderIntent`` to a native Nautilus order.…, LimitOrder, MarketOrder (+24 more)

### Community 34 - "schemas/__init__.py"
Cohesion: 0.08
Nodes (44): BaseContractModel, BaseModel, Common configuration shared by all contracts and sub-models., MemoryContext, Market-regime classifier output (architecture §16 regime testing).…, Memory-derived stance from the temporal memory (Graphiti, INV-3, INV-11). A…, RegimeContext, Canonical domain contracts (architecture §15) and the event envelope (§14).… (+36 more)

### Community 35 - "HumanApprovalGate"
Cohesion: 0.06
Nodes (37): DecisionBody, KillBody, BaseModel, Authenticated operator API for LIVE_GATED approval and emergency controls., _record(), ApprovalRecord, ApprovalStatus, ApprovalStore (+29 more)

### Community 36 - "quality.py"
Cohesion: 0.17
Nodes (11): DataQualityEngine, _next_bar_time(), datetime, timedelta, QualityOutcome, Silver-layer data quality: flags, duplicate handling, missing-bar detection.…, Deterministic duplicate resolution. Key: ``(instrument_id, timeframe,…, Interior gaps per (instrument, timeframe) against the bar grid. (+3 more)

### Community 37 - "stages/posttrade.py"
Cohesion: 0.05
Nodes (65): PosttradeStage, Any, datetime, UUID, Post-trade stage: closed-and-reconciled trade → full postmortem (Phase 7).…, Idempotently finish lifecycle state after canonical persistence., Certify the trade is definitively closed-and-reconciled (INV-6)., The entry-side lifecycle matched by position id (INV-6 audit path). (+57 more)

### Community 38 - "test_memory.py"
Cohesion: 0.08
Nodes (31): OntologyError, An entity type or relation is not part of the frozen trading ontology., assert_known_entities(), assert_known_relations(), EntityType, _extraction_model(), BaseModel, StrEnum (+23 more)

### Community 39 - "worker_helpers.py"
Cohesion: 0.05
Nodes (55): PaperVenueConfig, BaseModel, Venue parameters for the Nautilus paper simulator. ``slippage_*`` and…, build_default_config(), _instrument(), main(), _parser(), ArgumentParser (+47 more)

### Community 40 - "test_paper_ledger.py"
Cohesion: 0.15
Nodes (13): _CrashOnAckBus, Simulates a worker killed after processing but before the ACK landed., account_record(), build_ledger(), make_fill_report(), make_intent(), Decimal, PaperLedger tests: netting, closes, outcomes, account/portfolio views. (+5 more)

### Community 41 - "MinioArtifactStore"
Cohesion: 0.14
Nodes (7): ArtifactStore, MinioArtifactStore, Any, Protocol, Object-storage boundary for post-trade artifacts., S3-compatible artifact storage backed by MinIO (ADR-0011)., TestMinioArtifacts

### Community 42 - "test_client.py"
Cohesion: 0.10
Nodes (34): LiveTradingAgentsAdapter, Strict adapter boundary around ``TradingAgentsGraph.propagate``. Lifecycle per…, AdapterConfig, Explicit configuration for one adapter instance. Model choice is mandatory —…, fake_state(), FakeGraph, FakeResponse, Any (+26 more)

### Community 43 - "NautilusPaperExecutor"
Cohesion: 0.07
Nodes (25): Venue, Authoritative balances as tracked by the Nautilus venue (for cross-checks)., ConfigurableSlippageFillModel, NotionalCommissionFeeModel, Decimal, Realistic commission: ``rate_bps`` of trade notional per fill, floored. For FX…, Deterministic slippage by shifting the simulated order book away from best.…, The quote the most recent fill simulation used (for slippage accounting). (+17 more)

### Community 44 - "NautilusRouterStrategy"
Cohesion: 0.10
Nodes (15): NautilusRouterStrategy, datetime, Decimal, OrderAccepted, OrderDenied, OrderFilled, OrderRejected, OrderSubmitted (+7 more)

### Community 45 - "StrategyState"
Cohesion: 0.17
Nodes (23): PromotionAction, Strategy lifecycle (INV-8, architecture §16). There is no ``RD-Agent -> LIVE``…, Outcome of a promotion review (INV-8). Approval is never an LLM action., StrategyState, PromotionDecision, Strategy promotion contract: ``PromotionDecision`` (INV-8, Phase 10+).…, PaperEligibility, The only deterministic check used before requesting PAPER promotion. (+15 more)

### Community 46 - "LiveAutoRegistry"
Cohesion: 0.05
Nodes (36): LiveAutoViolation, RuntimeError, An automated order or a governance action violates LIVE_AUTO policy., Fail closed unless the capability is on AND every limit is explicit., LIVE_AUTO governance (Phase 11): deterministic, operator-controlled promotion…, _decode_strategy(), _encode_strategy(), PostgresLiveAutoStore (+28 more)

### Community 47 - "MemoryRecord"
Cohesion: 0.07
Nodes (24): UUID, Known envelopes (test/debug surface)., LayerPolicyError, A tier policy parameter is inconsistent (e.g. overlapping reach windows)., MemoryRecord, One stored memory item: the ontology content plus the temporal envelope., Persist one memory record (idempotent per ``episode_id``)., Idempotent write keyed by ``episode_id`` (replays overwrite safely). (+16 more)

### Community 48 - "test_command_center_api.py"
Cohesion: 0.06
Nodes (33): SQLAlchemy Core table definitions for the market data catalog. PostgreSQL is…, build_command_center_router(), CommandCenterDataSource, _json(), PostgresCommandCenterDataSource, Any, APIRouter, datetime (+25 more)

### Community 49 - "calibration.py"
Cohesion: 0.05
Nodes (57): calibrate(), Calibrator, DataScope, Any, datetime, Calibration: learn fusion weights and confidence maps from labeled history…, All compositions of ``units`` into ``n_components`` non-negative parts, in…, Deterministic calibration from labeled cases (INV-16). (+49 more)

### Community 50 - "risk/engine.py"
Cohesion: 0.17
Nodes (17): ValueError, Raised when engine inputs are structurally inconsistent. A hard ``REJECT``…, RiskEngineInputError, compute_inputs_hash(), _dedupe(), evaluate_proposal(), AccountState, datetime (+9 more)

### Community 51 - "domain/__init__.py"
Cohesion: 0.11
Nodes (17): is_live_mode(), True only for the two modes that send real orders to a broker venue., Domain layer: canonical enums and state machines (architecture §5-§18)., assert_valid_order_transition(), assert_valid_strategy_transition(), InvalidStateTransition, is_valid_order_transition(), is_valid_strategy_transition() (+9 more)

### Community 52 - "EmergencyControlState"
Cohesion: 0.05
Nodes (31): build_provenance(), DeadManSwitchState, EmergencyControlState, OperationalAlert, model_validator, Self, Operational alert raised on SAFE_MODE and emergency-control transitions (§31)., Persisted state of one emergency control (INV-7, architecture §10). Keyed by… (+23 more)

### Community 53 - "make_bar"
Cohesion: 0.14
Nodes (12): parquet_to_bars(), Deserialize bars from Parquet bytes., DataQualityFlag, Row-level quality flags attached in the silver layer., make_bar(), _engine(), Unit tests: quality flags, duplicate handling, missing-bar detection., TestDuplicates (+4 more)

### Community 54 - "App.tsx"
Cohesion: 0.11
Nodes (23): get(), App(), CollectionPage(), Icon, money(), OverviewPage(), RecordSummary(), RiskPage() (+15 more)

### Community 55 - "_sizing_probe.py"
Cohesion: 0.17
Nodes (17): AccountState, Risk & Policy contracts consumed by the deterministic Risk Engine (INV-4).…, Point-in-time account state (INV-3). All fields are Decimals — never floats., compute_size_plan(), _currency_legs(), floor_to_step(), _max_currency_notional(), AccountState (+9 more)

### Community 57 - "MarketSnapshot"
Cohesion: 0.08
Nodes (36): EvalReport, evaluate(), evaluate_all(), fixture_to_mock_scenario(), fixture_to_request(), fixture_to_snapshot(), load_scenarios(), BaseModel (+28 more)

### Community 58 - "ScriptedRedis"
Cohesion: 0.11
Nodes (9): OperationalError, operational_error(), Any, datetime, Exception, UUID, A realistic PostgreSQL connectivity failure (server restart window)., Minimal faithful ``RedisConnection`` double for one RedisStreamBus. Streams and… (+1 more)

### Community 59 - "evaluate_cases"
Cohesion: 0.29
Nodes (8): evaluate_cases(), datetime, Compare quant_only / llm_only / quant_plus_llm / baseline on ``cases``.…, _case(), make_config(), datetime, Research evaluation: Quant-only vs LLM-only vs Quant+LLM vs baseline., TestMandatoryComparison

### Community 60 - "CalibrationStore"
Cohesion: 0.12
Nodes (14): CalibrationArtifact, Complete, versioned output of a calibration run. Everything needed to reproduce…, EvaluationReport, Full comparison of the mandatory configurations on one case set., CalibrationStore, Any, Path, UUID (+6 more)

### Community 61 - "make_risk_policy"
Cohesion: 0.19
Nodes (5): make_risk_policy(), datetime, TestAccountState, TestRiskDecisionResize, TestRiskPolicy

### Community 62 - "Target Architecture — Autonomous Quantitative Trading & Research Platform"
Cohesion: 0.07
Nodes (28): 10. Point-in-Time rule (INV-3), 11. Data architecture (INV-10), 12. Event bus (INV-15), 13. Canonical domain objects (INV-2), 14. Signal Fusion (INV-16), 15. Post-trade learning loop, 16. Strategy lifecycle (INV-8), 17. LLM evaluation (+20 more)

### Community 63 - "Settings"
Cohesion: 0.05
Nodes (52): BaseSettings, field_validator, Runtime configuration (pydantic-settings). Environment variables use the…, Live-mode secrets must be at least 32 characters: an empty or weak operator…, Settings, assert_llm_process_cannot_execute(), ExecutionBoundaryViolation, RuntimeError (+44 more)

### Community 64 - "test_workflows.py"
Cohesion: 0.18
Nodes (9): FailingQlib, FakeQlib, FakeRDAgent, MemoryStore, MemoryTracker, Any, Path, test_all_seven_workflow_stages_produce_canonical_outputs() (+1 more)

### Community 65 - "architecture.md"
Cohesion: 0.07
Nodes (27): 12. Regla Point-in-Time, 14. Event Bus, 15. Objetos de dominio canónicos, 16. Signal Fusion Engine, 17. Post-trade learning loop, 18. Strategy Factory, 1. Visión final, 20. Métricas obligatorias (+19 more)

### Community 66 - "make_memory_episode"
Cohesion: 0.07
Nodes (24): The temporal envelope is impossible: event_time <= available_time <=…, TemporalOrderingError, Write one episode into memory. ``available_time`` is the moment the system…, model_validator, Self, Map a domain :class:`MemoryEpisode` to the stored envelope. ``source`` /…, Map the stored record back to the domain contract., MemoryEpisode (+16 more)

### Community 67 - "risk_helpers.py"
Cohesion: 0.21
Nodes (28): AssetClass, build_account(), build_instrument(), build_policy(), build_portfolio(), build_portfolio_with_exposure(), build_proposal(), build_snapshot() (+20 more)

### Community 68 - "5. Scenario playbooks"
Cohesion: 0.12
Nodes (16): 1. Objectives, 2. What is already built in, 3. Backups, 4. Restore, 5.1 Core crash mid-submit, 5.2 MT4 / broker unavailable, 5.3 Material divergence (unexpected broker position / quantity mismatch), 5.4 Postgres loss (volume corruption / deleted) (+8 more)

### Community 69 - "OperatingMode"
Cohesion: 0.21
Nodes (18): OperatingMode, The only five operating modes (INV-8, architecture §5)., InMemoryApprovalStore, Thread-safe test/dev store. Production wiring should use transactional storage., _gate(), _price(), _service(), test_expired_approval_never_reaches_mt4() (+10 more)

### Community 70 - "worker/ledger.py"
Cohesion: 0.17
Nodes (12): FillApplication, Paper ledger: authoritative position & account accounting for the PAPER venue…, Append one observed price point to the open position's path. Bounded…, The observed path for a (possibly closed) position., Outcome of applying one fill report to the ledger., _adverse_extreme(), _favorable_extreme(), PricePoint (+4 more)

### Community 71 - "ConnectionMonitor"
Cohesion: 0.20
Nodes (8): ConnectionMonitor, datetime, Tracks bridge liveness from the heartbeat stream (clock-injected)., ZeroMQ transport + connection health tests (no MetaTrader, no docker)., REQ/REP over inproc in one context — the command channel contract., test_connection_monitor_transitions(), test_inproc_req_rep_roundtrip(), test_monitor_rejects_bad_thresholds()

### Community 72 - "PositionSnapshot"
Cohesion: 0.11
Nodes (13): _OpenPosition, PositionLedger, Decimal, OrderFilled, PositionChanged, PositionClosed, PositionOpened, Account-currency equity: quote cash + base cash at mid + unrealized. (+5 more)

### Community 73 - "DomainObject"
Cohesion: 0.04
Nodes (69): build_domain_event(), deserialize_event(), Any, datetime, UUID, Envelope construction, serialization and validation (INV-15)., Build a standard envelope around a validated canonical payload. The payload…, Deterministic UTF-8 bytes for the event bus. (+61 more)

### Community 74 - "32. Roadmap definitivo"
Cohesion: 0.08
Nodes (26): 32. Roadmap definitivo, Definition of Done, Definition of Done, Definition of Done, Definition of Done, Definition of Done, Definition of Done, Definition of Done (+18 more)

### Community 75 - "Mt4ExecutionClient"
Cohesion: 0.04
Nodes (107): BrokerConfig, BaseModel, Configuration of the simulated venue., build_parser(), _collect_events(), main(), ArgumentParser, Command-line entrypoints for the MT4 execution protocol (Phase 6). - ``run`` —… (+99 more)

### Community 76 - "Instrument"
Cohesion: 0.18
Nodes (6): _instrument_from_row(), Any, Instrument, model_validator, Self, Static description of a tradable instrument (symbol rules, lot rules).

### Community 77 - "TokenUsageCollector"
Cohesion: 0.17
Nodes (9): Any, Duck-typed LangChain callback handler accumulating token usage. Deliberately…, Called by LangChain after each LLM generation completes., Trace the real provider invocation without exporting prompt contents., LangChain callback: start a Langfuse tool observation., Run propagate in a worker thread under the adapter timeout budget. Note: a…, TokenUsageCollector, BaseException (+1 more)

### Community 78 - "._require_calibrated_version"
Cohesion: 0.47
Nodes (3): model_validator, Self, INV-16: weights must derive from historical calibration. A config that never…

### Community 79 - "redact"
Cohesion: 0.11
Nodes (18): Security primitives for trust-zone enforcement (architecture §29, ADR-0025). -…, _attach_filter(), install_redacting_logging(), Log redaction — secrets must never reach logs (architecture §29, ADR-0025).…, Return ``text`` with every known secret pattern masked (``None`` → ``""``)., Masks secret patterns on the record itself, before any handler renders.…, Formatter that masks secret patterns (including exception text)., Install redaction process-wide: filter + redacting std handler. Idempotent… (+10 more)

### Community 80 - "backtest/conftest.py"
Cohesion: 0.09
Nodes (34): build_config(), main(), Deterministic backtest CLI: prints the reproducibility fingerprints. Usage: uv…, BacktestConfig, BaselineSmaConfig, CommissionConfig, BaseModel, datetime (+26 more)

### Community 81 - "nautilus/engine.py"
Cohesion: 0.16
Nodes (23): code_sha(), Decimal, The BACKTEST runner: Nautilus ``BacktestEngine`` + virtual clock + domain…, Git HEAD SHA of the repository, or the adapter version outside a repo. The code…, NautilusTrader adapter — Phase 4, deterministic backtest/paper venue…, compute_metrics(), EquityPoint, _max_drawdown_pct() (+15 more)

### Community 82 - "compilerOptions"
Cohesion: 0.08
Nodes (23): compilerOptions, allowJs, allowSyntheticDefaultImports, esModuleInterop, forceConsistentCasingInFileNames, isolatedModules, jsx, lib (+15 more)

### Community 83 - "test_execution_boundary.py"
Cohesion: 0.33
Nodes (7): assert_emergency_closure_matches_positions(), An emergency intent may only close a known open position (ADR-0025).…, make_closure(), make_position(), Decimal, Execution-boundary hardening (ADR-0025): emergency closures and order mutations…, TestEmergencyClosureMustMatchOpenPosition

### Community 84 - "compute_trade_metrics"
Cohesion: 0.38
Nodes (6): compute_trade_metrics(), MetricsInput, Derive the canonical :class:`TradeMetrics` block for one closed trade., Everything the metric computation reads (pure inputs, no IO)., long_outcome(), TestComputeMetrics

### Community 85 - "strategy.py"
Cohesion: 0.12
Nodes (23): CurrencyPair, BaselineSmaStrategy, DomainStrategy, datetime, Decimal, Protocol, Domain-side strategy contract and the minimal deterministic baseline. The…, What a domain strategy may see at one bar (point-in-time, INV-3). Nothing… (+15 more)

### Community 86 - "PortfolioState"
Cohesion: 0.22
Nodes (7): Portfolio view after the proposed exit: the closing instrument is excluded from…, PortfolioState, model_validator, Self, Point-in-time portfolio state: open positions, pending orders, exposure., _max_orders_reached(), _max_positions_reached()

### Community 87 - "Agent details"
Cohesion: 0.10
Nodes (19): Agent details, Agent index, AI Engineering Team Architecture — OpenTrading, ai-trading-systems, backend-platform, command-center, execution-mt4, Hard boundary (+11 more)

### Community 88 - "3. Classification against the requested axes"
Cohesion: 0.10
Nodes (19): 1. Snapshot facts (repository evidence), 2. Complete repository inventory, 3.10 Tests, 3.11 Configuration, 3.12 Secrets handling, 3.1 Existing trading code, 3.2 Experimental code, 3.3 Duplicated code (+11 more)

### Community 89 - "test_resize.py"
Cohesion: 0.13
Nodes (6): _portfolio(), Decimal, RESIZE paths: the engine reduces the quantity to the binding soft limit. The…, TestExposureResize, TestLeverageMarginResize, TestRiskBudgetResize

### Community 90 - "test_live_infra_restart.py"
Cohesion: 0.32
Nodes (9): _compose(), _docker_available(), live_chaos(), _postgres_up(), fixture, Real container restarts (docker-gated; opt-in). These scenarios actually…, settings(), TestLiveRestarts (+1 more)

### Community 91 - "test_registry.py"
Cohesion: 0.23
Nodes (27): LiveAutoConfig, decision_for(), enabled_config(), intent_for(), make_registry(), price(), promote(), datetime (+19 more)

### Community 92 - "GraphitiConfig"
Cohesion: 0.33
Nodes (3): GraphitiConfig, Connection settings for the live Graphiti-over-FalkorDB store., TestSearchWindowAndConfig

### Community 93 - "5. Controls"
Cohesion: 0.09
Nodes (22): 1. Trust zones, 2. Assets, 3. Threat actors, 4. Threat register, 5. Controls, 6. Definition of Done — traceability, 7. Residual risks, C10 — Emergency controls (INV-7) (+14 more)

### Community 94 - "RiskPolicy"
Cohesion: 0.33
Nodes (5): Decimal, field_validator, Versioned risk policy. Every numeric limit is explicit — no implicit defaults.…, RiskPolicy, _spread_too_high()

### Community 95 - "Architecture Invariants"
Cohesion: 0.11
Nodes (17): Architecture Invariants, INV-10 — Data stores are separated by purpose, INV-11 — Graphify ≠ Graphiti, INV-12 — Frozen decisions require ADRs, INV-13 — Two runtimes, never merged, INV-14 — Dependencies are pinned, INV-15 — Domain events use the standard envelope, INV-16 — Signal Fusion weights are calibrated, not arbitrary (+9 more)

### Community 96 - "VirtualClock"
Cohesion: 0.05
Nodes (64): Protocol, SnapshotSource, PostTradeReconciliationPendingError, RuntimeError, The trade is not yet definitively closed-and-reconciled (INV-6). Raised on…, Deterministic simulation clock. Time only advances through explicit…, VirtualClock, get_settings() (+56 more)

### Community 97 - "LangfuseTracer"
Cohesion: 0.08
Nodes (21): Vendor-specific telemetry adapters with safe no-op defaults., deterministic_trace_id(), LangfuseTracer, NullObservation, Any, UUID, Langfuse v4 tracing correlated to the canonical domain ``trace_id``., Return the W3C 16-byte lowercase hexadecimal trace identifier. (+13 more)

### Community 98 - "synthetic_dataset"
Cohesion: 0.13
Nodes (34): DatasetConfig, Deterministic historical dataset: synthetic (seeded) or parquet replay., Constant spread applied around each bar close when synthesizing quotes., SpreadConfig, build_dataset(), Dataset, _hash_rows(), load_parquet_dataset() (+26 more)

### Community 99 - "test_posttrade_metrics.py"
Cohesion: 0.20
Nodes (8): direction_correct(), Signed move over entry in percent (LONG: up positive; SHORT: down positive)., A producer's stance vs the realized move. LONG is correct when the market rose,…, signed_return_pct(), long_winner_path(), Deterministic metric math for the post-trade learning loop (architecture §17)., TestDirectionCorrectness, TestSignedReturn

### Community 100 - "Operations Manual — OpenTrading"
Cohesion: 0.18
Nodes (10): 1. Operating modes (INV-8), 2. Daily runbook — development / staging, 3. Live operations (LIVE_GATED), 4. Emergency control system (INV-7), 5. Reconciliation (INV-6 — mandatory), 6. Monitoring & alerting, 7. Maintenance tasks, 8. Troubleshooting quick map (+2 more)

### Community 101 - "test_live_auto_api.py"
Cohesion: 0.17
Nodes (22): build_live_auto_router(), DemotionBody, PnlBody, PromotionBody, APIRouter, BaseModel, OperatorResolver, Authenticated operator API for LIVE_AUTO governance (Phase 11). Every mutation… (+14 more)

### Community 102 - "Known Limitations — OpenTrading"
Cohesion: 0.20
Nodes (9): Documentation & repository, Execution & venues, Infrastructure & observability, Known Limitations — OpenTrading, Performance, Resolution policy, Risk & fusion, Security (+1 more)

### Community 103 - "QlibAdapter"
Cohesion: 0.21
Nodes (8): EvaluationResult, Any, BaseModel, Protocol, QlibAdapter, QlibBackend, Qlib result mapper; Qlib classes never enter the canonical domain., Typed Qlib evaluation boundary for the Python 3.11 research runtime.

### Community 104 - "_build_platform_with_poison"
Cohesion: 0.21
Nodes (6): _build_platform_with_poison(), Six M1 bars at 10:00…10:05 plus deliberately planted future information: - a…, Absolute invariant: no returned bar has available_time > as_of., bars/snapshot require as_of; there is no bypass method., TestApiLeakage, TestRepositoryLeakage

### Community 105 - "StageWorker"
Cohesion: 0.10
Nodes (12): Mirror an already-authoritative event (used by synchronous runs)., Reclaim stale PEL entries; dead-letter poisoned ones. Returns the reclaimed…, Dispatch one message; ACK on success, leave unacked on failure. Stages publish…, One pass: recover, then read+dispatch new messages. Returns (reclaimed,…, One consumer group: recovery loop + new-message loop (unattended)., StageWorker, Long-running unattended mode: scheduler + worker threads., Runs the autonomous PAPER pipeline, optionally forever. (+4 more)

### Community 106 - "OrderRejectionSim"
Cohesion: 0.29
Nodes (5): OrderRejectionSim, datetime, Decimal, Deterministic rejection rule chain evaluated per ``OrderIntent``., Return a rejection reason, or ``None`` when the order may proceed.

### Community 107 - "NativeRDAgentQlibBackend"
Cohesion: 0.26
Nodes (4): NativeRDAgentQlibBackend, Any, Concrete bridge to RD-Agent 0.8.0's Qlib factor/model loops. All imports of…, Drive one official RD-Agent hypothesis/code/run cycle at a time.

### Community 108 - "SignalDirection"
Cohesion: 0.09
Nodes (38): build_committee(), infer_stance(), parse_trader_action(), Read the Trader's BUY/HOLD/SELL action out of its rendered proposal., Deterministic, documented heuristic: net bullish/bearish token weight. Used…, Preserve analyst / researcher / trader / portfolio-manager evidence. The…, Translate a normalized upstream result into the canonical ``LLMSignal``.…, result_to_signal() (+30 more)

### Community 109 - "Any"
Cohesion: 0.44
Nodes (12): given, _effective_budget(), _entry_price(), _evaluate(), Any, Decimal, settings, test_approved_risk_and_size_respect_every_soft_limit() (+4 more)

### Community 110 - "test_paper_executor.py"
Cohesion: 0.40
Nodes (6): build_executor(), make_intent(), make_snapshot(), Decimal, Nautilus paper executor tests: fills, slippage, determinism, rejects., TestPaperExecutor

### Community 111 - "Phase 0 — Foundations: Implementation Record"
Cohesion: 0.15
Nodes (12): 10. Explicitly NOT implemented (phase gates), 11. Local verification commands, 1. Definition of Done — evidence, 2. Module map (architecture §27 layout), 3. Canonical contracts (`core/schemas`), 4. Enums and state machines (`core/domain`), 5. Clock semantics (`core/clock`), 6. Event bus contract (`core/events`) (+4 more)

### Community 112 - "Runbook — Infrastructure"
Cohesion: 0.14
Nodes (13): Architecture, Backups (operational notes), Definition of Done (this milestone), Development vs production, Files, Health checks, Migrations, Observability (+5 more)

### Community 113 - "window_blind_store"
Cohesion: 0.25
Nodes (5): A backend that leaks everything — for defense-in-depth tests., window_blind_store(), Sweep as_of through the whole timeline against a backend that reports…, test_invariant_holds_for_every_as_of_in_a_sweep(), TestDefenseInDepth

### Community 114 - "producers.py"
Cohesion: 0.22
Nodes (9): BaselineQuantProducer, _episode_stance(), MemoryContextProducer, datetime, UUID, Signal producers for the research stage (Phase 7). -…, Deterministic momentum quant signal from a single snapshot. ``strength`` scales…, Distills point-in-time memory episodes into a directional stance. Only episodes… (+1 more)

### Community 115 - "Domain Glossary (OpenTrading)"
Cohesion: 0.17
Nodes (11): Core objects (§15), Data (§13), Domain Glossary (OpenTrading), Events (§14), Kill switches (§10), Memory (§11), Operating modes (§6), Order state machine (§9) (+3 more)

### Community 116 - "Detail"
Cohesion: 0.17
Nodes (11): 10–15 Quant, 16–20 Trading, 1–4 Repository intelligence, 21 AI systems, 22–27 Engineering, 28–31 Security, 32–35 Operations, 5–9 Architecture (+3 more)

### Community 117 - "Product"
Cohesion: 0.17
Nodes (11): Accessibility & Inclusion, Capabilities and Constraints, Evidence on Hand, Operating Context, Platform, Positioning, Product, Product Principles (+3 more)

### Community 118 - "NautilusBacktestRunner"
Cohesion: 0.08
Nodes (37): NautilusBacktestRunner, Runs one BACKTEST with the Nautilus simulated venue (virtual clock)., make_config(), A realistic cost-inclusive deterministic config; override any field., _fills(), Cost-model tests: commission, spread, slippage are real and applied (skill:…, test_commission_is_applied_per_fill(), test_partial_fill_status_never_claimed_for_single_fill_orders() (+29 more)

### Community 120 - "SequenceTracker"
Cohesion: 0.27
Nodes (4): Record a newly accepted sequence (must equal expected)., Per-namespace last-accepted sequences (reconciliation payload)., Strict monotonic sequence validation per ``strategy_id`` namespace. Sequences…, SequenceTracker

### Community 121 - "ensure_utc"
Cohesion: 0.10
Nodes (12): datetime, Point-in-time truth: the system could know this item at ``moment`` only if it…, datetime, timedelta, Current time as timezone-aware UTC., Move forward by ``delta`` (strictly positive) and return the new time., Jump to ``moment``; moving backwards is refused (monotonic simulation time)., ensure_utc() (+4 more)

### Community 122 - "Task Routing Workflow"
Cohesion: 0.18
Nodes (10): Anti-swarm rule, Step 1 — Classify, Step 2 — Context, Step 3 — Primary specialist, Step 4 — Mandatory reviewers, Step 5 — Skills, Step 6 — Execute, Step 7 — Verify (+2 more)

### Community 123 - "Observability alert runbook"
Cohesion: 0.18
Nodes (10): Daily loss threshold, Drawdown threshold, LLM provider failure, MT4 heartbeat missing, Observability alert runbook, PostgreSQL failure, Queue backlog, Redis failure (+2 more)

### Community 124 - "mt4/protocol — MT4 execution protocol v1.0 (ADR-0020, §34.18)"
Cohesion: 0.18
Nodes (10): 1. Transport, 2. Envelope (every message), 3. Messages, 4. Validation order (frozen — EA must match), 5. EA defense-in-depth venue checks (INV-5, §8), 6. Error codes, 7. Connection health, 8. Versioning policy (+2 more)

### Community 125 - "Agent: AI Trading Systems"
Cohesion: 0.20
Nodes (9): Agent: AI Trading Systems, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 126 - "Agent: Backend Platform"
Cohesion: 0.20
Nodes (9): Agent: Backend Platform, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 127 - "Agent: Command Center / Frontend"
Cohesion: 0.20
Nodes (9): Agent: Command Center / Frontend, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 128 - "Agent: Execution / MT4"
Cohesion: 0.20
Nodes (9): Agent: Execution / MT4, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 129 - "Agent: Infrastructure & SRE"
Cohesion: 0.20
Nodes (9): Agent: Infrastructure & SRE, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 130 - "Agent: Market Data"
Cohesion: 0.20
Nodes (9): Agent: Market Data, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 131 - "Agent: Principal Architect"
Cohesion: 0.20
Nodes (9): Agent: Principal Architect, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 132 - "Agent: Quant Research"
Cohesion: 0.20
Nodes (9): Agent: Quant Research, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 133 - "Agent: Risk"
Cohesion: 0.20
Nodes (9): Agent: Risk, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 134 - "Agent: Security"
Cohesion: 0.20
Nodes (9): Agent: Security, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 135 - "Agent: Trading & Backtest"
Cohesion: 0.20
Nodes (9): Agent: Trading & Backtest, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 136 - "Agent: Verification"
Cohesion: 0.20
Nodes (9): Agent: Verification, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 137 - "Production Readiness — OpenTrading"
Cohesion: 0.29
Nodes (6): Blocking issues: status after this audit, Open items before live capital (gates), Production Readiness — OpenTrading, Verdict, Verification matrix (how to re-audit), What is production-grade today

### Community 138 - "ADR/README.md"
Cohesion: 0.20
Nodes (8): ADR-0021: Broker reconciliation and Safe Mode (persisted execution state), Consequences, Context, Decision, Accepted, ADR Index — OpenTrading, Frozen items not yet ADR'd, Process

### Community 139 - "26. Command Center"
Cohesion: 0.20
Nodes (10): 26. Command Center, Agents, Backtests, Memory, Orders & Trades, Overview, Research, Risk (+2 more)

### Community 140 - "1. What was built"
Cohesion: 0.20
Nodes (9): 1. What was built, 2. Definition of Done — evidence, 3. Checks run, 4. Operational notes, Extensibility for fundamentals / macro / news, HTTP API (`apps/api/market_data.py`), Phase 1 — Data Platform: Market Data Implementation Record, Pipeline: RAW → BRONZE → SILVER → GOLD → MarketSnapshot (+1 more)

### Community 141 - "Phase 5 — Deterministic Risk & Policy Engine (implementation record)"
Cohesion: 0.20
Nodes (9): Controls, Decision assembly, Definition of Done, Denomination (ADR-0018), Inputs, Phase 5 — Deterministic Risk & Policy Engine (implementation record), Sizing math (deterministic, exact), Tests (`tests/risk/`) (+1 more)

### Community 142 - "Runbook — Local Development"
Cohesion: 0.20
Nodes (9): Daily commands, Endpoints (dev), First-time setup, Market data API (Phase 1), Prerequisites, Runbook — Local Development, Running the API against the stack, Troubleshooting (+1 more)

### Community 143 - "FakeGraph"
Cohesion: 0.22
Nodes (3): FakeGraph, Any, Upstream graph double: records add_episode calls, returns queued edges.

### Community 144 - "19. Validation Factory"
Cohesion: 0.22
Nodes (9): 19. Validation Factory, Backtest básico, Monte Carlo, Multiple-testing protection, Out-of-sample, Purged/embargo validation, Regime testing, Sensitivity (+1 more)

### Community 145 - "Bar"
Cohesion: 0.06
Nodes (48): DatasetNotFoundError, DatasetNotSealedError, DatasetSealedError, FutureDataLeakageError, InstrumentResolutionError, MarketDataError, Exception, Market data platform errors. Concrete error types so callers (pipeline,… (+40 more)

### Community 146 - ".ai — Canonical AI Engineering Layer (OpenTrading)"
Cohesion: 0.25
Nodes (7): Agents (one primary per task by default), .ai — Canonical AI Engineering Layer (OpenTrading), Governance notes, Hard boundary (never changes), Layout, Routing, Tool adapters

### Community 147 - "LLM Agent Evaluation"
Cohesion: 0.25
Nodes (7): Inputs, LLM Agent Evaluation, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 148 - "ADR Management"
Cohesion: 0.25
Nodes (7): ADR Management, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 149 - "Architecture Review"
Cohesion: 0.25
Nodes (7): Architecture Review, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 150 - "Domain Boundary Review"
Cohesion: 0.25
Nodes (7): Domain Boundary Review, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 151 - "Event Contract Design"
Cohesion: 0.25
Nodes (7): Event Contract Design, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 152 - "State Machine Review"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Procedure, Purpose, Related agents, State Machine Review, Trigger conditions

### Community 153 - "API Contract Review"
Cohesion: 0.25
Nodes (7): API Contract Review, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 154 - "Dead Code Detection"
Cohesion: 0.25
Nodes (7): Dead Code Detection, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 155 - "Debugging"
Cohesion: 0.25
Nodes (7): Debugging, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 156 - "Performance Profiling"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Performance Profiling, Procedure, Purpose, Related agents, Trigger conditions

### Community 157 - "Refactoring"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Procedure, Purpose, Refactoring, Related agents, Trigger conditions

### Community 158 - "Test Generation"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Procedure, Purpose, Related agents, Test Generation, Trigger conditions

### Community 159 - "Docker Review"
Cohesion: 0.25
Nodes (7): Docker Review, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 160 - "Incident Analysis"
Cohesion: 0.25
Nodes (7): Incident Analysis, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 161 - "Observability Review"
Cohesion: 0.25
Nodes (7): Inputs, Observability Review, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 162 - "Production Readiness"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Procedure, Production Readiness, Purpose, Related agents, Trigger conditions

### Community 163 - "Backtest Validation"
Cohesion: 0.25
Nodes (7): Backtest Validation, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 164 - "Experiment Reproducibility"
Cohesion: 0.25
Nodes (7): Experiment Reproducibility, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 165 - "Factor Evaluation"
Cohesion: 0.25
Nodes (7): Factor Evaluation, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 166 - "Model Evaluation"
Cohesion: 0.25
Nodes (7): Inputs, Model Evaluation, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 167 - "Point-in-Time Validation"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Point-in-Time Validation, Procedure, Purpose, Related agents, Trigger conditions

### Community 168 - "Walk-Forward Validation"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions, Walk-Forward Validation

### Community 169 - "Change Impact Analysis"
Cohesion: 0.25
Nodes (7): Change Impact Analysis, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 170 - "Dependency Tracing"
Cohesion: 0.25
Nodes (7): Dependency Tracing, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 171 - "Graphify Context"
Cohesion: 0.25
Nodes (7): Graphify Context, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 172 - "Repository Navigation"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Procedure, Purpose, Related agents, Repository Navigation, Trigger conditions

### Community 173 - "Dependency Security"
Cohesion: 0.25
Nodes (7): Dependency Security, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 174 - "Privilege Boundary Review"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Privilege Boundary Review, Procedure, Purpose, Related agents, Trigger conditions

### Community 175 - "Secret Scan"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Procedure, Purpose, Related agents, Secret Scan, Trigger conditions

### Community 176 - "Threat Model"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Procedure, Purpose, Related agents, Threat Model, Trigger conditions

### Community 177 - "Execution Safety"
Cohesion: 0.25
Nodes (7): Execution Safety, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 178 - "Order Lifecycle Review"
Cohesion: 0.25
Nodes (7): Inputs, Order Lifecycle Review, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 179 - "Portfolio Risk Review"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Portfolio Risk Review, Procedure, Purpose, Related agents, Trigger conditions

### Community 180 - "Reconciliation Review"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Procedure, Purpose, Reconciliation Review, Related agents, Trigger conditions

### Community 181 - "Trading Cost Validation"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Procedure, Purpose, Related agents, Trading Cost Validation, Trigger conditions

### Community 182 - "compilerOptions"
Cohesion: 0.25
Nodes (7): compilerOptions, composite, module, moduleResolution, skipLibCheck, include, vite.config.ts

### Community 183 - "Runbook — Secrets management (SOPS + age)"
Cohesion: 0.22
Nodes (8): Encrypting / decrypting, One-time setup, Policy, Production compose, Rotation, Runbook — Secrets management (SOPS + age), Secret inventory (production), Verification

### Community 184 - "_validate_lineage"
Cohesion: 0.46
Nodes (4): Any, model_validator, Self, _validate_lineage()

### Community 185 - "brier_error"
Cohesion: 0.43
Nodes (3): brier_error(), Per-observation calibration error ``(confidence - hit)²``. The proper-scoring-…, TestBrierError

### Community 186 - "allows_order_submission"
Cohesion: 0.31
Nodes (4): allows_order_submission(), True when the pipeline may submit ``OrderIntent``s to a venue. RESEARCH: no…, model_validator, Self

### Community 187 - "Quant R&D Runtime Specification"
Cohesion: 0.25
Nodes (7): Boundaries, Capability map, Commands, Objective, Quant R&D Runtime Specification, Stack and exact pins, Success criteria

### Community 188 - "Postmortem — EURUSD LONG"
Cohesion: 0.29
Nodes (6): Expected vs actual, Lessons, Metrics, Postmortem — EURUSD LONG, Signal quality, Trace

### Community 189 - "env.py"
Cohesion: 0.33
Nodes (5): Alembic environment for OpenTrading. The target DSN comes from the application…, Run migrations in 'offline' mode (emit SQL without a DBAPI connection)., Run migrations in 'online' mode., run_migrations_offline(), run_migrations_online()

### Community 190 - "test_serialization.py"
Cohesion: 0.39
Nodes (7): datetime, parametrize, Deterministic serialization tests for every canonical contract., Same content -> same bytes, independent of construction time., test_json_uses_utc_iso_timestamps(), test_round_trip_is_lossless(), test_serialization_is_deterministic()

### Community 191 - "adapters/graphiti — temporal semantic memory (Phase 3)"
Cohesion: 0.29
Nodes (6): adapters/graphiti — temporal semantic memory (Phase 3), Layout, Live backend (FalkorDB), Memory tiers, Point-in-time semantics (INV-3), Tests

### Community 192 - "adapters/tradingagents — TradingAgents behind a strict boundary (ADR-0004)"
Cohesion: 0.29
Nodes (6): adapters/tradingagents — TradingAgents behind a strict boundary (ADR-0004), Boundary rules, Point-in-time contract (INV-3), Tests, Upstream pin (INV-14), Usage

### Community 193 - ".store"
Cohesion: 0.27
Nodes (6): _load_upstream(), Any, Write one record into Graphiti. The full envelope is embedded in the episode…, Hybrid search with a temporal pushdown; results resolve fail-closed., Episode body: human-readable summary plus the machine-readable envelope., Import the upstream classes. The single upstream import seam. Order: (Graphiti,…

### Community 195 - "ADR-0001: Python as the quantitative backend language"
Cohesion: 0.29
Nodes (6): ADR-0001: Python as the quantitative backend language, Alternatives considered, Consequences, Context, Decision, Validation

### Community 196 - "ADR-0002: TypeScript for the Command Center"
Cohesion: 0.29
Nodes (6): ADR-0002: TypeScript for the Command Center, Alternatives considered, Consequences, Context, Decision, Validation

### Community 197 - "ADR-0003: MQL4 exists only in the MT4 execution bridge"
Cohesion: 0.29
Nodes (6): ADR-0003: MQL4 exists only in the MT4 execution bridge, Alternatives considered, Consequences, Context, Decision, Validation

### Community 198 - "ADR-0004: TradingAgents as the LLM research committee"
Cohesion: 0.29
Nodes (6): ADR-0004: TradingAgents as the LLM research committee, Alternatives considered, Consequences, Context, Decision, Validation

### Community 199 - "ADR-0005: Qlib as the quantitative research platform"
Cohesion: 0.29
Nodes (6): ADR-0005: Qlib as the quantitative research platform, Alternatives considered, Consequences, Context, Decision, Validation

### Community 200 - "ADR-0006: RD-Agent as the autonomous R&D factory (offline)"
Cohesion: 0.29
Nodes (6): ADR-0006: RD-Agent as the autonomous R&D factory (offline), Alternatives considered, Consequences, Context, Decision, Validation

### Community 201 - "ADR-0007: NautilusTrader as the event-driven backtest/paper engine"
Cohesion: 0.29
Nodes (6): ADR-0007: NautilusTrader as the event-driven backtest/paper engine, Alternatives considered, Consequences, Context, Decision, Validation

### Community 202 - "ADR-0008: Graphiti as the temporal trading memory"
Cohesion: 0.29
Nodes (6): ADR-0008: Graphiti as the temporal trading memory, Alternatives considered, Consequences, Context, Decision, Validation

### Community 203 - "ADR-0009: Graphify as development context tooling only"
Cohesion: 0.29
Nodes (6): ADR-0009: Graphify as development context tooling only, Alternatives considered, Consequences, Context, Decision, Validation

### Community 204 - "ADR-0010: PostgreSQL as the transactional source of truth"
Cohesion: 0.29
Nodes (6): ADR-0010: PostgreSQL as the transactional source of truth, Alternatives considered, Consequences, Context, Decision, Validation

### Community 205 - "ADR-0011: MinIO + Parquet for large historical datasets"
Cohesion: 0.29
Nodes (6): ADR-0011: MinIO + Parquet for large historical datasets, Alternatives considered, Consequences, Context, Decision, Validation

### Community 206 - "ADR-0012: Redis Streams as the initial event bus"
Cohesion: 0.29
Nodes (6): ADR-0012: Redis Streams as the initial event bus, Alternatives considered, Consequences, Context, Decision, Validation

### Community 207 - "ADR-0013: Langfuse for AI observability"
Cohesion: 0.29
Nodes (6): ADR-0013: Langfuse for AI observability, Alternatives considered, Consequences, Context, Decision, Validation

### Community 208 - "ADR-0014: Prometheus + Grafana for operational observability"
Cohesion: 0.29
Nodes (6): ADR-0014: Prometheus + Grafana for operational observability, Alternatives considered, Consequences, Context, Decision, Validation

### Community 209 - "ADR-0015: Deterministic Risk Engine (no LLM authority over capital)"
Cohesion: 0.29
Nodes (6): ADR-0015: Deterministic Risk Engine (no LLM authority over capital), Alternatives considered, Consequences, Context, Decision, Validation

### Community 210 - "ADR-0016: MT4 as execution venue only"
Cohesion: 0.29
Nodes (6): ADR-0016: MT4 as execution venue only, Alternatives considered, Consequences, Context, Decision, Validation

### Community 211 - "ADR-0017: Point-in-time market data semantics (medallion pipeline)"
Cohesion: 0.29
Nodes (6): ADR-0017: Point-in-time market data semantics (medallion pipeline), Alternatives considered, Consequences, Context, Decision, Validation

### Community 212 - "ADR-0018: Risk Engine — RESIZE decision and exposure denomination"
Cohesion: 0.29
Nodes (6): ADR-0018: Risk Engine — RESIZE decision and exposure denomination, Alternatives considered, Consequences, Context, Decision, Validation

### Community 213 - "ADR-0019: Signal Fusion Engine — calibrated weights, signed components, regime-specific models"
Cohesion: 0.29
Nodes (6): ADR-0019: Signal Fusion Engine — calibrated weights, signed components, regime-specific models, Alternatives considered, Consequences, Context, Decision, Validation

### Community 214 - "ADR-0020: MT4 execution protocol v1.0 (versioned ZeroMQ, emulator-first)"
Cohesion: 0.29
Nodes (6): ADR-0020: MT4 execution protocol v1.0 (versioned ZeroMQ, emulator-first), Alternatives considered, Consequences, Context, Decision, Validation

### Community 215 - "Context Strategy — OpenTrading"
Cohesion: 0.29
Nodes (6): Cheap context bootstrap, Context Strategy — OpenTrading, Correctness override, Graphify policy, Priority order, Token discipline

### Community 216 - "30. Testing"
Cohesion: 0.29
Nodes (7): 30. Testing, Chaos tests, Integration, Leakage tests, Property-based, Replay tests, Unit

### Community 217 - "Gap Analysis — Current vs Target Architecture"
Cohesion: 0.29
Nodes (6): 1. Component-by-component gap, 2. Documentation-level gaps (closed or remaining), 3. Where the repository is AHEAD of the target, 4. Structural risks of the gap, 5. Verdict, Gap Analysis — Current vs Target Architecture

### Community 218 - "Implementation Order — OpenTrading"
Cohesion: 0.29
Nodes (6): 1. Guiding constraints, 2. Implementation dependency graph, 3. Phase-by-phase order with deliverables and gates, 4. Cross-cutting workstreams (interleaved, not phases), 5. Immediate next actions (still non-feature), Implementation Order — OpenTrading

### Community 219 - "Phase 7 — Autonomous PAPER pipeline"
Cohesion: 0.29
Nodes (6): Components, Definitions of Done (verified by tests), Operating modes, Phase 7 — Autonomous PAPER pipeline, Recovery guarantees, The lifecycle

### Community 220 - "Runbook — Autonomous PAPER pipeline"
Cohesion: 0.29
Nodes (6): 1. Quick start (no infrastructure), 2. Full stack (Redis Streams + PostgreSQL), 3. Key configuration (OT_* env / .env), 4. Operations & recovery, 5. Stop safely, Runbook — Autonomous PAPER pipeline

### Community 221 - "engines/signal_fusion — Signal Fusion Engine (Phase 7, INV-16)"
Cohesion: 0.29
Nodes (6): Calibration & research evaluation, engines/signal_fusion — Signal Fusion Engine (Phase 7, INV-16), Fusion law, Guarantees, Modules, Usage

### Community 222 - "OpenTrading — GitHub Copilot instructions"
Cohesion: 0.29
Nodes (6): Always start here, Context, Hard rules, OpenTrading — GitHub Copilot instructions, Reporting, Routing (do not wait for the user to name an agent)

### Community 223 - "test_reject.py"
Cohesion: 0.11
Nodes (5): Hard-check REJECT paths: every hard violation rejects with its reason code., TestBrokerState, TestMarketDataFreshness, TestStrategyState, TestWhitelist

### Community 225 - "adapters/mt4 — MT4 execution protocol (Phase 6, ADR-0020)"
Cohesion: 0.33
Nodes (5): adapters/mt4 — MT4 execution protocol (Phase 6, ADR-0020), Guarantees implemented, Modules, Topology, Usage

### Community 226 - "adapters/nautilus — NautilusTrader event-driven backtest engine (ADR-0007)"
Cohesion: 0.33
Nodes (5): adapters/nautilus — NautilusTrader event-driven backtest engine (ADR-0007), BACKTEST mode on the virtual clock, Definition of Done, Extending to PAPER / LIVE, Layout

### Community 227 - "Research context — $instrument_id @ $as_of"
Cohesion: 0.33
Nodes (5): Point-in-time market context (valid strictly at or before $as_of), Question, Research context — $instrument_id @ $as_of, Scope, Supplementary context

### Community 228 - "AGENTS.md — OpenTrading (Codex & generic agent adapters)"
Cohesion: 0.33
Nodes (5): AGENTS.md — OpenTrading (Codex & generic agent adapters), Context, Hard rules, Read first (cheap bootstrap), Routing

### Community 229 - "Repository Map (OpenTrading)"
Cohesion: 0.33
Nodes (5): Canonical sources of truth, Domain glossary, Key facts for agents, Repository Map (OpenTrading), Target repository layout (architecture §27 — created in Phase 0)

### Community 230 - "Definition of Done"
Cohesion: 0.33
Nodes (5): Definition of Done, Evidence standard, Mandatory gates (all that apply to the task), Reporting, Review gates

### Community 231 - "TestApprovedRiskInvariant"
Cohesion: 0.40
Nodes (3): parametrize, approved risk <= policy risk — for every decision type, exactly., TestApprovedRiskInvariant

### Community 232 - "Routing Rules — OpenTrading"
Cohesion: 0.33
Nodes (5): Anti-routing rules, Change classes → mandatory reviewers, Examples (canonical), Primary-agent matrix, Routing Rules — OpenTrading

### Community 233 - "10. Kill switch y Dead Man Switch"
Cohesion: 0.33
Nodes (6): 10. Kill switch y Dead Man Switch, Dead man, Emergency kill, Instrument kill, Portfolio kill, Strategy kill

### Community 234 - "Inspiración FinMem"
Cohesion: 0.33
Nodes (6): 11. Memoria: Graphiti + conceptos de FinMem, Inspiración FinMem, Long-term memory, Medium-term memory, Ontología de trading, Short-term memory

### Community 235 - "13. Arquitectura de datos"
Cohesion: 0.33
Nodes (6): 13. Arquitectura de datos, FalkorDB + Graphiti, MLflow, Parquet + MinIO, PostgreSQL + TimescaleDB, Redis

### Community 236 - "6. Los cinco modos operativos"
Cohesion: 0.33
Nodes (6): 6. Los cinco modos operativos, BACKTEST, LIVE_AUTO, LIVE_GATED, PAPER, RESEARCH

### Community 237 - "8. MetaTrader 4: solamente capa de ejecución"
Cohesion: 0.33
Nodes (6): 8. MetaTrader 4: solamente capa de ejecución, Canales propuestos, Por qué no WebRequest, Protocol, Transporte, Validaciones dentro del EA

### Community 238 - "Phase 7 — Execution state: broker reconciliation & Safe Mode (implemented)"
Cohesion: 0.33
Nodes (5): DoD evidence, Phase 7 — Execution state: broker reconciliation & Safe Mode (implemented), Reconciliation resolution matrix, State machine, What was built

### Community 239 - "engines/risk — Deterministic Risk & Policy Engine (Phase 5)"
Cohesion: 0.33
Nodes (5): Checks, Decision model (ADR-0018), Determinism, engines/risk — Deterministic Risk & Policy Engine (Phase 5), Usage

### Community 240 - "OpenTrading — Autonomous Quantitative Trading & Research Platform"
Cohesion: 0.33
Nodes (5): Canonical documents, Development, OpenTrading — Autonomous Quantitative Trading & Research Platform, Repository layout (per `docs/architecture.md` §27), Status

### Community 241 - "SafeModeViolation"
Cohesion: 0.20
Nodes (16): Action classes gated by SAFE_MODE. Only NEW_ENTRY is blocked., SafeModeAction, RuntimeError, Raise :class:`SafeModeViolation` for blocked actions while active., Raised when an action is blocked while SAFE_MODE is active., SafeModeViolation, fixture, SafeModeController DoD tests: gate semantics, alerts, audit, idempotency. (+8 more)

### Community 242 - "RDAgentBackend"
Cohesion: 0.33
Nodes (3): Any, Protocol, RDAgentBackend

### Community 243 - "test_import_guard.py"
Cohesion: 0.47
Nodes (4): _forbidden_imports(), AST, DoD guard: the domain layer (core/) imports no external trading framework.…, test_core_imports_no_external_trading_framework()

### Community 244 - "Trade — 2c7c2d4f-fec5-5bdb-a428-4ebde0e0f237"
Cohesion: 0.40
Nodes (4): Canonical event snapshot, Summary, Trace, Trade — 2c7c2d4f-fec5-5bdb-a428-4ebde0e0f237

### Community 245 - "Cross-Review Rules"
Cohesion: 0.40
Nodes (4): Anti-patterns, Cross-Review Rules, Escalation ladder, How to detect the change class

### Community 246 - "apps/worker — Autonomous PAPER pipeline (Phase 7, ADR-0022)"
Cohesion: 0.40
Nodes (4): apps/worker — Autonomous PAPER pipeline (Phase 7, ADR-0022), Delivery & recovery, Layout, Run

### Community 247 - "CLAUDE.md — OpenTrading (Claude Code adapter)"
Cohesion: 0.40
Nodes (4): Bootstrap (read before working), CLAUDE.md — OpenTrading (Claude Code adapter), Report, Working rules

### Community 250 - "ADR-0022: Autonomous PAPER pipeline — Redis Streams stages, idempotent run ledger, recovery semantics"
Cohesion: 0.40
Nodes (4): ADR-0022: Autonomous PAPER pipeline — Redis Streams stages, idempotent run ledger, recovery semantics, Consequences, Context, Decision

### Community 251 - "ADR-0023: Post-trade analysis & learning engine — deterministic postmortems with four sinks"
Cohesion: 0.40
Nodes (4): ADR-0023: Post-trade analysis & learning engine — deterministic postmortems with four sinks, Consequences, Context, Decision

### Community 252 - "ADR-0024: Emergency control system — kill switches and dead man switch"
Cohesion: 0.40
Nodes (4): ADR-0024: Emergency control system — kill switches and dead man switch, Consequences, Context, Decision

### Community 253 - "7. Risk Engine: componente más importante"
Cohesion: 0.40
Nodes (5): 7. Risk Engine: componente más importante, Controles, Entradas, Invariante, Resultado

### Community 254 - "Phase 7 — Post-trade analysis & learning engine (ADR-0023)"
Cohesion: 0.40
Nodes (4): Files, Key design points, Phase 7 — Post-trade analysis & learning engine (ADR-0023), Tests

### Community 255 - "engines/posttrade — Post-trade analysis & learning engine (Phase 7, ADR-0023)"
Cohesion: 0.40
Nodes (4): engines/posttrade — Post-trade analysis & learning engine (Phase 7, ADR-0023), Invariants, Layout, Metric definitions

### Community 256 - "mt4/ — MetaTrader 4 execution-only layer (Phase 6, INV-5)"
Cohesion: 0.40
Nodes (4): Layout, mt4/ — MetaTrader 4 execution-only layer (Phase 6, INV-5), Run the emulator / lifecycle, Status

### Community 257 - "WireGuard — private transport for remote Windows MT4 deployments"
Cohesion: 0.33
Nodes (5): Hardening rules, Layout, Setup, Topology, WireGuard — private transport for remote Windows MT4 deployments

### Community 258 - "Context Usage Rules"
Cohesion: 0.50
Nodes (3): Budget discipline, Context Usage Rules, Maintenance

### Community 259 - "ADR Template"
Cohesion: 0.50
Nodes (3): ADR Template, Process, When an ADR is required

### Community 261 - "Routing Validation — OpenTrading"
Cohesion: 0.50
Nodes (3): Checks performed, Routing Validation — OpenTrading, Verified by design (not yet executable)

### Community 262 - "Strategy Validation Factory"
Cohesion: 0.50
Nodes (3): Evidence and PAPER eligibility, Required stages, Strategy Validation Factory

### Community 267 - "ADR-0026 — LIVE_AUTO governance: automated live trading, disabled by default"
Cohesion: 0.40
Nodes (4): ADR-0026 — LIVE_AUTO governance: automated live trading, disabled by default, Consequences, Context, Decision

### Community 269 - "29. Seguridad"
Cohesion: 0.67
Nodes (3): 29. Seguridad, MT4, Secrets

### Community 270 - "4. Qlib + RD-Agent: fábrica cuantitativa autónoma"
Cohesion: 0.67
Nodes (3): 4. Qlib + RD-Agent: fábrica cuantitativa autónoma, Entorno separado, Qué podrá hacer nuestro Quant Factory

### Community 271 - "5. NautilusTrader: columna vertebral del trading"
Cohesion: 0.67
Nodes (3): 5. NautilusTrader: columna vertebral del trading, Función, Regla fundamental

### Community 328 - "tests/chaos — dedicated chaos/recovery suite"
Cohesion: 0.40
Nodes (4): Deterministic construction rules, Scenario matrix, tests/chaos — dedicated chaos/recovery suite, Validation properties (DoD)

### Community 344 - "ADR-0025 — Security hardening milestone: trust zones, least privilege, secret lifecycle"
Cohesion: 0.40
Nodes (4): ADR-0025 — Security hardening milestone: trust zones, least privilege, secret lifecycle, Consequences, Context, Decision

### Community 345 - "PortfolioExposure"
Cohesion: 0.07
Nodes (9): PortfolioExposure, Pre-computed aggregate exposures of the current portfolio (engines/portfolio).…, TestSimultaneity, Boundary tests: exactly-at-limit behavior with exact Decimal arithmetic.…, TestCountBoundaries, TestLeverageMarginBoundary, TestRiskBoundary, TestSizeBoundaries (+1 more)

### Community 346 - "ExecutionService"
Cohesion: 0.09
Nodes (15): ReconciliationResponse, LiveExecutionRuntime, Deterministic dead man evaluation (safe to call on a cadence)., ExecutionService, datetime, Protocol, UUID, Owns the submit path and the restart reconciliation procedure. (+7 more)

### Community 352 - "infra_health.py"
Cohesion: 0.43
Nodes (6): main(), probe_http(), probe_minio(), probe_postgres(), probe_redis(), ProbeResult

## Knowledge Gaps
- **1014 isolated node(s):** `files`, `name`, `private`, `version`, `type` (+1009 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **76 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Clock` connect `Clock` to `WireMessage`, `DomainEvent`, `InMemoryStreamBus`, `OrderType`, `FusionInputs`, `Memory`, `Bar`, `OrderRecord`, `market_data/pipeline.py`, `Stack`, `normalization.py`, `PaperLedger`, `graphiti/memory.py`, `OrderState`, `main.py`, `HumanApprovalGate`, `quality.py`, `worker_helpers.py`, `LiveAutoRegistry`, `MemoryRecord`, `worker/ledger.py`, `ConnectionMonitor`, `DomainObject`, `Mt4ExecutionClient`, `ExecutionService`, `VirtualClock`, `StageWorker`, `ensure_utc`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._
- **Why does `OrderIntent` connect `Clock` to `DomainEvent`, `OrderType`, `mapping.py`, `OrderRecord`, `Stack`, `PaperLedger`, `OrderState`, `factories.py`, `make_order_intent`, `schemas/__init__.py`, `HumanApprovalGate`, `test_paper_ledger.py`, `NautilusPaperExecutor`, `NautilusRouterStrategy`, `LiveAutoRegistry`, `allows_order_submission`, `OperatingMode`, `worker/ledger.py`, `DomainObject`, `Mt4ExecutionClient`, `backtest/conftest.py`, `test_execution_boundary.py`, `strategy.py`, `ExecutionService`, `OrderRejectionSim`, `test_paper_executor.py`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Why does `SignalDirection` connect `SignalDirection` to `Clock`, `DomainEvent`, `TradeLifecycle`, `make_market_snapshot`, `TradeProposal`, `mapping.py`, `enums.py`, `FusionInputs`, `mapper.py`, `PaperLedger`, `OrderState`, `factories.py`, `schemas/__init__.py`, `stages/posttrade.py`, `test_client.py`, `calibration.py`, `domain/__init__.py`, `_sizing_probe.py`, `MarketSnapshot`, `evaluate_cases`, `CalibrationStore`, `risk_helpers.py`, `worker/ledger.py`, `compute_trade_metrics`, `test_posttrade_metrics.py`, `Any`, `producers.py`, `NautilusBacktestRunner`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Are the 45 inferred relationships involving `VirtualClock` (e.g. with `_long_adapter()` and `_snapshot_event()`) actually correct?**
  _`VirtualClock` has 45 INFERRED edges - model-reasoned connections that need verification._
- **Are the 81 inferred relationships involving `Stack` (e.g. with `TestPostgresRestart` and `_service()`) actually correct?**
  _`Stack` has 81 INFERRED edges - model-reasoned connections that need verification._
- **Are the 83 inferred relationships involving `SignalDirection` (e.g. with `trade_outcome_from_position_closed()` and `build_committee()`) actually correct?**
  _`SignalDirection` has 83 INFERRED edges - model-reasoned connections that need verification._
- **Are the 40 inferred relationships involving `Clock` (e.g. with `Memory` and `MarketDataPipeline`) actually correct?**
  _`Clock` has 40 INFERRED edges - model-reasoned connections that need verification._