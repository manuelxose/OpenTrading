# Graph Report - OpenTrading  (2026-08-29)

## Corpus Check
- 540 files · ~233,498 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 6626 nodes · 18311 edges · 362 communities (285 shown, 77 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 1674 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `70402ede`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Mt4Emulator
- enums.py
- DomainEvent
- InMemoryStreamBus
- TradeLifecycle
- make_market_snapshot
- protocol.py
- TradeProposal
- mapping.py
- test_hashing.py
- make_submit
- workflows.py
- repository.py
- FusionInputs
- evaluate
- LiveGraphitiStore
- mapper.py
- test_export.py
- OrderRecord
- LayerName
- FakeReconcileClient
- normalization.py
- PaperLedger
- make_record
- Timeframe
- Memory
- InMemoryExecutionStateStore
- QuantResearchWorkflows
- health.py
- test_contracts.py
- ExperimentRun
- test_paper_contracts.py
- devDependencies
- make_order_intent
- analysis.py
- OperatingMode
- Bar
- PostTradeReviewRecord
- schemas/memory.py
- worker/cli.py
- test_paper_ledger.py
- test_posttrade_integration.py
- test_client.py
- NautilusPaperExecutor
- NautilusRouterStrategy
- StrategyState
- LiveAutoStrategyRecord
- MemoryRecord
- test_command_center_api.py
- BaseContractModel
- SystemClock
- domain/__init__.py
- EmergencyControlState
- make_bar
- App.tsx
- market_data/pipeline.py
- test_invariants.py
- LLMSignal
- ScriptedRedis
- evaluate_cases
- CalibrationStore
- make_risk_policy
- Target Architecture — Autonomous Quantitative Trading & Research Platform
- Settings
- EmergencyController
- architecture.md
- build_memory
- risk_helpers.py
- 5. Scenario playbooks
- stages/posttrade.py
- KillScope
- signal_fusion/fusion.py
- PositionSnapshot
- schemas/__init__.py
- 32. Roadmap definitivo
- OrderType
- factories.py
- TokenUsageCollector
- FusionConfig
- redact
- nautilus/__init__.py
- nautilus/engine.py
- compilerOptions
- OrderState
- test_versioning.py
- strategy.py
- ._check_loss_streak
- Agent details
- 3. Classification against the requested axes
- TestExposureResize
- test_live_infra_restart.py
- test_registry.py
- LiveAutoRegistry
- 5. Controls
- Decimal
- Architecture Invariants
- VirtualClock
- OperationalMetrics
- Instrument
- Guía Completa de Instalación y Uso — OpenTrading
- Operations Manual — OpenTrading
- test_live_auto_api.py
- Known Limitations — OpenTrading
- EvaluationResult
- _build_platform_with_poison
- StageWorker
- OrderRejectionSim
- NativeRDAgentQlibBackend
- signals.py
- Any
- test_paper_executor.py
- Phase 0 — Foundations: Implementation Record
- Runbook — Infrastructure
- command_center.py
- MarketSnapshot
- Domain Glossary (OpenTrading)
- Detail
- Product
- NautilusBacktestRunner
- make_intent
- SequenceTracker
- infra_health.py
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
- _WindowBlindStore
- 19. Validation Factory
- MarketDataRepository
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
- test_posttrade_notes.py
- model_validator
- Quant R&D Runtime Specification
- Postmortem — EURUSD LONG
- env.py
- test_serialization.py
- adapters/graphiti — temporal semantic memory (Phase 3)
- adapters/tradingagents — TradingAgents behind a strict boundary (ADR-0004)
- .store
- SignalDirection
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
- signal_fusion/config.py
- build_domain_event
- adapters/mt4 — MT4 execution protocol (Phase 6, ADR-0020)
- adapters/nautilus — NautilusTrader event-driven backtest engine (ADR-0007)
- Research context — $instrument_id @ $as_of
- AGENTS.md — OpenTrading (Codex & generic agent adapters)
- Repository Map (OpenTrading)
- Definition of Done
- test_adapter_boundary.py
- Routing Rules — OpenTrading
- 10. Kill switch y Dead Man Switch
- Inspiración FinMem
- 13. Arquitectura de datos
- 6. Los cinco modos operativos
- 8. MetaTrader 4: solamente capa de ejecución
- Phase 7 — Execution state: broker reconciliation & Safe Mode (implemented)
- engines/risk — Deterministic Risk & Policy Engine (Phase 5)
- OpenTrading — Autonomous Quantitative Trading & Research Platform
- Stack
- PostgresAuditSink
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
- .__init__
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
- RiskReasonCode
- ExecutionService
- .from_episode
- test-postgres-roles.sh
- assert_llm_process_cannot_execute
- 002-roles.sh
- entrypoint-acl.sh
- test_live_auto.py
- test_infra_smoke.py
- live_auto.py
- test_settings.py
- .canonical_dict
- test_end_to_end.py
- ._check_temporal_order
- TestWorkerHasNoExecutionCapability
- TestSeparationFromTrading

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
- `test_rating_profile_covers_all_tiers()` --uses--> `SignalDirection`  [INFERRED]
  tests/unit/tradingagents/test_mapper.py → core/domain/enums.py
- `test_live_store_never_leaks_upstream_errors()` --uses--> `GraphitiUnavailableError`  [INFERRED]
  tests/unit/graphiti/test_adapter_boundary.py → adapters/graphiti/errors.py
- `test_graphiti_can_disappear_and_the_domain_still_works()` --uses--> `GraphitiIngestError`  [INFERRED]
  tests/unit/graphiti/test_adapter_boundary.py → adapters/graphiti/errors.py

## Import Cycles
- None detected.

## Communities (362 total, 77 thin omitted)

### Community 0 - "Mt4Emulator"
Cohesion: 0.03
Nodes (80): Core-side MT4 execution client (Phase 6, ADR-0020). The client is the Core's…, Send one command and await its reply (idempotent-safe retries OK). Raises…, Mt4Emulator, datetime, Python MT4 emulator — the bridge's stand-in before real MetaTrader (Phase 6).…, One serve iteration: handle a command (if any) + periodic work., The Python stand-in for QuantBridgeEA.mq4 + the broker. Serve loop runs in a…, Bind channels and (optionally) start the serve thread. Returns the actually… (+72 more)

### Community 1 - "enums.py"
Cohesion: 0.03
Nodes (121): get_mt4_settings(), Mt4Settings, BaseSettings, MT4 execution settings (OT_MT4_* environment variables). Mirrors the pattern of…, Process-wide MT4 settings singleton (matching core get_settings)., Authenticated operator API for the emergency control system (INV-7). Mounts…, OpenTrading API service (core runtime, Python 3.12). Operational endpoints: -…, Paper ledger: authoritative position & account accounting for the PAPER venue… (+113 more)

### Community 2 - "DomainEvent"
Cohesion: 0.05
Nodes (71): Any, UUID, Trade lifecycle transition helpers (Phase 7). All lifecycle mutations flow…, Move the trace's lifecycle to ``target`` if the canonical machine allows it.…, Apply a sequence of transitions in order (each CAS-guarded)., transition(), transition_chain(), PaperPipeline (+63 more)

### Community 3 - "InMemoryStreamBus"
Cohesion: 0.04
Nodes (43): BusUnavailableError, _connection_factory(), InMemoryStreamBus, new_trace_id(), PendingMessage, Any, Protocol, RuntimeError (+35 more)

### Community 4 - "TradeLifecycle"
Cohesion: 0.04
Nodes (52): _account_from_row(), _account_values(), _context_from_row(), InMemoryPipelineStore, _lifecycle_from_row(), _lifecycle_values(), PipelineStore, PostgresPipelineStore (+44 more)

### Community 5 - "make_market_snapshot"
Cohesion: 0.09
Nodes (47): Translate a canonical request into the upstream ``propagate`` surface., Translate a normalized upstream result into the canonical ``LLMSignal``.…, request_to_upstream_input(), result_to_signal(), make_market_snapshot(), build_research_request(), A valid ResearchRequest whose instrument/as_of live in ``context``., MonkeyPatch (+39 more)

### Community 6 - "protocol.py"
Cohesion: 0.05
Nodes (57): BrokerOutcome, AccountState, datetime, Decimal, UUID, _quote(), QuoteEngine, Deterministic simulated broker for the MT4 emulator (Phase 6, ADR-0020). The… (+49 more)

### Community 7 - "TradeProposal"
Cohesion: 0.07
Nodes (65): Portfolio view after the proposed exit: the closing instrument is excluded from…, AccountState, PortfolioState, Risk & Policy contracts consumed by the deterministic Risk Engine (INV-4).…, Point-in-time portfolio state: open positions, pending orders, exposure., Point-in-time account state (INV-3). All fields are Decimals — never floats., Point-in-time strategy configuration snapshot. ``allowed_instruments=None``…, Versioned risk policy. Every numeric limit is explicit — no implicit defaults.… (+57 more)

### Community 8 - "mapping.py"
Cohesion: 0.12
Nodes (33): Domain-side position accounting that mirrors the Nautilus venue ledger.…, _decimal(), provenance(), datetime, OrderAccepted, OrderDenied, OrderFilled, OrderRejected (+25 more)

### Community 9 - "test_hashing.py"
Cohesion: 0.12
Nodes (30): bar_checksum(), canonical_bar_bytes(), canonical_decimal(), canonical_timestamp(), dataset_hash(), _hash_stream(), partition_hash(), Any (+22 more)

### Community 10 - "make_submit"
Cohesion: 0.06
Nodes (65): BrokerConfig, BaseModel, model_validator, Broker-side symbol constraints the EA enforces before sending orders., Configuration of the simulated venue., SymbolSpec, CommandGate, Validates incoming commands: expiry → duplicates → sequence. (+57 more)

### Community 11 - "workflows.py"
Cohesion: 0.06
Nodes (48): QlibAdapter, Validate untrusted upstream output before it enters a workflow., RDAgentAdapter, PermissionError, assert_runtime_version(), main(), Any, Fail-closed executable composition for autonomous canonical Quant R&D. (+40 more)

### Community 12 - "repository.py"
Cohesion: 0.05
Nodes (61): Catalog, MemoryCatalog, PostgresCatalog, datetime, Protocol, UUID, Market data catalog: PostgreSQL-backed (ADR-0010) or in-memory. The catalog…, Deterministic in-memory catalog (unit and leakage tests). (+53 more)

### Community 13 - "FusionInputs"
Cohesion: 0.11
Nodes (29): FusionInputs, MemoryContext, Signal Fusion input contracts (INV-16, Phase 7). The fusion engine fuses up to…, Market-regime classifier output (architecture §16 regime testing).…, Memory-derived stance from the temporal memory (Graphiti, INV-3, INV-11). A…, All fusion inputs for one instrument at one point in time. Any input may be…, Names of the inputs that are present, in canonical engine order., RegimeContext (+21 more)

### Community 14 - "evaluate"
Cohesion: 0.03
Nodes (23): A Risk Decision is never a bare boolean (INV-4, architecture §7). ``RESIZE``…, RiskDecisionType, evaluate(), Evaluate a proposal against the baseline inputs with dict overrides.…, APPROVE paths: the engine accepts the proposal quantity unchanged., TestApproveVariants, TestBaselineApprove, For each soft limit: an adversarial proposal never bypasses the limit. Every… (+15 more)

### Community 15 - "LiveGraphitiStore"
Cohesion: 0.07
Nodes (39): _installed_version(), LiveGraphitiStore, UUID, Live Graphiti-over-FalkorDB store — the ONLY module allowed to import upstream.…, Close the underlying graph driver (idempotent)., Known envelopes (test/debug surface)., Distribution version of the installed upstream, or None if absent., Graphiti storage backed by FalkorDB (ADR-0008: FalkorDB first). Requires… (+31 more)

### Community 16 - "mapper.py"
Cohesion: 0.05
Nodes (75): _installed_version(), _installed_version_safely(), _load_graph_class(), _load_graph_class_safely(), Live TradingAgents adapter — the ONLY module allowed to import upstream.…, Distribution version of the installed upstream, or None if absent., Import the upstream graph class. The single upstream import seam., Exception (+67 more)

### Community 17 - "test_export.py"
Cohesion: 0.07
Nodes (37): _canonical_id(), initialize_vault(), _note_path(), ObsidianExporter, Path, ValueError, Best-effort Obsidian mirror of authoritative domain events. The event bus and…, Write a mirror note when ``event`` is exportable; otherwise return ``None``. (+29 more)

### Community 18 - "OrderRecord"
Cohesion: 0.05
Nodes (33): OrderRecord, The single authoritative persisted record for one ``order_intent_id``. Keyed by…, OrderStateApplier, datetime, Decimal, UUID, Persist the canonical crossing object (INV-2) as ORDER_INTENT., Persist SUBMITTED **before** the wire send (crash-after-submit safety). (+25 more)

### Community 19 - "LayerName"
Cohesion: 0.09
Nodes (15): LayerStore, MemoryLayerStore, MinioLayerStore, parquet_to_raw(), Any, Protocol, Deterministic in-memory store used by unit and leakage tests., S3-compatible object storage backed by MinIO (ADR-0011). (+7 more)

### Community 20 - "FakeReconcileClient"
Cohesion: 0.11
Nodes (37): FakeReconcileClient, make_reconciliation_response(), not_connected_error(), Implements the service's ReconcileClient protocol without any sockets., heartbeat(), pending_order(), datetime, ExecutionService + EmergencyController integration DoD tests. Proves the… (+29 more)

### Community 21 - "normalization.py"
Cohesion: 0.07
Nodes (24): NormalizationError, A raw payload could not be mapped to a normalized record., BarPayloadMapper, build_bar_from_payload(), _epoch_to_utc(), normalize_timestamp(), parse_timeframe(), Any (+16 more)

### Community 22 - "PaperLedger"
Cohesion: 0.10
Nodes (17): FillApplication, LedgerPosition, PaperLedger, AccountState, datetime, Decimal, UUID, Append one observed price point to the open position's path. Bounded… (+9 more)

### Community 23 - "make_record"
Cohesion: 0.06
Nodes (30): Temporal window pushed down to the store as an optimization. The authoritative…, Temporal validity interval [``valid_from``, ``valid_until``].…, Duration in seconds, or None when open-ended., SearchWindow, Validity, InMemoryStore, Deterministic in-memory backend — same window semantics as the live store.…, _tokens() (+22 more)

### Community 24 - "Timeframe"
Cohesion: 0.10
Nodes (37): Timeframe, Leakage tests: future information must be impossible to retrieve (INV-3). Phase…, DoD: (instrument X, dataset version Y, as_of T) → same hash, always., TestDeterministicDoD, TestImmutabilityLeakage, ingest_and_seal(), make_minute_raw_records(), Platform (+29 more)

### Community 25 - "Memory"
Cohesion: 0.09
Nodes (22): FutureMemoryLeakageError, INV-3 violation: an episode with available_time > as_of reached the query…, Memory, PointInTimeFilter, datetime, UUID, Write one episode into memory. ``available_time`` is the moment the system…, Point-in-time retrieval: what the system knew at ``as_of``. Never exposes an… (+14 more)

### Community 26 - "InMemoryExecutionStateStore"
Cohesion: 0.05
Nodes (40): Result of one mandatory reconciliation pass (INV-6, §9)., Persisted SAFE_MODE state (singleton row in PostgreSQL)., ReconciliationRun, SafeModeRecord, _empty_safe_mode(), InMemoryExecutionStateStore, datetime, Deterministic in-memory store with the exact same semantics as Postgres. (+32 more)

### Community 27 - "QuantResearchWorkflows"
Cohesion: 0.12
Nodes (19): Any, Protocol, RD-Agent translation seam for the isolated Python 3.11 service., RDAgentBackend, Typed boundary around Microsoft RD-Agent (offline research only)., Hypothesis, Implementation, BaseModel (+11 more)

### Community 28 - "health.py"
Cohesion: 0.13
Nodes (18): check_falkordb(), check_minio(), check_postgres(), check_redis(), HealthCheckResult, CheckFunc, Dependency readiness checks backing ``GET /readyz`` (§31 observability). Each…, Run one probe with a hard timeout; never raise. (+10 more)

### Community 29 - "test_contracts.py"
Cohesion: 0.08
Nodes (21): One fused input (quant / llm / regime / memory) with calibrated weight.…, SignalComponent, make_fused_signal(), make_risk_decision_approve(), datetime, parametrize, Schema validation tests: every contract validates, bad input is rejected., test_contract_constructs() (+13 more)

### Community 30 - "ExperimentRun"
Cohesion: 0.12
Nodes (23): ExperimentStatus, ExperimentRun, Quant factory contracts: factor/model/strategy candidates and experiment runs…, One reproducible experiment (MLflow-native abstraction, architecture §10)., A strategy under the INV-8 lifecycle. No RD-Agent -> LIVE edge exists., StrategyCandidate, Strategy promotion pipeline — deterministic validation gate (INV-8)., ExperimentRecorder (+15 more)

### Community 31 - "test_paper_contracts.py"
Cohesion: 0.12
Nodes (8): assert_valid_trade_transition(), is_valid_trade_transition(), Pipeline contract, state machine and registry tests (Phase 7)., TestEventRegistry, TestPaperAccountRecord, TestPipelineRunRecord, TestTradeLifecycle, TestTradeLifecycleMachine

### Community 32 - "devDependencies"
Cohesion: 0.04
Nodes (47): dependencies, lucide-react, react, react-dom, typescript, vite, @vitejs/plugin-react, devDependencies (+39 more)

### Community 33 - "make_order_intent"
Cohesion: 0.10
Nodes (29): instrument_to_nautilus(), order_intent_to_order(), CurrencyPair, Venue, Map the canonical domain ``Instrument`` to a Nautilus spot ``CurrencyPair``.…, Map the canonical ``OrderIntent`` to a native Nautilus order.…, LimitOrder, MarketOrder (+21 more)

### Community 34 - "analysis.py"
Cohesion: 0.06
Nodes (55): ExecutionQualityRecord, PostTradeContract, Post-trade analysis contracts (Phase 7, architecture §15 "Post-trade learning…, Independent quality evaluation of one signal producer (INV-16). ``producer`` is…, Independent evaluation of the Risk Decision quality. ``limits_respected``…, Independent evaluation of execution quality (costs, slippage)., Frozen, closed, schema-version-pinned base for post-trade records., Canonical per-trade metrics (architecture §17). Semantics (documented in… (+47 more)

### Community 35 - "OperatingMode"
Cohesion: 0.08
Nodes (45): build_live_gated_router(), DecisionBody, KillBody, APIRouter, BaseModel, OperatorResolver, Authenticated operator API for LIVE_GATED approval and emergency controls., Build the mutation API; callers must inject a real authentication dependency. (+37 more)

### Community 36 - "Bar"
Cohesion: 0.14
Nodes (15): DataQualityEngine, _next_bar_time(), datetime, timedelta, QualityOutcome, Silver-layer data quality: flags, duplicate handling, missing-bar detection.…, Deterministic duplicate resolution. Key: ``(instrument_id, timeframe,…, Interior gaps per (instrument, timeframe) against the bar grid. (+7 more)

### Community 37 - "PostTradeReviewRecord"
Cohesion: 0.09
Nodes (21): PostTradeReviewRecord, model_validator, Self, Persisted canonical-metrics row (PostgreSQL, INV-10). One row per closed-and-…, PostgresPostTradeStore, PostTradeStore, Any, Protocol (+13 more)

### Community 38 - "schemas/memory.py"
Cohesion: 0.10
Nodes (26): OntologyError, An entity type or relation is not part of the frozen trading ontology., assert_known_entities(), assert_known_relations(), _extraction_model(), BaseModel, Frozen trading ontology (ADR-0008, architecture §11). Seventeen entity types…, Ontology gate for a whole episode: every entity type and relation must be known. (+18 more)

### Community 39 - "worker/cli.py"
Cohesion: 0.05
Nodes (57): PaperVenueConfig, BaseModel, Venue parameters for the Nautilus paper simulator. ``slippage_*`` and…, build_default_config(), _instrument(), main(), _parser(), ArgumentParser (+49 more)

### Community 40 - "test_paper_ledger.py"
Cohesion: 0.19
Nodes (11): account_record(), build_ledger(), make_fill_report(), make_intent(), Decimal, PaperLedger tests: netting, closes, outcomes, account/portfolio views., Minimal execution-store double recording only positions., _RecordingExecutionStore (+3 more)

### Community 41 - "test_posttrade_integration.py"
Cohesion: 0.09
Nodes (22): artifact_key(), ArtifactStore, build_artifact(), MinioArtifactStore, Any, datetime, Protocol, UUID (+14 more)

### Community 42 - "test_client.py"
Cohesion: 0.12
Nodes (30): LiveTradingAgentsAdapter, Strict adapter boundary around ``TradingAgentsGraph.propagate``. Lifecycle per…, AdapterConfig, Explicit configuration for one adapter instance. Model choice is mandatory —…, fake_state(), FakeGraph, FakeResponse, Any (+22 more)

### Community 43 - "NautilusPaperExecutor"
Cohesion: 0.05
Nodes (30): ConfigurableSlippageFillModel, NotionalCommissionFeeModel, Decimal, Realistic commission: ``rate_bps`` of trade notional per fill, floored. For FX…, Deterministic slippage by shifting the simulated order book away from best.…, The quote the most recent fill simulation used (for slippage accounting)., Return a book whose only levels sit ``ticks`` away from the touch., NautilusPaperExecutor (+22 more)

### Community 44 - "NautilusRouterStrategy"
Cohesion: 0.10
Nodes (15): NautilusRouterStrategy, datetime, Decimal, OrderAccepted, OrderDenied, OrderFilled, OrderRejected, OrderSubmitted (+7 more)

### Community 45 - "StrategyState"
Cohesion: 0.17
Nodes (23): PromotionAction, Strategy lifecycle (INV-8, architecture §16). There is no ``RD-Agent -> LIVE``…, Outcome of a promotion review (INV-8). Approval is never an LLM action., StrategyState, PromotionDecision, Strategy promotion contract: ``PromotionDecision`` (INV-8, Phase 10+).…, PaperEligibility, The only deterministic check used before requesting PAPER promotion. (+15 more)

### Community 46 - "LiveAutoStrategyRecord"
Cohesion: 0.08
Nodes (19): LIVE_AUTO governance (Phase 11): deterministic, operator-controlled promotion…, _decode_strategy(), _encode_strategy(), PostgresLiveAutoStore, Any, datetime, Decimal, UUID (+11 more)

### Community 47 - "MemoryRecord"
Cohesion: 0.06
Nodes (37): LayerPolicyError, A tier policy parameter is inconsistent (e.g. overlapping reach windows)., Graphiti adapter — Phase 3, temporal trading memory (ADR-0008, INV-3, INV-11).…, Domain-facing temporal memory (ADR-0008, INV-3) — the only query path.…, EntityType, StrEnum, The seventeen entity types of the trading ontology (architecture §11)., The eleven relations of the trading ontology (architecture §11). (+29 more)

### Community 48 - "test_command_center_api.py"
Cohesion: 0.09
Nodes (18): ensure_psycopg_dsn(), Force the psycopg (v3) SQLAlchemy dialect on PostgreSQL DSNs. The project pins…, client(), Connection, Engine, Any, datetime, TestClient (+10 more)

### Community 49 - "BaseContractModel"
Cohesion: 0.07
Nodes (47): BaseContractModel, BaseModel, Common configuration shared by all contracts and sub-models., Calibrator, DataScope, datetime, Calibration: learn fusion weights and confidence maps from labeled history…, All compositions of ``units`` into ``n_components`` non-negative parts, in… (+39 more)

### Community 50 - "SystemClock"
Cohesion: 0.05
Nodes (49): Mt4Endpoints, BaseModel, The three ZeroMQ channel addresses. Defaults are private loopback. Production…, NoSnapshotError, Decimal, RuntimeError, Raised when no point-in-time snapshot is available for a cycle., Snapshots from the sealed market-data repository (INV-3 choke point). (+41 more)

### Community 51 - "domain/__init__.py"
Cohesion: 0.13
Nodes (15): Domain layer: canonical enums and state machines (architecture §5-§18)., assert_valid_order_transition(), assert_valid_strategy_transition(), InvalidStateTransition, is_valid_order_transition(), is_valid_strategy_transition(), ValueError, Explicit state machines for the canonical lifecycles. The machines here are the… (+7 more)

### Community 52 - "EmergencyControlState"
Cohesion: 0.08
Nodes (18): DeadManSwitchState, EmergencyControlState, model_validator, Self, Persisted state of one emergency control (INV-7, architecture §10). Keyed by…, Persisted dead man switch state (singleton row in PostgreSQL).…, _control_values(), _dead_man_values() (+10 more)

### Community 53 - "make_bar"
Cohesion: 0.17
Nodes (10): datetime, Derive the point-in-time snapshot for the latest bar visible at ``as_of``.…, snapshot_from_bar(), make_bar(), _engine(), Unit tests: quality flags, duplicate handling, missing-bar detection., TestDuplicates, TestFlags (+2 more)

### Community 54 - "App.tsx"
Cohesion: 0.11
Nodes (23): get(), App(), CollectionPage(), Icon, money(), OverviewPage(), RecordSummary(), RiskPage() (+15 more)

### Community 55 - "market_data/pipeline.py"
Cohesion: 0.09
Nodes (32): bar_row_key(), Deterministic ordering key for bars., _group_bars(), MarketDataPipeline, _merge_gold_rows(), datetime, Medallion ingestion pipeline: RAW → BRONZE → SILVER → GOLD. -…, Build one immutable gold dataset version from all silver runs. Deterministic by… (+24 more)

### Community 56 - "test_invariants.py"
Cohesion: 0.11
Nodes (10): _effective_budget(), Decimal, parametrize, Critical invariants of the Risk Engine (DoD: no tested path bypasses limits). -…, The three blocking invariants: daily loss, stale data, disabled strategy., approved risk <= policy risk — for every decision type, exactly., approved quantity <= configured maximum (policy and instrument)., TestApprovedQuantityInvariant (+2 more)

### Community 57 - "LLMSignal"
Cohesion: 0.10
Nodes (36): EvalReport, evaluate(), evaluate_all(), fixture_to_mock_scenario(), fixture_to_request(), fixture_to_snapshot(), load_scenarios(), BaseModel (+28 more)

### Community 58 - "ScriptedRedis"
Cohesion: 0.13
Nodes (7): OperationalError, operational_error(), Any, Exception, A realistic PostgreSQL connectivity failure (server restart window)., Minimal faithful ``RedisConnection`` double for one RedisStreamBus. Streams and…, ScriptedRedis

### Community 59 - "evaluate_cases"
Cohesion: 0.29
Nodes (8): evaluate_cases(), datetime, Compare quant_only / llm_only / quant_plus_llm / baseline on ``cases``.…, _case(), make_config(), datetime, Research evaluation: Quant-only vs LLM-only vs Quant+LLM vs baseline., TestMandatoryComparison

### Community 60 - "CalibrationStore"
Cohesion: 0.11
Nodes (18): calibrate(), CalibrationArtifact, Any, Convenience wrapper around :class:`Calibrator`., Complete, versioned output of a calibration run. Everything needed to reproduce…, EvaluationReport, Full comparison of the mandatory configurations on one case set., CalibrationStore (+10 more)

### Community 61 - "make_risk_policy"
Cohesion: 0.17
Nodes (8): make_account_state(), make_risk_policy(), AccountState, datetime, Validation tests for the Risk & Policy contracts and the RESIZE decision shape., TestAccountState, TestRiskDecisionResize, TestRiskPolicy

### Community 62 - "Target Architecture — Autonomous Quantitative Trading & Research Platform"
Cohesion: 0.07
Nodes (28): 10. Point-in-Time rule (INV-3), 11. Data architecture (INV-10), 12. Event bus (INV-15), 13. Canonical domain objects (INV-2), 14. Signal Fusion (INV-16), 15. Post-trade learning loop, 16. Strategy lifecycle (INV-8), 17. LLM evaluation (+20 more)

### Community 63 - "Settings"
Cohesion: 0.10
Nodes (29): create_app(), CheckFunc, FastAPI, OperatorResolver, BaseSettings, field_validator, Live-mode secrets must be at least 32 characters: an empty or weak operator…, Settings (+21 more)

### Community 64 - "EmergencyController"
Cohesion: 0.08
Nodes (21): build_emergency_router(), APIRouter, OperatorResolver, build_provenance(), Convenience provenance builder shared by the execution engine., EmergencyController, Any, datetime (+13 more)

### Community 65 - "architecture.md"
Cohesion: 0.07
Nodes (27): 12. Regla Point-in-Time, 14. Event Bus, 15. Objetos de dominio canónicos, 16. Signal Fusion Engine, 17. Post-trade learning loop, 18. Strategy Factory, 1. Visión final, 20. Métricas obligatorias (+19 more)

### Community 66 - "build_memory"
Cohesion: 0.14
Nodes (10): build_memory(), datetime, Test helpers for the graphiti adapter (mirrors ta_test_helpers.py)., A ready-to-query :class:`adapters.graphiti.memory.Memory` over the in-memory…, Memory service tests: point-in-time retrieval, invalidation, contradictions,…, test_search_returns_domain_episodes(), TestContradictions, TestHistoricalQueries (+2 more)

### Community 67 - "risk_helpers.py"
Cohesion: 0.14
Nodes (32): AssetClass, PortfolioExposure, Pre-computed aggregate exposures of the current portfolio (engines/portfolio).…, build_account(), build_instrument(), build_policy(), build_portfolio(), build_portfolio_with_exposure() (+24 more)

### Community 68 - "5. Scenario playbooks"
Cohesion: 0.12
Nodes (16): 1. Objectives, 2. What is already built in, 3. Backups, 4. Restore, 5.1 Core crash mid-submit, 5.2 MT4 / broker unavailable, 5.3 Material divergence (unexpected broker position / quantity mismatch), 5.4 Postgres loss (volume corruption / deleted) (+8 more)

### Community 69 - "stages/posttrade.py"
Cohesion: 0.13
Nodes (25): ensure_secret_free(), Reject secret-like keys or credential values before a vault write., PostTradeReconciliationPendingError, PosttradeStage, Any, datetime, RuntimeError, UUID (+17 more)

### Community 70 - "KillScope"
Cohesion: 0.10
Nodes (17): ApprovalStatus, ApprovalStore, KillScope, _decode(), _encode(), PostgresApprovalStore, Any, datetime (+9 more)

### Community 71 - "signal_fusion/fusion.py"
Cohesion: 0.08
Nodes (31): DisagreementRecord, FusedSignal, model_validator, Self, Signal Fusion output (INV-16). Weights derive from historical calibration,…, One recorded conflict between directional inputs and the policy applied…, FusionConfigurationError, FusionError (+23 more)

### Community 72 - "PositionSnapshot"
Cohesion: 0.11
Nodes (13): _OpenPosition, PositionLedger, Decimal, OrderFilled, PositionChanged, PositionClosed, PositionOpened, Account-currency equity: quote cash + base cash at mid + unrealized. (+5 more)

### Community 73 - "schemas/__init__.py"
Cohesion: 0.07
Nodes (30): EventRegistry, ValueError, Event registry: canonical event names → payload contract classes (architecture…, Raised when an event name has no registered payload contract., Immutable name → payload contract registry used by producers and consumers., UnknownEventError, DomainObject, Any (+22 more)

### Community 74 - "32. Roadmap definitivo"
Cohesion: 0.08
Nodes (26): 32. Roadmap definitivo, Definition of Done, Definition of Done, Definition of Done, Definition of Done, Definition of Done, Definition of Done, Definition of Done (+18 more)

### Community 75 - "OrderType"
Cohesion: 0.06
Nodes (49): build_parser(), _collect_events(), main(), ArgumentParser, Command-line entrypoints for the MT4 execution protocol (Phase 6). - ``run`` —…, Full lifecycle against the emulator over real loopback ZeroMQ sockets., run_emulator(), run_smoke() (+41 more)

### Community 76 - "factories.py"
Cohesion: 0.25
Nodes (32): make_dead_man_switch_state(), make_domain_event(), make_emergency_control_state(), make_emergency_event(), make_execution_quality(), make_execution_report(), make_experiment_run(), make_factor_candidate() (+24 more)

### Community 77 - "TokenUsageCollector"
Cohesion: 0.12
Nodes (13): Any, datetime, UUID, Duck-typed LangChain callback handler accumulating token usage. Deliberately…, Called by LangChain after each LLM generation completes., Trace the real provider invocation without exporting prompt contents., LangChain callback: start a Langfuse tool observation., Execute the upstream committee for ``request`` and return a signal. Fails… (+5 more)

### Community 78 - "FusionConfig"
Cohesion: 0.09
Nodes (17): paper_fusion_config(), Default calibrated fusion config for the paper pipeline. Equal weights over the…, _default_fusion(), ComponentWeights, FusionConfig, model_validator, Self, Deterministic fusion configuration. - ``default_weights``: calibrated weights… (+9 more)

### Community 79 - "redact"
Cohesion: 0.11
Nodes (18): Security primitives for trust-zone enforcement (architecture §29, ADR-0025). -…, _attach_filter(), install_redacting_logging(), Log redaction — secrets must never reach logs (architecture §29, ADR-0025).…, Return ``text`` with every known secret pattern masked (``None`` → ``""``)., Masks secret patterns on the record itself, before any handler renders.…, Formatter that masks secret patterns (including exception text)., Install redaction process-wide: filter + redacting std handler. Idempotent… (+10 more)

### Community 80 - "nautilus/__init__.py"
Cohesion: 0.10
Nodes (39): build_config(), main(), Deterministic backtest CLI: prints the reproducibility fingerprints. Usage: uv…, BacktestConfig, BaselineSmaConfig, CommissionConfig, BaseModel, datetime (+31 more)

### Community 81 - "nautilus/engine.py"
Cohesion: 0.13
Nodes (24): code_sha(), Decimal, Venue, The BACKTEST runner: Nautilus ``BacktestEngine`` + virtual clock + domain…, Authoritative balances as tracked by the Nautilus venue (for cross-checks)., Git HEAD SHA of the repository, or the adapter version outside a repo. The code…, compute_metrics(), EquityPoint (+16 more)

### Community 82 - "compilerOptions"
Cohesion: 0.08
Nodes (23): compilerOptions, allowJs, allowSyntheticDefaultImports, esModuleInterop, forceConsistentCasingInFileNames, isolatedModules, jsx, lib (+15 more)

### Community 83 - "OrderState"
Cohesion: 0.26
Nodes (30): DiscrepancyCode, OrderState, Canonical order lifecycle (INV-6, architecture §8)., Broker reconciliation discrepancy codes (INV-6, architecture §9). Severity is…, get_order(), make_broker_view(), make_venue_view_position(), _live_order() (+22 more)

### Community 84 - "test_versioning.py"
Cohesion: 0.12
Nodes (26): deserialize_event(), Any, Deserialize and fully validate an envelope (including its payload contract).…, Event layer: registry, payload versioning, standard envelope (INV-15)., _market_snapshot_0100_to_100(), _market_snapshot_090_to_0100(), Any, ValueError (+18 more)

### Community 85 - "strategy.py"
Cohesion: 0.19
Nodes (18): BaselineSmaStrategy, datetime, Decimal, Domain-side strategy contract and the minimal deterministic baseline. The…, What a domain strategy may see at one bar (point-in-time, INV-3). Nothing…, Minimal deterministic baseline: SMA crossover, long-only, market orders. - LONG…, StrategyContext, _config() (+10 more)

### Community 87 - "Agent details"
Cohesion: 0.10
Nodes (19): Agent details, Agent index, AI Engineering Team Architecture — OpenTrading, ai-trading-systems, backend-platform, command-center, execution-mt4, Hard boundary (+11 more)

### Community 88 - "3. Classification against the requested axes"
Cohesion: 0.10
Nodes (19): 1. Snapshot facts (repository evidence), 2. Complete repository inventory, 3.10 Tests, 3.11 Configuration, 3.12 Secrets handling, 3.1 Existing trading code, 3.2 Experimental code, 3.3 Duplicated code (+11 more)

### Community 89 - "TestExposureResize"
Cohesion: 0.31
Nodes (3): _portfolio(), Decimal, TestExposureResize

### Community 90 - "test_live_infra_restart.py"
Cohesion: 0.32
Nodes (9): _compose(), _docker_available(), live_chaos(), _postgres_up(), fixture, Real container restarts (docker-gated; opt-in). These scenarios actually…, settings(), TestLiveRestarts (+1 more)

### Community 91 - "test_registry.py"
Cohesion: 0.28
Nodes (25): decision_for(), enabled_config(), intent_for(), make_registry(), price(), promote(), datetime, Decimal (+17 more)

### Community 92 - "LiveAutoRegistry"
Cohesion: 0.14
Nodes (15): LiveAutoViolation, RuntimeError, An automated order or a governance action violates LIVE_AUTO policy., _audit_metadata(), LiveAutoRegistry, Any, Normalize values into JSON-serializable audit metadata., Deterministic governance authority for LIVE_AUTO execution. (+7 more)

### Community 93 - "5. Controls"
Cohesion: 0.09
Nodes (22): 1. Trust zones, 2. Assets, 3. Threat actors, 4. Threat register, 5. Controls, 6. Definition of Done — traceability, 7. Residual risks, C10 — Emergency controls (INV-7) (+14 more)

### Community 95 - "Architecture Invariants"
Cohesion: 0.11
Nodes (17): Architecture Invariants, INV-10 — Data stores are separated by purpose, INV-11 — Graphify ≠ Graphiti, INV-12 — Frozen decisions require ADRs, INV-13 — Two runtimes, never merged, INV-14 — Dependencies are pinned, INV-15 — Domain events use the standard envelope, INV-16 — Signal Fusion weights are calibrated, not arbitrary (+9 more)

### Community 96 - "VirtualClock"
Cohesion: 0.06
Nodes (57): MockTradingAgentsAdapter, Scenario-driven stand-in for the upstream committee. Scenario lookup: exact…, Protocol, SnapshotSource, Deterministic simulation clock. Time only advances through explicit…, VirtualClock, get_settings(), Process-wide settings singleton. (+49 more)

### Community 97 - "OperationalMetrics"
Cohesion: 0.05
Nodes (30): _tool_metric_name(), CollectorRegistry, Vendor-specific telemetry adapters with safe no-op defaults., OperationalMetrics, Bounded-cardinality Prometheus metrics for the trading runtime., Own all application metrics so tests can use an isolated registry., deterministic_trace_id(), LangfuseTracer (+22 more)

### Community 98 - "Instrument"
Cohesion: 0.09
Nodes (36): _instrument_from_row(), Any, DatasetConfig, Deterministic historical dataset: synthetic (seeded) or parquet replay., build_dataset(), Dataset, _hash_rows(), load_parquet_dataset() (+28 more)

### Community 99 - "Guía Completa de Instalación y Uso — OpenTrading"
Cohesion: 0.07
Nodes (26): 10.1 LIVE_GATED — aprobación humana por operación, 10.2 LIVE_AUTO — gobernanza determinista sin aprobación por operación, 10.3 Controles de emergencia y dead man switch (INV-7), 10. Modos LIVE_GATED y LIVE_AUTO (cuenta demo), 11. Quant R&D (fábrica de estrategias), 12. Observabilidad: métricas, trazas y paneles, 13. Operación diaria y recuperación, 14. Configuración de referencia (+18 more)

### Community 100 - "Operations Manual — OpenTrading"
Cohesion: 0.18
Nodes (10): 1. Operating modes (INV-8), 2. Daily runbook — development / staging, 3. Live operations (LIVE_GATED), 4. Emergency control system (INV-7), 5. Reconciliation (INV-6 — mandatory), 6. Monitoring & alerting, 7. Maintenance tasks, 8. Troubleshooting quick map (+2 more)

### Community 101 - "test_live_auto_api.py"
Cohesion: 0.20
Nodes (17): LiveAutoConfig, Configuration for LIVE_AUTO governance (Phase 11). ``LiveAutoConfig`` mirrors…, Fail closed unless the capability is on AND every limit is explicit., test_disabled_or_partial_config_fails_closed_on_runtime_wiring(), app_with(), authenticated_operator(), make_registry(), promotion_body() (+9 more)

### Community 102 - "Known Limitations — OpenTrading"
Cohesion: 0.20
Nodes (9): Documentation & repository, Execution & venues, Infrastructure & observability, Known Limitations — OpenTrading, Performance, Resolution policy, Risk & fusion, Security (+1 more)

### Community 103 - "EvaluationResult"
Cohesion: 0.18
Nodes (7): EvaluationResult, Any, BaseModel, Protocol, QlibBackend, Qlib result mapper; Qlib classes never enter the canonical domain., Typed Qlib evaluation boundary for the Python 3.11 research runtime.

### Community 104 - "_build_platform_with_poison"
Cohesion: 0.21
Nodes (6): _build_platform_with_poison(), Six M1 bars at 10:00…10:05 plus deliberately planted future information: - a…, Absolute invariant: no returned bar has available_time > as_of., bars/snapshot require as_of; there is no bypass method., TestApiLeakage, TestRepositoryLeakage

### Community 105 - "StageWorker"
Cohesion: 0.06
Nodes (21): MirroringEventBus, Any, Bus proxy that mirrors only after authoritative publish succeeds. Export errors…, Mirror an already-authoritative event (used by synchronous runs)., Reclaim stale PEL entries; dead-letter poisoned ones. Returns the reclaimed…, Dispatch one message; ACK on success, leave unacked on failure. Stages publish…, One pass: recover, then read+dispatch new messages. Returns (reclaimed,…, One consumer group: recovery loop + new-message loop (unattended). (+13 more)

### Community 106 - "OrderRejectionSim"
Cohesion: 0.15
Nodes (11): OrderRejectionSim, datetime, Decimal, Deterministic simulated-venue order rejection (ADR-0007: rejection simulation).…, Deterministic rejection rule chain evaluated per ``OrderIntent``., Return a rejection reason, or ``None`` when the order may proceed., CurrencyPair, DomainStrategy (+3 more)

### Community 107 - "NativeRDAgentQlibBackend"
Cohesion: 0.26
Nodes (4): NativeRDAgentQlibBackend, Any, Concrete bridge to RD-Agent 0.8.0's Qlib factor/model loops. All imports of…, Drive one official RD-Agent hypothesis/code/run cycle at a time.

### Community 108 - "signals.py"
Cohesion: 0.19
Nodes (14): CommitteeMember, Signal contracts: ``QuantSignal``, ``LLMSignal``, ``FusedSignal``., One analyst in the TradingAgents qualitative committee (Phase 2+)., _imports_in(), AST, Path, Boundary contract tests: TradingAgents can disappear entirely. These tests…, (node, module-name) for every import in a file, with module context. (+6 more)

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

### Community 113 - "command_center.py"
Cohesion: 0.16
Nodes (14): SQLAlchemy Core table definitions for the market data catalog. PostgreSQL is…, build_command_center_router(), CommandCenterDataSource, _json(), PostgresCommandCenterDataSource, Any, APIRouter, datetime (+6 more)

### Community 114 - "MarketSnapshot"
Cohesion: 0.12
Nodes (17): BaselineQuantProducer, _episode_stance(), MemoryContextProducer, datetime, UUID, Signal producers for the research stage (Phase 7). -…, Deterministic momentum quant signal from a single snapshot. ``strength`` scales…, Distills point-in-time memory episodes into a directional stance. Only episodes… (+9 more)

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
Cohesion: 0.07
Nodes (36): NautilusBacktestRunner, Runs one BACKTEST with the Nautilus simulated venue (virtual clock)., input_fingerprint(), _fills(), Cost-model tests: commission, spread, slippage are real and applied (skill:…, test_commission_is_applied_per_fill(), test_partial_fill_status_never_claimed_for_single_fill_orders(), test_slippage_applied_and_tracked() (+28 more)

### Community 119 - "make_intent"
Cohesion: 0.19
Nodes (24): ExecutionDivergenceError, RuntimeError, A venue report contradicts authoritative state in a capital-relevant way., make_intent(), _candidate(), fixture, OrderStateApplier DoD tests: full canonical lifecycle, crash-restart state,…, A fresh engine over the same store sees exactly the persisted state. (+16 more)

### Community 120 - "SequenceTracker"
Cohesion: 0.27
Nodes (4): Record a newly accepted sequence (must equal expected)., Per-namespace last-accepted sequences (reconciliation payload)., Strict monotonic sequence validation per ``strategy_id`` namespace. Sequences…, SequenceTracker

### Community 121 - "infra_health.py"
Cohesion: 0.10
Nodes (16): datetime, timedelta, Current time as timezone-aware UTC., Move forward by ``delta`` (strictly positive) and return the new time., Jump to ``moment``; moving backwards is refused (monotonic simulation time)., main(), probe_http(), probe_minio() (+8 more)

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

### Community 143 - "_WindowBlindStore"
Cohesion: 0.14
Nodes (5): FakeGraph, Any, Deliberately broken backend: ignores the temporal window and returns every…, Upstream graph double: records add_episode calls, returns queued edges., _WindowBlindStore

### Community 144 - "19. Validation Factory"
Cohesion: 0.22
Nodes (9): 19. Validation Factory, Backtest básico, Monte Carlo, Multiple-testing protection, Out-of-sample, Purged/embargo validation, Regime testing, Sensitivity (+1 more)

### Community 145 - "MarketDataRepository"
Cohesion: 0.11
Nodes (16): MarketDataRepository, PointInTimeFilter, datetime, Bars of a sealed dataset visible at ``as_of`` (INV-3 filter applied).…, Point-in-time snapshot from the latest bar visible at ``as_of``. Returns…, The single INV-3 choke point. Dropping logic in exactly one place makes the…, Read-only query API over sealed gold dataset versions., build_market_data_router() (+8 more)

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

### Community 185 - "test_posttrade_notes.py"
Cohesion: 0.13
Nodes (18): FileVaultWriter, Path, Filesystem vault writer (UTF-8, parent directories created as needed)., _fmt(), note_path(), datetime, UUID, Human-readable Obsidian note rendering (architecture §25). Deterministic… (+10 more)

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

### Community 194 - "SignalDirection"
Cohesion: 0.16
Nodes (13): SignalDirection, Random, _case(), _noisy_llm_cases(), datetime, Calibration tests: LLM zeroing, regime-specific weights, determinism (INV-16)., Quant is 60% accurate; the LLM is pure noise., Quant is 55% accurate; the LLM is 90% accurate. (+5 more)

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

### Community 223 - "signal_fusion/config.py"
Cohesion: 0.16
Nodes (13): ConfidenceMap, DisagreementPolicy, MissingSignalPolicy, StrEnum, Fusion configuration: component weights, policies and confidence maps (INV-16).…, Map one raw confidence through the calibrated curve., How conflicting directional inputs are resolved (INV-16)., How absent inputs are handled (INV-16). (+5 more)

### Community 224 - "build_domain_event"
Cohesion: 0.17
Nodes (16): build_domain_event(), datetime, UUID, Envelope construction, serialization and validation (INV-15)., Build a standard envelope around a validated canonical payload. The payload…, Deterministic UTF-8 bytes for the event bus., serialize_event(), parametrize (+8 more)

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

### Community 231 - "test_adapter_boundary.py"
Cohesion: 0.17
Nodes (13): _imports_in(), AST, MonkeyPatch, Path, Boundary contract tests: Graphiti can disappear entirely. These tests enforce…, (node, module-name) for every import in a file, with module context., Whether ``node`` sits inside a function definition (lazy import seam)., Block any import of the ``graphiti_core`` top-level package. (+5 more)

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

### Community 241 - "Stack"
Cohesion: 0.10
Nodes (41): EmergencyBody, BaseModel, EmergencyLevel, The four emergency-control levels (INV-7, architecture §10). Semantics frozen…, EmergencyPolicy, Configuration of the emergency control system (never changeable by LLMs)., Wire the whole engine together over one store (tests inject doubles)., Stack (+33 more)

### Community 242 - "PostgresAuditSink"
Cohesion: 0.18
Nodes (10): AuditEntry, AuditSink, Any, Protocol, UUID, One immutable audit record., Audit layer: immutable, clock-stamped action records., PostgresAuditSink (+2 more)

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

### Community 268 - ".__init__"
Cohesion: 0.14
Nodes (9): PendingOrderCanceller, PositionFlattener, Protocol, Callable that closes every open position (``OPTIONALLY_FLATTEN``)., Callable that cancels every still-live order (``CANCEL_PENDING``)., AlertSink, Protocol, Operational alert fan-out (log, pager, webhook — transport later). (+1 more)

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

### Community 345 - "RiskReasonCode"
Cohesion: 0.09
Nodes (9): Canonical decision reason codes (architecture §7 controls, ADR-0018). Used both…, RiskReasonCode, TestStrategyState, Boundary tests: exactly-at-limit behavior with exact Decimal arithmetic.…, TestCountBoundaries, TestLeverageMarginBoundary, TestRiskBoundary, TestSizeBoundaries (+1 more)

### Community 346 - "ExecutionService"
Cohesion: 0.12
Nodes (12): LiveExecutionRuntime, Deterministic dead man evaluation (safe to call on a cadence)., ExecutionService, datetime, UUID, Owns the submit path and the restart reconciliation procedure., Run the intent through the gates, persist before send, apply reply., Apply pushed venue events. Divergences escalate to SAFE_MODE. (+4 more)

### Community 347 - ".from_episode"
Cohesion: 0.21
Nodes (4): datetime, Map a domain :class:`MemoryEpisode` to the stored envelope. ``source`` /…, Point-in-time truth: the system could know this item at ``moment`` only if it…, TestMemoryRecordEnvelope

### Community 349 - "assert_llm_process_cannot_execute"
Cohesion: 0.19
Nodes (8): assert_llm_process_cannot_execute(), ExecutionBoundaryViolation, RuntimeError, Process-level trust-zone enforcement (architecture §29, INV-1, INV-9,…, An LLM-facing process attempted to cross into the execution zone (INV-1)., Fail closed if an LLM-facing process is started in an execution mode. Must be…, MonkeyPatch, TestLlmProcessZoneGuard

### Community 352 - "test_live_auto.py"
Cohesion: 0.50
Nodes (12): _intent(), _price(), _promoted(), LIVE_AUTO execution-path tests (Phase 11). Proves the automated path: a…, _registry(), _service(), test_automated_order_requires_no_human_approval_and_is_persisted(), test_automated_order_without_risk_decision_fails_closed() (+4 more)

### Community 353 - "test_infra_smoke.py"
Cohesion: 0.35
Nodes (11): integration, _infra_up(), fixture, Integration smoke tests against the local docker-compose stack. Run ``make up``…, require_infra(), settings(), test_falkordb_responds_and_graph_module_loaded(), test_minio_expected_buckets_exist() (+3 more)

### Community 354 - "live_auto.py"
Cohesion: 0.24
Nodes (9): build_live_auto_router(), DemotionBody, PnlBody, PromotionBody, APIRouter, BaseModel, OperatorResolver, Authenticated operator API for LIVE_AUTO governance (Phase 11). Every mutation… (+1 more)

### Community 355 - "test_settings.py"
Cohesion: 0.27
Nodes (9): _clear_settings_cache(), fixture, MonkeyPatch, Settings tests: env-var overrides and enum validation., test_defaults(), test_env_prefix(), test_get_settings_is_cached(), test_invalid_mode_rejected() (+1 more)

### Community 358 - "test_end_to_end.py"
Cohesion: 0.43
Nodes (6): build_request_from_snapshot(), End-to-end contract: MarketSnapshot → ResearchRequest → TradingAgents →…, The canonical first hop of the DoD chain: MarketSnapshot → ResearchRequest., test_e2e_replay_is_deterministic_with_the_mock(), test_end_to_end_has_no_execution_capability_whatsoever(), test_market_snapshot_to_research_request_to_llmsignal()

## Knowledge Gaps
- **1036 isolated node(s):** `Canonical sources of truth`, `Target repository layout (architecture §27 — created in Phase 0)`, `Key facts for agents`, `Domain glossary`, `INV-1 — Intelligence is never authority over capital` (+1031 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **77 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `SignalDirection` connect `SignalDirection` to `enums.py`, `DomainEvent`, `TradeLifecycle`, `make_market_snapshot`, `TradeProposal`, `mapping.py`, `FusionInputs`, `mapper.py`, `PaperLedger`, `test_contracts.py`, `test_paper_contracts.py`, `analysis.py`, `PostTradeReviewRecord`, `test_posttrade_integration.py`, `test_client.py`, `domain/__init__.py`, `market_data/pipeline.py`, `LLMSignal`, `test_posttrade_notes.py`, `evaluate_cases`, `CalibrationStore`, `risk_helpers.py`, `stages/posttrade.py`, `signal_fusion/fusion.py`, `schemas/__init__.py`, `factories.py`, `signal_fusion/config.py`, `test_end_to_end.py`, `signals.py`, `Any`, `MarketSnapshot`, `NautilusBacktestRunner`?**
  _High betweenness centrality (0.036) - this node is a cross-community bridge._
- **Why does `OrderIntent` connect `enums.py` to `Mt4Emulator`, `DomainEvent`, `protocol.py`, `mapping.py`, `OrderRecord`, `PaperLedger`, `InMemoryExecutionStateStore`, `make_order_intent`, `OperatingMode`, `test_paper_ledger.py`, `NautilusPaperExecutor`, `NautilusRouterStrategy`, `SystemClock`, `model_validator`, `EmergencyController`, `schemas/__init__.py`, `OrderType`, `factories.py`, `OrderState`, `strategy.py`, `ExecutionService`, `LiveAutoRegistry`, `OrderRejectionSim`, `test_paper_executor.py`, `make_intent`?**
  _High betweenness centrality (0.033) - this node is a cross-community bridge._
- **Why does `Instrument` connect `Instrument` to `make_order_intent`, `DomainEvent`, `risk_helpers.py`, `worker/cli.py`, `PositionSnapshot`, `mapping.py`, `OrderRejectionSim`, `NautilusPaperExecutor`, `repository.py`, `schemas/__init__.py`, `TradeProposal`, `factories.py`, `nautilus/__init__.py`, `nautilus/engine.py`, `MarketSnapshot`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Are the 45 inferred relationships involving `VirtualClock` (e.g. with `_long_adapter()` and `_snapshot_event()`) actually correct?**
  _`VirtualClock` has 45 INFERRED edges - model-reasoned connections that need verification._
- **Are the 81 inferred relationships involving `Stack` (e.g. with `TestPostgresRestart` and `_service()`) actually correct?**
  _`Stack` has 81 INFERRED edges - model-reasoned connections that need verification._
- **Are the 83 inferred relationships involving `SignalDirection` (e.g. with `trade_outcome_from_position_closed()` and `build_committee()`) actually correct?**
  _`SignalDirection` has 83 INFERRED edges - model-reasoned connections that need verification._
- **Are the 40 inferred relationships involving `Clock` (e.g. with `Memory` and `MarketDataPipeline`) actually correct?**
  _`Clock` has 40 INFERRED edges - model-reasoned connections that need verification._