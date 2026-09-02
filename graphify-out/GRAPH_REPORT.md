# Graph Report - OpenTrading  (2026-09-02)

## Corpus Check
- 571 files · ~235,810 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 6683 nodes · 18354 edges · 386 communities (285 shown, 101 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 1674 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `88b8c994`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- schemas/execution.py
- protocol.py
- DomainEvent
- TradeLifecycle
- OperatingMode
- VirtualClock
- SystemClock
- MarketSnapshot
- execution_helpers.py
- worker/cli.py
- repository.py
- evaluate
- SignalDirection
- KillScope
- PostTradeReviewRecord
- FusionInputs
- LiveGraphitiStore
- OrderRecord
- mapper.py
- OrderType
- Clock
- Settings
- FakeReconcileClient
- TierPolicy
- SimulatedBroker
- make_submit
- calibration.py
- mapping.py
- Provenance
- Timeframe
- test_export.py
- normalization.py
- OrderIntent
- make_memory_episode
- LayerName
- test_validation_factory.py
- devDependencies
- NautilusBacktestRunner
- tradingagents/client.py
- factories.py
- PositionSide
- enums.py
- EmergencyControlState
- EmergencyController
- Stack
- make_record
- nautilus/__init__.py
- test_command_center_api.py
- LiveAutoRegistry
- Validity
- synthetic_dataset
- make_order_intent
- MemoryRecord
- make_market_snapshot
- schemas/memory.py
- market_data/pipeline.py
- export.py
- bootstrap.py
- test_hashing.py
- ConfigurableSlippageFillModel
- ExperimentRun
- test_client.py
- App.tsx
- MemoryCatalog
- NautilusRouterStrategy
- evaluator.py
- redact
- make_bar
- OrderState
- InvalidStateTransition
- test_protocol.py
- Bar
- MarketDataRepository
- Target Architecture — Autonomous Quantitative Trading & Research Platform
- service.py
- nautilus/engine.py
- PositionLedger
- architecture.md
- test_workflows.py
- OperationalMetrics
- test_live_auto_api.py
- StrategyState
- test_versioning.py
- Guía Completa de Instalación y Uso — OpenTrading
- build_domain_event
- TestStrategyState
- CalibrationStore
- test_registry.py
- make_intent
- ScriptedRedis
- test_invariants.py
- compilerOptions
- 5. Controls
- test_process_crash.py
- StageWorker
- LangfuseTracer
- test_boundary.py
- TestWorkerHasNoExecutionCapability
- PortfolioExposure
- Agent details
- 3. Classification against the requested axes
- test_resize.py
- strategy.py
- TokenUsageCollector
- test_readyz.py
- schemas/__init__.py
- SafeModeViolation
- obsidian/__init__.py
- ._require_calibrated_version
- datetime
- Instrument
- Architecture Invariants
- MinioArtifactStore
- 5. Scenario playbooks
- test_property_based.py
- RepositorySnapshotSource
- ConnectionHealth
- EvaluationResult
- test_adapter_boundary.py
- 26. Command Center
- 32. Roadmap definitivo
- test_live_infra_restart.py
- FakeGraph
- MemoryStore
- NativeRDAgentQlibBackend
- Runbook — Infrastructure
- create_app
- Phase 0 — Foundations: Implementation Record
- MirroringEventBus
- test_paper_executor.py
- _FlakyConnection
- Domain Glossary (OpenTrading)
- Detail
- Product
- SequenceTracker
- Task Routing Workflow
- test_serialization.py
- Operations Manual — OpenTrading
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
- ADR/README.md
- 1. What was built
- Phase 5 — Deterministic Risk & Policy Engine (implementation record)
- Known Limitations — OpenTrading
- Runbook — Local Development
- FileVaultWriter
- 19. Validation Factory
- Runbook — Secrets management (SOPS + age)
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
- _validate_lineage
- Self
- AGENTS.md — OpenTrading (Codex & generic agent adapters)
- Quant R&D Runtime Specification
- infra_health.py
- OpenTrading — GitHub Copilot instructions
- adapters/graphiti — temporal semantic memory (Phase 3)
- RDAgentBackend
- adapters/tradingagents — TradingAgents behind a strict boundary (ADR-0004)
- .snapshot_for
- CLAUDE.md — OpenTrading (Claude Code adapter)
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
- Production Readiness — OpenTrading
- Runbook — Autonomous PAPER pipeline
- LiveExecutionRuntime
- mt4/config.py
- engines/signal_fusion — Signal Fusion Engine (Phase 7, INV-16)
- OpenTrading — GitHub Copilot instructions
- Postmortem — EURUSD LONG
- adapters/mt4 — MT4 execution protocol (Phase 6, ADR-0020)
- adapters/nautilus — NautilusTrader event-driven backtest engine (ADR-0007)
- Research context — $instrument_id @ $as_of
- AGENTS.md — OpenTrading (Codex & generic agent adapters)
- Repository Map (OpenTrading)
- Definition of Done
- initialize_vault
- Routing Rules — OpenTrading
- 10. Kill switch y Dead Man Switch
- Inspiración FinMem
- 13. Arquitectura de datos
- 8. MetaTrader 4: solamente capa de ejecución
- Phase 7 — Execution state: broker reconciliation & Safe Mode (implemented)
- engines/risk — Deterministic Risk & Policy Engine (Phase 5)
- _Bus
- WireGuard — private transport for remote Windows MT4 deployments
- ._check_validity
- OpenTrading — Autonomous Quantitative Trading & Research Platform
- tests/conftest.py
- test_import_guard.py
- Cross-Review Rules
- apps/worker — Autonomous PAPER pipeline (Phase 7, ADR-0022)
- CLAUDE.md — OpenTrading (Claude Code adapter)
- agents/architect.md
- agents/backend.md
- ADR-0022: Autonomous PAPER pipeline — Redis Streams stages, idempotent run ledger, recovery semantics
- ADR-0023: Post-trade analysis & learning engine — deterministic postmortems with four sinks
- ADR-0024: Emergency control system — kill switches and dead man switch
- ADR-0025 — Security hardening milestone: trust zones, least privilege, secret lifecycle
- ADR-0026 — LIVE_AUTO governance: automated live trading, disabled by default
- 7. Risk Engine: componente más importante
- Phase 7 — Post-trade analysis & learning engine (ADR-0023)
- engines/posttrade — Post-trade analysis & learning engine (Phase 7, ADR-0023)
- mt4/ — MetaTrader 4 execution-only layer (Phase 6, INV-5)
- tests/chaos — dedicated chaos/recovery suite
- Trade — 2c7c2d4f-fec5-5bdb-a428-4ebde0e0f237
- Context Usage Rules
- ADR Template
- agents/database.md
- agents/devops.md
- Routing Validation — OpenTrading
- Strategy Validation Factory
- 0009_audit_trail_immutability.py
- Agent Output Standard
- Verification Review Report
- tsconfig.json
- agents/frontend.md
- ._check_envelope
- agents/performance.md
- 29. Seguridad
- 4. Qlib + RD-Agent: fábrica cuantitativa autónoma
- 5. NautilusTrader: columna vertebral del trading
- backup.sh
- restore.sh
- test-postgres-roles.sh
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
- 002-roles.sh
- postgres/README.md
- prometheus/README.md
- infra/README.md
- entrypoint-acl.sh
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
- agents/qa.md
- agents/reviewer.md
- .agentic/agents/security.md
- agents/ux-ui.md
- 20260829-165324/architect.md
- 20260829-165324/backend.md
- 20260829-165324/database.md
- 20260829-165324/devops.md
- 20260829-165324/frontend.md
- orchestrator.md
- 20260829-165324/performance.md
- 20260829-165324/POLICY.md
- 20260829-165324/qa.md
- 20260829-165324/reviewer.md
- 20260829-165324/security.md
- seo.md
- 20260829-165324/ux-ui.md
- .agentic/POLICY.md

## God Nodes (most connected - your core abstractions)
1. `VirtualClock` - 172 edges
2. `Stack` - 158 edges
3. `SignalDirection` - 134 edges
4. `evaluate()` - 134 edges
5. `Clock` - 105 edges
6. `OrderType` - 99 edges
7. `DomainEvent` - 97 edges
8. `OrderSide` - 95 edges
9. `Mt4ExecutionClient` - 95 edges
10. `Timeframe` - 95 edges

## Surprising Connections (you probably didn't know these)
- `test_trade_outcomes_are_internally_consistent()` --uses--> `SignalDirection`  [INFERRED]
  tests/backtest/test_position_accounting.py → core/domain/enums.py
- `test_rating_profile_covers_all_tiers()` --uses--> `SignalDirection`  [INFERRED]
  tests/unit/tradingagents/test_mapper.py → core/domain/enums.py
- `test_partial_fill_status_never_claimed_for_single_fill_orders()` --uses--> `ExecutionState`  [INFERRED]
  tests/backtest/test_costs.py → core/domain/enums.py
- `_record()` --uses--> `ApprovalRecord`  [INFERRED]
  apps/api/live_gated.py → engines/execution/live_gate.py
- `build_live_execution_runtime()` --uses--> `Mt4Settings`  [INFERRED]
  engines/execution/live_runtime.py → adapters/mt4/config.py

## Import Cycles
- None detected.

## Communities (386 total, 101 thin omitted)

### Community 0 - "schemas/execution.py"
Cohesion: 0.04
Nodes (43): ExecutionContract, model_validator, Self, Execution-state contracts: persistent order lifecycle, positions, broker…, One difference found between persisted state and live broker state., Result of one mandatory reconciliation pass (INV-6, §9)., Persisted SAFE_MODE state (singleton row in PostgreSQL)., Result of the mandatory startup reconciliation procedure. (+35 more)

### Community 1 - "protocol.py"
Cohesion: 0.06
Nodes (49): Core-side MT4 execution client (Phase 6, ADR-0020). The client is the Core's…, Poll one market quote (non-blocking by default); returns (symbol, quote)., Python MT4 emulator — the bridge's stand-in before real MetaTrader (Phase 6).…, is_retryable(), Mt4ErrorCode, Mt4ProtocolError, ProtocolErrorDetail, BaseModel (+41 more)

### Community 2 - "DomainEvent"
Cohesion: 0.04
Nodes (90): Any, UUID, Trade lifecycle transition helpers (Phase 7). All lifecycle mutations flow…, Move the trace's lifecycle to ``target`` if the canonical machine allows it.…, Apply a sequence of transitions in order (each CAS-guarded)., transition(), transition_chain(), PaperPipeline (+82 more)

### Community 3 - "TradeLifecycle"
Cohesion: 0.03
Nodes (55): _account_from_row(), _account_values(), _context_from_row(), InMemoryPipelineStore, _lifecycle_from_row(), _lifecycle_values(), PipelineStore, PostgresPipelineStore (+47 more)

### Community 4 - "OperatingMode"
Cohesion: 0.10
Nodes (40): build_live_gated_router(), DecisionBody, KillBody, APIRouter, BaseModel, OperatorResolver, Authenticated operator API for LIVE_GATED approval and emergency controls., Build the mutation API; callers must inject a real authentication dependency. (+32 more)

### Community 5 - "VirtualClock"
Cohesion: 0.05
Nodes (69): default_mock_scenario(), MockTradingAgentsAdapter, The built-in fallback: a balanced, evidence-carrying HOLD decision., Scenario-driven stand-in for the upstream committee. Scenario lookup: exact…, MockScenario, Deterministic scenario played back by :class:`MockTradingAgentsAdapter`., Protocol, SnapshotSource (+61 more)

### Community 6 - "SystemClock"
Cohesion: 0.04
Nodes (44): BusUnavailableError, _connection_factory(), InMemoryStreamBus, new_trace_id(), PendingMessage, Any, Protocol, RuntimeError (+36 more)

### Community 7 - "MarketSnapshot"
Cohesion: 0.05
Nodes (71): MarketSnapshot, Decimal, model_validator, Self, Point-in-time market state for one instrument (INV-3). ``as_of`` is the…, PortfolioState, Decimal, field_validator (+63 more)

### Community 8 - "execution_helpers.py"
Cohesion: 0.11
Nodes (28): PostgreSQL persistence for authoritative execution state (INV-6, §9). Four…, _collect(), _connect(), _drain_until(), partial_emulator(), fixture, Broker event chaos: partial fills and malformed event streams. Wire-level (real…, Captures every wire event the service drains — including the ones applied… (+20 more)

### Community 9 - "worker/cli.py"
Cohesion: 0.05
Nodes (56): NautilusPaperExecutor, PaperVenueConfig, BaseModel, CurrencyPair, One-shot Nautilus paper venue: OrderIntent + snapshot → ExecutionReports.…, Venue parameters for the Nautilus paper simulator. ``slippage_*`` and…, build_default_config(), _instrument() (+48 more)

### Community 10 - "repository.py"
Cohesion: 0.09
Nodes (33): Market data catalog: PostgreSQL-backed (ADR-0010) or in-memory. The catalog…, DatasetNotFoundError, DatasetNotSealedError, DatasetSealedError, DatasetVersionExistsError, FutureDataLeakageError, InstrumentResolutionError, MarketDataError (+25 more)

### Community 11 - "evaluate"
Cohesion: 0.04
Nodes (15): evaluate(), Evaluate a proposal against the baseline inputs with dict overrides.…, TestApproveVariants, TestBaselineApprove, TestBrokerState, TestLossControls, TestMarketDataFreshness, TestSchedule (+7 more)

### Community 12 - "SignalDirection"
Cohesion: 0.07
Nodes (51): Append one observed price point to the open position's path. Bounded…, The observed path for a (possibly closed) position., SignalDirection, Canonical per-trade metrics (architecture §17). Semantics (documented in…, TradeMetrics, AnalysisContext, AnalysisResult, analyze() (+43 more)

### Community 13 - "KillScope"
Cohesion: 0.10
Nodes (17): ApprovalStatus, ApprovalStore, KillScope, _decode(), _encode(), PostgresApprovalStore, Any, datetime (+9 more)

### Community 14 - "PostTradeReviewRecord"
Cohesion: 0.05
Nodes (47): PostTradeReviewRecord, model_validator, Self, Persisted canonical-metrics row (PostgreSQL, INV-10). One row per closed-and-…, artifact_key(), build_artifact(), datetime, UUID (+39 more)

### Community 15 - "FusionInputs"
Cohesion: 0.05
Nodes (63): FusionInputs, All fusion inputs for one instrument at one point in time. Any input may be…, Names of the inputs that are present, in canonical engine order., ComponentWeights, DisagreementPolicy, FusionConfig, Fusion configuration: component weights, policies and confidence maps (INV-16).…, Deterministic fusion configuration. - ``default_weights``: calibrated weights… (+55 more)

### Community 16 - "LiveGraphitiStore"
Cohesion: 0.05
Nodes (51): _installed_version(), LiveGraphitiStore, _load_upstream(), Any, UUID, Live Graphiti-over-FalkorDB store — the ONLY module allowed to import upstream.…, Close the underlying graph driver (idempotent)., Write one record into Graphiti. The full envelope is embedded in the episode… (+43 more)

### Community 17 - "OrderRecord"
Cohesion: 0.08
Nodes (25): OrderRecord, The single authoritative persisted record for one ``order_intent_id``. Keyed by…, OrderStateApplier, Decimal, UUID, Persist the canonical crossing object (INV-2) as ORDER_INTENT., Persist SUBMITTED **before** the wire send (crash-after-submit safety)., Apply a broker ACK. Late ACKs after fill/cancel/reject are no-ops. (+17 more)

### Community 18 - "mapper.py"
Cohesion: 0.07
Nodes (49): A domain input could not be translated to upstream, or an upstream output could…, TradingAgentsMappingError, build_committee(), _coerce_datetime(), _context_template(), infer_stance(), now_utc(), parse_rating() (+41 more)

### Community 19 - "OrderType"
Cohesion: 0.06
Nodes (65): build_parser(), _collect_events(), main(), ArgumentParser, Command-line entrypoints for the MT4 execution protocol (Phase 6). - ``run`` —…, Full lifecycle against the emulator over real loopback ZeroMQ sockets., run_emulator(), run_smoke() (+57 more)

### Community 20 - "Clock"
Cohesion: 0.04
Nodes (70): get_mt4_settings(), Process-wide MT4 settings singleton (matching core get_settings)., Authenticated operator API for the emergency control system (INV-7). Mounts…, OpenTrading API service (core runtime, Python 3.12). Operational endpoints: -…, AuditEntry, AuditLogger, AuditSink, InMemoryAuditSink (+62 more)

### Community 21 - "Settings"
Cohesion: 0.07
Nodes (42): check_falkordb(), check_minio(), check_postgres(), check_redis(), Connect to PostgreSQL and run ``SELECT 1``., PING Redis (cache / locks / streams)., PING FalkorDB (speaks RESP, so the Redis client works)., Verify MinIO is reachable and the readiness bucket exists. (+34 more)

### Community 22 - "FakeReconcileClient"
Cohesion: 0.14
Nodes (35): FakeReconcileClient, make_reconciliation_response(), not_connected_error(), Implements the service's ReconcileClient protocol without any sockets., fixture, ExecutionService DoD tests: the 7-step startup reconciliation and the write-…, send_order() raised — the SUBMITTED record survives the 'crash' and the next…, Two genuinely distinct full-size fills exceed requested → SAFE_MODE. (+27 more)

### Community 23 - "TierPolicy"
Cohesion: 0.15
Nodes (9): datetime, timedelta, Derive the tier from metadata only: validity span, importance, hints. - open-…, Decay half-life per tier; long-term knowledge does not decay., Relevance multiplier in [0, 1] for knowledge of age ``at - available_time``., Whether the tier policy still surfaces this record at ``at``. Long-term…, Deterministic tier classification, relevance decay and reach windows., TierPolicy (+1 more)

### Community 24 - "SimulatedBroker"
Cohesion: 0.07
Nodes (31): BrokerOutcome, AccountState, datetime, Decimal, UUID, _quote(), QuoteEngine, Deterministic simulated broker for the MT4 emulator (Phase 6, ADR-0020). The… (+23 more)

### Community 25 - "make_submit"
Cohesion: 0.08
Nodes (55): BrokerConfig, BaseModel, model_validator, Broker-side symbol constraints the EA enforces before sending orders., Configuration of the simulated venue., SymbolSpec, CommandGate, Validates incoming commands: expiry → duplicates → sequence. (+47 more)

### Community 26 - "calibration.py"
Cohesion: 0.04
Nodes (75): calibrate(), Calibrator, DataScope, Any, datetime, Calibration: learn fusion weights and confidence maps from labeled history…, All compositions of ``units`` into ``n_components`` non-negative parts, in…, Deterministic calibration from labeled cases (INV-16). (+67 more)

### Community 27 - "mapping.py"
Cohesion: 0.07
Nodes (41): Domain-side position accounting that mirrors the Nautilus venue ledger.…, _decimal(), provenance(), datetime, OrderAccepted, OrderDenied, OrderFilled, OrderRejected (+33 more)

### Community 28 - "Provenance"
Cohesion: 0.08
Nodes (27): FillApplication, LedgerPosition, PaperLedger, AccountState, datetime, Decimal, UUID, Paper ledger: authoritative position & account accounting for the PAPER venue… (+19 more)

### Community 29 - "Timeframe"
Cohesion: 0.10
Nodes (39): Nearest canonical timeframe for a cycle interval (synthetic bars)., timeframe_for_interval(), Timeframe, Leakage tests: future information must be impossible to retrieve (INV-3). Phase…, DoD: (instrument X, dataset version Y, as_of T) → same hash, always., TestDeterministicDoD, TestImmutabilityLeakage, ingest_and_seal() (+31 more)

### Community 30 - "test_export.py"
Cohesion: 0.19
Nodes (13): ObsidianExporter, Render selected canonical events into deterministic Markdown notes., MemoryVaultWriter, Deterministic in-memory writer (unit tests, dev)., _BrokenExporter, _event(), parametrize, test_export_event_writes_marked_note_with_canonical_and_trace_ids() (+5 more)

### Community 31 - "normalization.py"
Cohesion: 0.07
Nodes (24): NormalizationError, A raw payload could not be mapped to a normalized record., BarPayloadMapper, build_bar_from_payload(), _epoch_to_utc(), normalize_timestamp(), parse_timeframe(), Any (+16 more)

### Community 32 - "OrderIntent"
Cohesion: 0.17
Nodes (9): OrderIntent, The only canonical object that crosses the system (INV-2). Never ``MT4Order``.…, ApprovalRecord, HumanApprovalGate, UUID, State machine and cryptographic verifier for human-gated live orders., Second boundary check used by the MT4 client immediately before send., Atomically verify and consume approval immediately before wire transmission. (+1 more)

### Community 33 - "make_memory_episode"
Cohesion: 0.10
Nodes (13): datetime, Map a domain :class:`MemoryEpisode` to the stored envelope. ``source`` /…, Point-in-time truth: the system could know this item at ``moment`` only if it…, make_memory_episode(), build_memory(), datetime, A ready-to-query :class:`adapters.graphiti.memory.Memory` over the in-memory…, test_search_returns_domain_episodes() (+5 more)

### Community 34 - "LayerName"
Cohesion: 0.10
Nodes (11): LayerStore, MemoryLayerStore, MinioLayerStore, Any, Protocol, Deterministic in-memory store used by unit and leakage tests., S3-compatible object storage backed by MinIO (ADR-0011)., Read/write interface for the four medallion layers. (+3 more)

### Community 35 - "test_validation_factory.py"
Cohesion: 0.10
Nodes (33): A strategy under the INV-8 lifecycle. No RD-Agent -> LIVE edge exists., StrategyCandidate, Strategy promotion pipeline — deterministic validation gate (INV-8)., ExperimentRecorder, PaperEligibility, Any, datetime, Exception (+25 more)

### Community 36 - "devDependencies"
Cohesion: 0.04
Nodes (47): dependencies, lucide-react, react, react-dom, typescript, vite, @vitejs/plugin-react, devDependencies (+39 more)

### Community 37 - "NautilusBacktestRunner"
Cohesion: 0.09
Nodes (29): NautilusBacktestRunner, Runs one BACKTEST with the Nautilus simulated venue (virtual clock)., make_config(), A realistic cost-inclusive deterministic config; override any field., _fills(), Cost-model tests: commission, spread, slippage are real and applied (skill:…, test_commission_is_applied_per_fill(), test_partial_fill_status_never_claimed_for_single_fill_orders() (+21 more)

### Community 38 - "tradingagents/client.py"
Cohesion: 0.07
Nodes (43): _installed_version(), _installed_version_safely(), _load_graph_class(), _load_graph_class_safely(), datetime, UUID, Live TradingAgents adapter — the ONLY module allowed to import upstream.…, Execute the upstream committee for ``request`` and return a signal. Fails… (+35 more)

### Community 39 - "factories.py"
Cohesion: 0.10
Nodes (46): make_account_state(), make_dead_man_switch_state(), make_domain_event(), make_emergency_control_state(), make_emergency_event(), make_execution_quality(), make_execution_report(), make_experiment_run() (+38 more)

### Community 40 - "PositionSide"
Cohesion: 0.07
Nodes (39): PositionSide, ExecutionPosition, Persisted point-in-time record of one broker-side position., assert_emergency_closure_matches_positions(), An emergency intent may only close a known open position (ADR-0025).…, InMemoryExecutionStateStore, _position_values(), Deterministic in-memory store with the exact same semantics as Postgres. (+31 more)

### Community 41 - "enums.py"
Cohesion: 0.06
Nodes (43): allows_order_submission(), ExperimentStatus, is_live_mode(), PromotionAction, Canonical domain enums for OpenTrading. Values are frozen by…, A Risk Decision is never a bare boolean (INV-4, architecture §7). ``RESIZE``…, Canonical decision reason codes (architecture §7 controls, ADR-0018). Used both…, Outcome of a promotion review (INV-8). Approval is never an LLM action. (+35 more)

### Community 42 - "EmergencyControlState"
Cohesion: 0.10
Nodes (20): DeadManSwitchState, EmergencyControlState, Persisted state of one emergency control (INV-7, architecture §10). Keyed by…, Persisted dead man switch state (singleton row in PostgreSQL).…, _control_values(), _dead_man_values(), EmergencyStore, _empty_dead_man() (+12 more)

### Community 43 - "EmergencyController"
Cohesion: 0.07
Nodes (26): build_emergency_router(), APIRouter, OperatorResolver, build_provenance(), OperationalAlert, Operational alert raised on SAFE_MODE and emergency-control transitions (§31)., Convenience provenance builder shared by the execution engine., EmergencyController (+18 more)

### Community 44 - "Stack"
Cohesion: 0.09
Nodes (47): EmergencyBody, BaseModel, DeadManSwitchReason, EmergencyLevel, The four emergency-control levels (INV-7, architecture §10). Semantics frozen…, Why the dead man switch engaged (INV-7, architecture §10)., EmergencyPolicy, Configuration of the emergency control system (never changeable by LLMs). (+39 more)

### Community 45 - "make_record"
Cohesion: 0.09
Nodes (20): Temporal window pushed down to the store as an optimization. The authoritative…, SearchWindow, InMemoryStore, Backend seam for temporal memory (ADR-0008). - :class:`MemoryStore` — the…, Deterministic in-memory backend — same window semantics as the live store.…, Idempotent write keyed by ``episode_id`` (replays overwrite safely)., _tokens(), make_record() (+12 more)

### Community 46 - "nautilus/__init__.py"
Cohesion: 0.10
Nodes (36): build_config(), main(), Deterministic backtest CLI: prints the reproducibility fingerprints. Usage: uv…, BacktestConfig, BaselineSmaConfig, CommissionConfig, BaseModel, datetime (+28 more)

### Community 47 - "test_command_center_api.py"
Cohesion: 0.06
Nodes (30): SQLAlchemy Core table definitions for the market data catalog. PostgreSQL is…, build_command_center_router(), CommandCenterDataSource, _json(), PostgresCommandCenterDataSource, Any, APIRouter, datetime (+22 more)

### Community 48 - "LiveAutoRegistry"
Cohesion: 0.05
Nodes (42): DemotionBody, PnlBody, PromotionBody, BaseModel, Authenticated operator API for LIVE_AUTO governance (Phase 11). Every mutation…, LiveAutoViolation, RuntimeError, Configuration for LIVE_AUTO governance (Phase 11). ``LiveAutoConfig`` mirrors… (+34 more)

### Community 49 - "Validity"
Cohesion: 0.07
Nodes (15): model_validator, Self, Temporal validity interval [``valid_from``, ``valid_until``].…, Duration in seconds, or None when open-ended., Validity, INVALIDATES: the old claim stays in memory but stops being valid., Reach binds even when validity still contains as_of: the calendar was known 10…, TestTemporalInvalidation (+7 more)

### Community 50 - "synthetic_dataset"
Cohesion: 0.12
Nodes (35): DatasetConfig, Deterministic historical dataset: synthetic (seeded) or parquet replay., build_dataset(), Dataset, _hash_rows(), load_parquet_dataset(), Decimal, Path (+27 more)

### Community 51 - "make_order_intent"
Cohesion: 0.09
Nodes (29): instrument_to_nautilus(), order_intent_to_order(), CurrencyPair, Venue, Map the canonical domain ``Instrument`` to a Nautilus spot ``CurrencyPair``.…, Map the canonical ``OrderIntent`` to a native Nautilus order.…, LimitOrder, MarketOrder (+21 more)

### Community 52 - "MemoryRecord"
Cohesion: 0.07
Nodes (36): FutureMemoryLeakageError, The temporal envelope is impossible: event_time <= available_time <=…, INV-3 violation: an episode with available_time > as_of reached the query…, TemporalOrderingError, Memory, PointInTimeFilter, datetime, UUID (+28 more)

### Community 53 - "make_market_snapshot"
Cohesion: 0.14
Nodes (30): Translate a canonical request into the upstream ``propagate`` surface., request_to_upstream_input(), make_market_snapshot(), TestMarketSnapshot, build_research_request(), datetime, A valid ResearchRequest whose instrument/as_of live in ``context``., The DoD chain must not depend on which adapter sits behind it. (+22 more)

### Community 54 - "schemas/memory.py"
Cohesion: 0.10
Nodes (26): OntologyError, An entity type or relation is not part of the frozen trading ontology., assert_known_entities(), assert_known_relations(), _extraction_model(), BaseModel, Frozen trading ontology (ADR-0008, architecture §11). Seventeen entity types…, Ontology gate for a whole episode: every entity type and relation must be known. (+18 more)

### Community 55 - "market_data/pipeline.py"
Cohesion: 0.08
Nodes (40): _group_bars(), MarketDataPipeline, _merge_gold_rows(), datetime, Medallion ingestion pipeline: RAW → BRONZE → SILVER → GOLD. -…, Build one immutable gold dataset version from all silver runs. Deterministic by…, Deterministic cross-run merge for gold: one row per bar identity. Identity:…, Deterministic raw→bronze→silver→gold pipeline (Phase 1 DoD). (+32 more)

### Community 56 - "export.py"
Cohesion: 0.20
Nodes (13): _canonical_id(), ensure_secret_free(), _note_path(), ValueError, Best-effort Obsidian mirror of authoritative domain events. The event bus and…, Write a mirror note when ``event`` is exportable; otherwise return ``None``., Reject secret-like keys or credential values before a vault write., Raised when content looks like credential material and is not written. (+5 more)

### Community 57 - "bootstrap.py"
Cohesion: 0.09
Nodes (27): PermissionError, assert_runtime_version(), main(), Any, Fail-closed executable composition for autonomous canonical Quant R&D., INV-13: Quant R&D runs on Python 3.11 — the two runtimes are never merged. The…, run_autonomous_cycle(), validate_authority_environment() (+19 more)

### Community 58 - "test_hashing.py"
Cohesion: 0.10
Nodes (35): bar_checksum(), bar_row_key(), canonical_bar_bytes(), canonical_decimal(), canonical_timestamp(), dataset_hash(), _hash_stream(), partition_hash() (+27 more)

### Community 59 - "ConfigurableSlippageFillModel"
Cohesion: 0.10
Nodes (19): ConfigurableSlippageFillModel, NotionalCommissionFeeModel, Decimal, Realistic commission: ``rate_bps`` of trade notional per fill, floored. For FX…, Deterministic slippage by shifting the simulated order book away from best.…, The quote the most recent fill simulation used (for slippage accounting)., Return a book whose only levels sit ``ticks`` away from the touch., datetime (+11 more)

### Community 60 - "ExperimentRun"
Cohesion: 0.11
Nodes (26): RD-Agent translation seam for the isolated Python 3.11 service., Typed boundary around Microsoft RD-Agent (offline research only)., Hypothesis, Implementation, BaseModel, Adapter-owned values; no RD-Agent class crosses this module boundary., CandidateStatus, ExperimentRun (+18 more)

### Community 61 - "test_client.py"
Cohesion: 0.12
Nodes (32): LiveTradingAgentsAdapter, Strict adapter boundary around ``TradingAgentsGraph.propagate``. Lifecycle per…, AdapterConfig, Explicit configuration for one adapter instance. Model choice is mandatory —…, client(), TestClient, fake_state(), FakeGraph (+24 more)

### Community 62 - "App.tsx"
Cohesion: 0.11
Nodes (23): get(), App(), CollectionPage(), Icon, money(), OverviewPage(), RecordSummary(), RiskPage() (+15 more)

### Community 63 - "MemoryCatalog"
Cohesion: 0.08
Nodes (28): Catalog, MemoryCatalog, PostgresCatalog, datetime, Protocol, UUID, Deterministic in-memory catalog (unit and leakage tests)., PostgreSQL-backed catalog (ADR-0010); metadata only, bars stay in MinIO. (+20 more)

### Community 64 - "NautilusRouterStrategy"
Cohesion: 0.10
Nodes (15): NautilusRouterStrategy, datetime, Decimal, OrderAccepted, OrderDenied, OrderFilled, OrderRejected, OrderSubmitted (+7 more)

### Community 65 - "evaluator.py"
Cohesion: 0.13
Nodes (29): EvalReport, evaluate(), evaluate_all(), fixture_to_mock_scenario(), fixture_to_request(), fixture_to_snapshot(), load_scenarios(), BaseModel (+21 more)

### Community 66 - "redact"
Cohesion: 0.09
Nodes (20): Security primitives for trust-zone enforcement (architecture §29, ADR-0025). -…, _attach_filter(), Log redaction — secrets must never reach logs (architecture §29, ADR-0025).…, Return ``text`` with every known secret pattern masked (``None`` → ``""``)., Masks secret patterns on the record itself, before any handler renders.…, Formatter that masks secret patterns (including exception text)., redact(), RedactingFilter (+12 more)

### Community 67 - "make_bar"
Cohesion: 0.24
Nodes (6): make_bar(), _engine(), Unit tests: quality flags, duplicate handling, missing-bar detection., TestDuplicates, TestFlags, TestMissingBars

### Community 68 - "OrderState"
Cohesion: 0.23
Nodes (32): DiscrepancyCode, OrderState, Canonical order lifecycle (INV-6, architecture §8)., Broker reconciliation discrepancy codes (INV-6, architecture §9). Severity is…, The bridge restarts (transport dies, broker state survives): the service…, test_mt4_restart_resyncs_and_reenters(), get_order(), make_broker_view() (+24 more)

### Community 69 - "InvalidStateTransition"
Cohesion: 0.13
Nodes (14): assert_valid_order_transition(), assert_valid_strategy_transition(), InvalidStateTransition, is_valid_order_transition(), is_valid_strategy_transition(), ValueError, Explicit state machines for the canonical lifecycles. The machines here are the…, Raised when a transition is not allowed by the canonical state machine. (+6 more)

### Community 70 - "test_protocol.py"
Cohesion: 0.10
Nodes (21): datetime, One serve iteration: handle a command (if any) + periodic work., parse_message(), datetime, Serialize with an attached checksum (transport integrity, §8)., Parse one frame into a validated wire message (schema validation gate)., serialize_message(), Wire model tests: schema validation, framing, checksum, fingerprints. (+13 more)

### Community 71 - "Bar"
Cohesion: 0.14
Nodes (15): DataQualityEngine, _next_bar_time(), datetime, timedelta, QualityOutcome, Silver-layer data quality: flags, duplicate handling, missing-bar detection.…, Deterministic duplicate resolution. Key: ``(instrument_id, timeframe,…, Interior gaps per (instrument, timeframe) against the bar grid. (+7 more)

### Community 72 - "MarketDataRepository"
Cohesion: 0.12
Nodes (14): MarketDataRepository, PointInTimeFilter, datetime, Bars of a sealed dataset visible at ``as_of`` (INV-3 filter applied).…, Point-in-time snapshot from the latest bar visible at ``as_of``. Returns…, The single INV-3 choke point. Dropping logic in exactly one place makes the…, Read-only query API over sealed gold dataset versions., dataset_id_for() (+6 more)

### Community 73 - "Target Architecture — Autonomous Quantitative Trading & Research Platform"
Cohesion: 0.07
Nodes (28): 10. Point-in-Time rule (INV-3), 11. Data architecture (INV-10), 12. Event bus (INV-15), 13. Canonical domain objects (INV-2), 14. Signal Fusion (INV-16), 15. Post-trade learning loop, 16. Strategy lifecycle (INV-8), 17. LLM evaluation (+20 more)

### Community 74 - "service.py"
Cohesion: 0.06
Nodes (32): execution_report_from_fill(), datetime, UUID, Mappings between canonical Core contracts and MT4 wire messages.…, Translate the canonical OrderIntent into a wire submit_order command.…, Map a venue fill event into the canonical ExecutionReport (INV-6)., submit_command_from_intent(), Poll one pushed event (non-blocking by default). (+24 more)

### Community 75 - "nautilus/engine.py"
Cohesion: 0.10
Nodes (30): code_sha(), Decimal, Venue, The BACKTEST runner: Nautilus ``BacktestEngine`` + virtual clock + domain…, Authoritative balances as tracked by the Nautilus venue (for cross-checks)., Git HEAD SHA of the repository, or the adapter version outside a repo. The code…, compute_metrics(), EquityPoint (+22 more)

### Community 76 - "PositionLedger"
Cohesion: 0.12
Nodes (11): _OpenPosition, PositionLedger, Decimal, OrderFilled, PositionChanged, PositionClosed, PositionOpened, Account-currency equity: quote cash + base cash at mid + unrealized. (+3 more)

### Community 77 - "architecture.md"
Cohesion: 0.07
Nodes (27): 12. Regla Point-in-Time, 14. Event Bus, 15. Objetos de dominio canónicos, 16. Signal Fusion Engine, 17. Post-trade learning loop, 18. Strategy Factory, 1. Visión final, 20. Métricas obligatorias (+19 more)

### Community 78 - "test_workflows.py"
Cohesion: 0.13
Nodes (14): QlibAdapter, Validate untrusted upstream output before it enters a workflow., RDAgentAdapter, CandidateStore, Protocol, FailingQlib, FakeQlib, FakeRDAgent (+6 more)

### Community 79 - "OperationalMetrics"
Cohesion: 0.12
Nodes (7): _tool_metric_name(), CollectorRegistry, OperationalMetrics, Own all application metrics so tests can use an isolated registry., test_operational_metrics_expose_required_low_cardinality_signals(), test_trace_ids_are_not_prometheus_labels(), test_upstream_tool_names_map_to_finite_metric_categories()

### Community 80 - "test_live_auto_api.py"
Cohesion: 0.25
Nodes (17): build_live_auto_router(), APIRouter, OperatorResolver, Build the governance API; callers must inject a real authentication dependency., app_with(), authenticated_operator(), make_registry(), promotion_body() (+9 more)

### Community 81 - "StrategyState"
Cohesion: 0.20
Nodes (27): AssetClass, Strategy lifecycle (INV-8, architecture §16). There is no ``RD-Agent -> LIVE``…, StrategyState, Random, build_account(), build_instrument(), build_policy(), build_portfolio_with_exposure() (+19 more)

### Community 82 - "test_versioning.py"
Cohesion: 0.09
Nodes (28): deserialize_event(), Any, Deserialize and fully validate an envelope (including its payload contract).…, Event layer: registry, payload versioning, standard envelope (INV-15)., EventRegistry, Immutable name → payload contract registry used by producers and consumers., _market_snapshot_0100_to_100(), _market_snapshot_090_to_0100() (+20 more)

### Community 83 - "Guía Completa de Instalación y Uso — OpenTrading"
Cohesion: 0.07
Nodes (26): 10.1 LIVE_GATED — aprobación humana por operación, 10.2 LIVE_AUTO — gobernanza determinista sin aprobación por operación, 10.3 Controles de emergencia y dead man switch (INV-7), 10. Modos LIVE_GATED y LIVE_AUTO (cuenta demo), 11. Quant R&D (fábrica de estrategias), 12. Observabilidad: métricas, trazas y paneles, 13. Operación diaria y recuperación, 14. Configuración de referencia (+18 more)

### Community 84 - "build_domain_event"
Cohesion: 0.14
Nodes (20): build_domain_event(), datetime, UUID, Envelope construction, serialization and validation (INV-15)., Build a standard envelope around a validated canonical payload. The payload…, Deterministic UTF-8 bytes for the event bus., serialize_event(), ValueError (+12 more)

### Community 86 - "CalibrationStore"
Cohesion: 0.11
Nodes (15): CalibrationArtifact, Complete, versioned output of a calibration run. Everything needed to reproduce…, EvaluationReport, Full comparison of the mandatory configurations on one case set., CalibrationStore, Any, Path, UUID (+7 more)

### Community 87 - "test_registry.py"
Cohesion: 0.20
Nodes (28): LiveAutoConfig, Fail closed unless the capability is on AND every limit is explicit., decision_for(), enabled_config(), intent_for(), make_registry(), price(), promote() (+20 more)

### Community 88 - "make_intent"
Cohesion: 0.19
Nodes (24): ExecutionDivergenceError, RuntimeError, A venue report contradicts authoritative state in a capital-relevant way., make_intent(), _candidate(), fixture, OrderStateApplier DoD tests: full canonical lifecycle, crash-restart state,…, A fresh engine over the same store sees exactly the persisted state. (+16 more)

### Community 89 - "ScriptedRedis"
Cohesion: 0.13
Nodes (7): OperationalError, operational_error(), Any, Exception, A realistic PostgreSQL connectivity failure (server restart window)., Minimal faithful ``RedisConnection`` double for one RedisStreamBus. Streams and…, ScriptedRedis

### Community 90 - "test_invariants.py"
Cohesion: 0.06
Nodes (13): _effective_budget(), Decimal, parametrize, Critical invariants of the Risk Engine (DoD: no tested path bypasses limits). -…, The three blocking invariants: daily loss, stale data, disabled strategy., For each soft limit: an adversarial proposal never bypasses the limit. Every…, approved risk <= policy risk — for every decision type, exactly., approved quantity <= configured maximum (policy and instrument). (+5 more)

### Community 91 - "compilerOptions"
Cohesion: 0.08
Nodes (23): compilerOptions, allowJs, allowSyntheticDefaultImports, esModuleInterop, forceConsistentCasingInFileNames, isolatedModules, jsx, lib (+15 more)

### Community 92 - "5. Controls"
Cohesion: 0.09
Nodes (22): 1. Trust zones, 2. Assets, 3. Threat actors, 4. Threat register, 5. Controls, 6. Definition of Done — traceability, 7. Residual risks, C10 — Emergency controls (INV-7) (+14 more)

### Community 93 - "test_process_crash.py"
Cohesion: 0.14
Nodes (13): _check_ok(), _collect(), _connect(), _CrashOnAckBus, emulator(), _feed_heartbeats(), fixture, Process crash scenarios: worker, API, and the Core ↔ MT4 heartbeat. - **Worker… (+5 more)

### Community 94 - "StageWorker"
Cohesion: 0.11
Nodes (11): Reclaim stale PEL entries; dead-letter poisoned ones. Returns the reclaimed…, Dispatch one message; ACK on success, leave unacked on failure. Stages publish…, One pass: recover, then read+dispatch new messages. Returns (reclaimed,…, One consumer group: recovery loop + new-message loop (unattended)., StageWorker, Long-running unattended mode: scheduler + worker threads., Runs the autonomous PAPER pipeline, optionally forever., Create the paper account if absent (idempotent). (+3 more)

### Community 95 - "LangfuseTracer"
Cohesion: 0.08
Nodes (22): Vendor-specific telemetry adapters with safe no-op defaults., deterministic_trace_id(), LangfuseTracer, NullObservation, Any, UUID, Langfuse v4 tracing correlated to the canonical domain ``trace_id``., Return the W3C 16-byte lowercase hexadecimal trace identifier. (+14 more)

### Community 96 - "test_boundary.py"
Cohesion: 0.16
Nodes (15): _imports_in(), AST, MonkeyPatch, Path, Boundary contract tests: TradingAgents can disappear entirely. These tests…, Block any import of the ``tradingagents`` top-level package., (node, module-name) for every import in a file, with module context., Whether ``node`` sits inside a function definition (lazy import seam). (+7 more)

### Community 98 - "PortfolioExposure"
Cohesion: 0.13
Nodes (10): PortfolioExposure, Pre-computed aggregate exposures of the current portfolio (engines/portfolio).…, build_portfolio(), make_position(), Hard-check REJECT paths: every hard violation rejects with its reason code., TestSimultaneity, Boundary tests: exactly-at-limit behavior with exact Decimal arithmetic.…, TestCountBoundaries (+2 more)

### Community 99 - "Agent details"
Cohesion: 0.10
Nodes (19): Agent details, Agent index, AI Engineering Team Architecture — OpenTrading, ai-trading-systems, backend-platform, command-center, execution-mt4, Hard boundary (+11 more)

### Community 100 - "3. Classification against the requested axes"
Cohesion: 0.10
Nodes (19): 1. Snapshot facts (repository evidence), 2. Complete repository inventory, 3.10 Tests, 3.11 Configuration, 3.12 Secrets handling, 3.1 Existing trading code, 3.2 Experimental code, 3.3 Duplicated code (+11 more)

### Community 101 - "test_resize.py"
Cohesion: 0.09
Nodes (7): _portfolio(), Decimal, RESIZE paths: the engine reduces the quantity to the binding soft limit. The…, TestExposureResize, TestLeverageMarginResize, TestResizeShape, TestRiskBudgetResize

### Community 102 - "strategy.py"
Cohesion: 0.12
Nodes (23): CurrencyPair, BaselineSmaStrategy, DomainStrategy, datetime, Decimal, Protocol, Domain-side strategy contract and the minimal deterministic baseline. The…, What a domain strategy may see at one bar (point-in-time, INV-3). Nothing… (+15 more)

### Community 103 - "TokenUsageCollector"
Cohesion: 0.20
Nodes (7): Any, Duck-typed LangChain callback handler accumulating token usage. Deliberately…, Called by LangChain after each LLM generation completes., Trace the real provider invocation without exporting prompt contents., LangChain callback: start a Langfuse tool observation., TokenUsageCollector, BaseException

### Community 104 - "test_readyz.py"
Cohesion: 0.22
Nodes (11): Dependency readiness checks backing ``GET /readyz`` (§31 observability). Each…, Serializable projection for API responses., result_dicts(), _client(), _down(), _ok(), CheckFunc, TestClient (+3 more)

### Community 105 - "schemas/__init__.py"
Cohesion: 0.04
Nodes (79): BaselineQuantProducer, _episode_stance(), MemoryContextProducer, datetime, UUID, Signal producers for the research stage (Phase 7). -…, Deterministic momentum quant signal from a single snapshot. ``strength`` scales…, Distills point-in-time memory episodes into a directional stance. Only episodes… (+71 more)

### Community 106 - "SafeModeViolation"
Cohesion: 0.15
Nodes (18): Action classes gated by SAFE_MODE. Only NEW_ENTRY is blocked., SafeModeAction, RuntimeError, Raise :class:`SafeModeViolation` for blocked actions while active., Raised when an action is blocked while SAFE_MODE is active., SafeModeViolation, _service(), TestWireLevelPartialFills (+10 more)

### Community 107 - "obsidian/__init__.py"
Cohesion: 0.18
Nodes (8): Obsidian adapter: a non-authoritative human knowledge mirror (§25)., NullVaultWriter, Protocol, Obsidian vault adapter (architecture §25, INV-9). Writes human-readable notes…, Write-one-note boundary for the Obsidian vault., Persist one note; returns the vault-relative path written., Unavailable-vault sink that deliberately persists nothing., VaultWriter

### Community 108 - "._require_calibrated_version"
Cohesion: 0.47
Nodes (3): model_validator, Self, INV-16: weights must derive from historical calibration. A config that never…

### Community 109 - "datetime"
Cohesion: 0.18
Nodes (5): datetime, timedelta, Current time as timezone-aware UTC., Move forward by ``delta`` (strictly positive) and return the new time., Jump to ``moment``; moving backwards is refused (monotonic simulation time).

### Community 110 - "Instrument"
Cohesion: 0.13
Nodes (10): _instrument_from_row(), Any, OrderRejectionSim, datetime, Decimal, Deterministic simulated-venue order rejection (ADR-0007: rejection simulation).…, Deterministic rejection rule chain evaluated per ``OrderIntent``., Return a rejection reason, or ``None`` when the order may proceed. (+2 more)

### Community 111 - "Architecture Invariants"
Cohesion: 0.11
Nodes (17): Architecture Invariants, INV-10 — Data stores are separated by purpose, INV-11 — Graphify ≠ Graphiti, INV-12 — Frozen decisions require ADRs, INV-13 — Two runtimes, never merged, INV-14 — Dependencies are pinned, INV-15 — Domain events use the standard envelope, INV-16 — Signal Fusion weights are calibrated, not arbitrary (+9 more)

### Community 112 - "MinioArtifactStore"
Cohesion: 0.14
Nodes (7): ArtifactStore, MinioArtifactStore, Any, Protocol, Object-storage boundary for post-trade artifacts., S3-compatible artifact storage backed by MinIO (ADR-0011)., TestMinioArtifacts

### Community 113 - "5. Scenario playbooks"
Cohesion: 0.12
Nodes (16): 1. Objectives, 2. What is already built in, 3. Backups, 4. Restore, 5.1 Core crash mid-submit, 5.2 MT4 / broker unavailable, 5.3 Material divergence (unexpected broker position / quantity mismatch), 5.4 Postgres loss (volume corruption / deleted) (+8 more)

### Community 114 - "test_property_based.py"
Cohesion: 0.40
Nodes (14): given, _effective_budget(), _entry_price(), _evaluate(), Any, Decimal, settings, Property-based tests (Hypothesis) for the deterministic Risk Engine. Properties… (+6 more)

### Community 115 - "RepositorySnapshotSource"
Cohesion: 0.22
Nodes (6): NoSnapshotError, datetime, RuntimeError, Raised when no point-in-time snapshot is available for a cycle., Snapshots from the sealed market-data repository (INV-3 choke point)., RepositorySnapshotSource

### Community 116 - "ConnectionHealth"
Cohesion: 0.11
Nodes (16): bind_ephemeral(), ConnectionHealth, ConnectionMonitor, datetime, StrEnum, Send one message with an integrity checksum attached., Bind a tcp endpoint, allowing port ``*`` to pick an ephemeral port., Tracks bridge liveness from the heartbeat stream (clock-injected). (+8 more)

### Community 117 - "EvaluationResult"
Cohesion: 0.18
Nodes (7): EvaluationResult, Any, BaseModel, Protocol, QlibBackend, Qlib result mapper; Qlib classes never enter the canonical domain., Typed Qlib evaluation boundary for the Python 3.11 research runtime.

### Community 118 - "test_adapter_boundary.py"
Cohesion: 0.17
Nodes (13): _imports_in(), AST, MonkeyPatch, Path, Boundary contract tests: Graphiti can disappear entirely. These tests enforce…, (node, module-name) for every import in a file, with module context., Whether ``node`` sits inside a function definition (lazy import seam)., Block any import of the ``graphiti_core`` top-level package. (+5 more)

### Community 119 - "26. Command Center"
Cohesion: 0.13
Nodes (15): 26. Command Center, 6. Los cinco modos operativos, Agents, BACKTEST, Backtests, LIVE_AUTO, LIVE_GATED, Memory (+7 more)

### Community 120 - "32. Roadmap definitivo"
Cohesion: 0.24
Nodes (15): 32. Roadmap definitivo, Definition of Done, Fase 0 — Foundations, Fase 10 — Strategy Promotion, Fase 11 — LIVE_AUTO, Fase 12 — Continuous Quant Firm, Fase 1 — Data Platform, Fase 2 — TradingAgents (+7 more)

### Community 121 - "test_live_infra_restart.py"
Cohesion: 0.32
Nodes (9): _compose(), _docker_available(), live_chaos(), _postgres_up(), fixture, Real container restarts (docker-gated; opt-in). These scenarios actually…, settings(), TestLiveRestarts (+1 more)

### Community 122 - "FakeGraph"
Cohesion: 0.22
Nodes (3): FakeGraph, Any, Upstream graph double: records add_episode calls, returns queued edges.

### Community 123 - "MemoryStore"
Cohesion: 0.22
Nodes (6): MemoryStore, Protocol, Storage protocol: write records, search within a temporal window., Persist one memory record (idempotent per ``episode_id``)., Return hits matching ``query`` within the pushed-down temporal window. The…, Release backend resources (no-op for in-memory).

### Community 124 - "NativeRDAgentQlibBackend"
Cohesion: 0.26
Nodes (4): NativeRDAgentQlibBackend, Any, Concrete bridge to RD-Agent 0.8.0's Qlib factor/model loops. All imports of…, Drive one official RD-Agent hypothesis/code/run cycle at a time.

### Community 125 - "Runbook — Infrastructure"
Cohesion: 0.14
Nodes (13): Architecture, Backups (operational notes), Definition of Done (this milestone), Development vs production, Files, Health checks, Migrations, Observability (+5 more)

### Community 126 - "create_app"
Cohesion: 0.09
Nodes (24): HealthCheckResult, CheckFunc, Run one probe with a hard timeout; never raise., Probe every dependency concurrently and return one result per check., Outcome of one dependency probe., run_check(), run_readiness_checks(), create_app() (+16 more)

### Community 127 - "Phase 0 — Foundations: Implementation Record"
Cohesion: 0.15
Nodes (12): 10. Explicitly NOT implemented (phase gates), 11. Local verification commands, 1. Definition of Done — evidence, 2. Module map (architecture §27 layout), 3. Canonical contracts (`core/schemas`), 4. Enums and state machines (`core/domain`), 5. Clock semantics (`core/clock`), 6. Event bus contract (`core/events`) (+4 more)

### Community 128 - "MirroringEventBus"
Cohesion: 0.31
Nodes (4): MirroringEventBus, Any, Bus proxy that mirrors only after authoritative publish succeeds. Export errors…, Mirror an already-authoritative event (used by synchronous runs).

### Community 129 - "test_paper_executor.py"
Cohesion: 0.40
Nodes (6): build_executor(), make_intent(), make_snapshot(), Decimal, Nautilus paper executor tests: fills, slippage, determinism, rejects., TestPaperExecutor

### Community 131 - "Domain Glossary (OpenTrading)"
Cohesion: 0.17
Nodes (11): Core objects (§15), Data (§13), Domain Glossary (OpenTrading), Events (§14), Kill switches (§10), Memory (§11), Operating modes (§6), Order state machine (§9) (+3 more)

### Community 132 - "Detail"
Cohesion: 0.17
Nodes (11): 10–15 Quant, 16–20 Trading, 1–4 Repository intelligence, 21 AI systems, 22–27 Engineering, 28–31 Security, 32–35 Operations, 5–9 Architecture (+3 more)

### Community 133 - "Product"
Cohesion: 0.17
Nodes (11): Accessibility & Inclusion, Capabilities and Constraints, Evidence on Hand, Operating Context, Platform, Positioning, Product, Product Principles (+3 more)

### Community 134 - "SequenceTracker"
Cohesion: 0.24
Nodes (4): Record a newly accepted sequence (must equal expected)., Per-namespace last-accepted sequences (reconciliation payload)., Strict monotonic sequence validation per ``strategy_id`` namespace. Sequences…, SequenceTracker

### Community 135 - "Task Routing Workflow"
Cohesion: 0.18
Nodes (10): Anti-swarm rule, Step 1 — Classify, Step 2 — Context, Step 3 — Primary specialist, Step 4 — Mandatory reviewers, Step 5 — Skills, Step 6 — Execute, Step 7 — Verify (+2 more)

### Community 136 - "test_serialization.py"
Cohesion: 0.39
Nodes (7): datetime, parametrize, Deterministic serialization tests for every canonical contract., Same content -> same bytes, independent of construction time., test_json_uses_utc_iso_timestamps(), test_round_trip_is_lossless(), test_serialization_is_deterministic()

### Community 137 - "Operations Manual — OpenTrading"
Cohesion: 0.18
Nodes (10): 1. Operating modes (INV-8), 2. Daily runbook — development / staging, 3. Live operations (LIVE_GATED), 4. Emergency control system (INV-7), 5. Reconciliation (INV-6 — mandatory), 6. Monitoring & alerting, 7. Maintenance tasks, 8. Troubleshooting quick map (+2 more)

### Community 138 - "Observability alert runbook"
Cohesion: 0.18
Nodes (10): Daily loss threshold, Drawdown threshold, LLM provider failure, MT4 heartbeat missing, Observability alert runbook, PostgreSQL failure, Queue backlog, Redis failure (+2 more)

### Community 139 - "mt4/protocol — MT4 execution protocol v1.0 (ADR-0020, §34.18)"
Cohesion: 0.18
Nodes (10): 1. Transport, 2. Envelope (every message), 3. Messages, 4. Validation order (frozen — EA must match), 5. EA defense-in-depth venue checks (INV-5, §8), 6. Error codes, 7. Connection health, 8. Versioning policy (+2 more)

### Community 140 - "Agent: AI Trading Systems"
Cohesion: 0.20
Nodes (9): Agent: AI Trading Systems, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 141 - "Agent: Backend Platform"
Cohesion: 0.20
Nodes (9): Agent: Backend Platform, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 142 - "Agent: Command Center / Frontend"
Cohesion: 0.20
Nodes (9): Agent: Command Center / Frontend, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 143 - "Agent: Execution / MT4"
Cohesion: 0.20
Nodes (9): Agent: Execution / MT4, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 144 - "Agent: Infrastructure & SRE"
Cohesion: 0.20
Nodes (9): Agent: Infrastructure & SRE, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 145 - "Agent: Market Data"
Cohesion: 0.20
Nodes (9): Agent: Market Data, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 146 - "Agent: Principal Architect"
Cohesion: 0.20
Nodes (9): Agent: Principal Architect, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 147 - "Agent: Quant Research"
Cohesion: 0.20
Nodes (9): Agent: Quant Research, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 148 - "Agent: Risk"
Cohesion: 0.20
Nodes (9): Agent: Risk, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 149 - "Agent: Security"
Cohesion: 0.20
Nodes (9): Agent: Security, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 150 - "Agent: Trading & Backtest"
Cohesion: 0.20
Nodes (9): Agent: Trading & Backtest, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 151 - "Agent: Verification"
Cohesion: 0.20
Nodes (9): Agent: Verification, Automatic triggers, Forbidden actions, Mandatory collaborators, Non-goals, Output standard, Owned skills, Purpose (+1 more)

### Community 152 - "ADR/README.md"
Cohesion: 0.20
Nodes (8): ADR-0021: Broker reconciliation and Safe Mode (persisted execution state), Consequences, Context, Decision, Accepted, ADR Index — OpenTrading, Frozen items not yet ADR'd, Process

### Community 153 - "1. What was built"
Cohesion: 0.20
Nodes (9): 1. What was built, 2. Definition of Done — evidence, 3. Checks run, 4. Operational notes, Extensibility for fundamentals / macro / news, HTTP API (`apps/api/market_data.py`), Phase 1 — Data Platform: Market Data Implementation Record, Pipeline: RAW → BRONZE → SILVER → GOLD → MarketSnapshot (+1 more)

### Community 154 - "Phase 5 — Deterministic Risk & Policy Engine (implementation record)"
Cohesion: 0.20
Nodes (9): Controls, Decision assembly, Definition of Done, Denomination (ADR-0018), Inputs, Phase 5 — Deterministic Risk & Policy Engine (implementation record), Sizing math (deterministic, exact), Tests (`tests/risk/`) (+1 more)

### Community 155 - "Known Limitations — OpenTrading"
Cohesion: 0.20
Nodes (9): Documentation & repository, Execution & venues, Infrastructure & observability, Known Limitations — OpenTrading, Performance, Resolution policy, Risk & fusion, Security (+1 more)

### Community 156 - "Runbook — Local Development"
Cohesion: 0.20
Nodes (9): Daily commands, Endpoints (dev), First-time setup, Market data API (Phase 1), Prerequisites, Runbook — Local Development, Running the API against the stack, Troubleshooting (+1 more)

### Community 157 - "FileVaultWriter"
Cohesion: 0.28
Nodes (6): FileVaultWriter, Path, Filesystem vault writer (UTF-8, parent directories created as needed)., Path, test_file_vault_writer_rejects_escaping_paths(), test_file_vault_writer_writes_and_reads()

### Community 158 - "19. Validation Factory"
Cohesion: 0.22
Nodes (9): 19. Validation Factory, Backtest básico, Monte Carlo, Multiple-testing protection, Out-of-sample, Purged/embargo validation, Regime testing, Sensitivity (+1 more)

### Community 159 - "Runbook — Secrets management (SOPS + age)"
Cohesion: 0.22
Nodes (8): Encrypting / decrypting, One-time setup, Policy, Production compose, Rotation, Runbook — Secrets management (SOPS + age), Secret inventory (production), Verification

### Community 160 - ".ai — Canonical AI Engineering Layer (OpenTrading)"
Cohesion: 0.25
Nodes (7): Agents (one primary per task by default), .ai — Canonical AI Engineering Layer (OpenTrading), Governance notes, Hard boundary (never changes), Layout, Routing, Tool adapters

### Community 161 - "LLM Agent Evaluation"
Cohesion: 0.25
Nodes (7): Inputs, LLM Agent Evaluation, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 162 - "ADR Management"
Cohesion: 0.25
Nodes (7): ADR Management, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 163 - "Architecture Review"
Cohesion: 0.25
Nodes (7): Architecture Review, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 164 - "Domain Boundary Review"
Cohesion: 0.25
Nodes (7): Domain Boundary Review, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 165 - "Event Contract Design"
Cohesion: 0.25
Nodes (7): Event Contract Design, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 166 - "State Machine Review"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Procedure, Purpose, Related agents, State Machine Review, Trigger conditions

### Community 167 - "API Contract Review"
Cohesion: 0.25
Nodes (7): API Contract Review, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 168 - "Dead Code Detection"
Cohesion: 0.25
Nodes (7): Dead Code Detection, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 169 - "Debugging"
Cohesion: 0.25
Nodes (7): Debugging, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 170 - "Performance Profiling"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Performance Profiling, Procedure, Purpose, Related agents, Trigger conditions

### Community 171 - "Refactoring"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Procedure, Purpose, Refactoring, Related agents, Trigger conditions

### Community 172 - "Test Generation"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Procedure, Purpose, Related agents, Test Generation, Trigger conditions

### Community 173 - "Docker Review"
Cohesion: 0.25
Nodes (7): Docker Review, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 174 - "Incident Analysis"
Cohesion: 0.25
Nodes (7): Incident Analysis, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 175 - "Observability Review"
Cohesion: 0.25
Nodes (7): Inputs, Observability Review, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 176 - "Production Readiness"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Procedure, Production Readiness, Purpose, Related agents, Trigger conditions

### Community 177 - "Backtest Validation"
Cohesion: 0.25
Nodes (7): Backtest Validation, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 178 - "Experiment Reproducibility"
Cohesion: 0.25
Nodes (7): Experiment Reproducibility, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 179 - "Factor Evaluation"
Cohesion: 0.25
Nodes (7): Factor Evaluation, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 180 - "Model Evaluation"
Cohesion: 0.25
Nodes (7): Inputs, Model Evaluation, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 181 - "Point-in-Time Validation"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Point-in-Time Validation, Procedure, Purpose, Related agents, Trigger conditions

### Community 182 - "Walk-Forward Validation"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions, Walk-Forward Validation

### Community 183 - "Change Impact Analysis"
Cohesion: 0.25
Nodes (7): Change Impact Analysis, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 184 - "Dependency Tracing"
Cohesion: 0.25
Nodes (7): Dependency Tracing, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 185 - "Graphify Context"
Cohesion: 0.25
Nodes (7): Graphify Context, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 186 - "Repository Navigation"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Procedure, Purpose, Related agents, Repository Navigation, Trigger conditions

### Community 187 - "Dependency Security"
Cohesion: 0.25
Nodes (7): Dependency Security, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 188 - "Privilege Boundary Review"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Privilege Boundary Review, Procedure, Purpose, Related agents, Trigger conditions

### Community 189 - "Secret Scan"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Procedure, Purpose, Related agents, Secret Scan, Trigger conditions

### Community 190 - "Threat Model"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Procedure, Purpose, Related agents, Threat Model, Trigger conditions

### Community 191 - "Execution Safety"
Cohesion: 0.25
Nodes (7): Execution Safety, Inputs, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 192 - "Order Lifecycle Review"
Cohesion: 0.25
Nodes (7): Inputs, Order Lifecycle Review, Outputs, Procedure, Purpose, Related agents, Trigger conditions

### Community 193 - "Portfolio Risk Review"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Portfolio Risk Review, Procedure, Purpose, Related agents, Trigger conditions

### Community 194 - "Reconciliation Review"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Procedure, Purpose, Reconciliation Review, Related agents, Trigger conditions

### Community 195 - "Trading Cost Validation"
Cohesion: 0.25
Nodes (7): Inputs, Outputs, Procedure, Purpose, Related agents, Trading Cost Validation, Trigger conditions

### Community 196 - "compilerOptions"
Cohesion: 0.25
Nodes (7): compilerOptions, composite, module, moduleResolution, skipLibCheck, include, vite.config.ts

### Community 197 - "_validate_lineage"
Cohesion: 0.46
Nodes (4): Any, model_validator, Self, _validate_lineage()

### Community 199 - "AGENTS.md — OpenTrading (Codex & generic agent adapters)"
Cohesion: 0.29
Nodes (6): AGENTS.md — OpenTrading (Codex & generic agent adapters), Context, Hard rules, Managed engineering policy, Read first (cheap bootstrap), Routing

### Community 200 - "Quant R&D Runtime Specification"
Cohesion: 0.25
Nodes (7): Boundaries, Capability map, Commands, Objective, Quant R&D Runtime Specification, Stack and exact pins, Success criteria

### Community 201 - "infra_health.py"
Cohesion: 0.43
Nodes (6): main(), probe_http(), probe_minio(), probe_postgres(), probe_redis(), ProbeResult

### Community 202 - "OpenTrading — GitHub Copilot instructions"
Cohesion: 0.29
Nodes (6): Always start here, Context, Hard rules, OpenTrading — GitHub Copilot instructions, Reporting, Routing (do not wait for the user to name an agent)

### Community 203 - "adapters/graphiti — temporal semantic memory (Phase 3)"
Cohesion: 0.29
Nodes (6): adapters/graphiti — temporal semantic memory (Phase 3), Layout, Live backend (FalkorDB), Memory tiers, Point-in-time semantics (INV-3), Tests

### Community 204 - "RDAgentBackend"
Cohesion: 0.33
Nodes (3): Any, Protocol, RDAgentBackend

### Community 205 - "adapters/tradingagents — TradingAgents behind a strict boundary (ADR-0004)"
Cohesion: 0.29
Nodes (6): adapters/tradingagents — TradingAgents behind a strict boundary (ADR-0004), Boundary rules, Point-in-time contract (INV-3), Tests, Upstream pin (INV-14), Usage

### Community 206 - ".snapshot_for"
Cohesion: 0.29
Nodes (4): Any, datetime, Cached point-in-time snapshot for (instrument, step)., Most recent snapshot for an instrument (latest_snapshots first).

### Community 207 - "CLAUDE.md — OpenTrading (Claude Code adapter)"
Cohesion: 0.33
Nodes (5): Bootstrap (read before working), CLAUDE.md — OpenTrading (Claude Code adapter), Managed engineering policy, Report, Working rules

### Community 208 - "ADR-0001: Python as the quantitative backend language"
Cohesion: 0.29
Nodes (6): ADR-0001: Python as the quantitative backend language, Alternatives considered, Consequences, Context, Decision, Validation

### Community 209 - "ADR-0002: TypeScript for the Command Center"
Cohesion: 0.29
Nodes (6): ADR-0002: TypeScript for the Command Center, Alternatives considered, Consequences, Context, Decision, Validation

### Community 210 - "ADR-0003: MQL4 exists only in the MT4 execution bridge"
Cohesion: 0.29
Nodes (6): ADR-0003: MQL4 exists only in the MT4 execution bridge, Alternatives considered, Consequences, Context, Decision, Validation

### Community 211 - "ADR-0004: TradingAgents as the LLM research committee"
Cohesion: 0.29
Nodes (6): ADR-0004: TradingAgents as the LLM research committee, Alternatives considered, Consequences, Context, Decision, Validation

### Community 212 - "ADR-0005: Qlib as the quantitative research platform"
Cohesion: 0.29
Nodes (6): ADR-0005: Qlib as the quantitative research platform, Alternatives considered, Consequences, Context, Decision, Validation

### Community 213 - "ADR-0006: RD-Agent as the autonomous R&D factory (offline)"
Cohesion: 0.29
Nodes (6): ADR-0006: RD-Agent as the autonomous R&D factory (offline), Alternatives considered, Consequences, Context, Decision, Validation

### Community 214 - "ADR-0007: NautilusTrader as the event-driven backtest/paper engine"
Cohesion: 0.29
Nodes (6): ADR-0007: NautilusTrader as the event-driven backtest/paper engine, Alternatives considered, Consequences, Context, Decision, Validation

### Community 215 - "ADR-0008: Graphiti as the temporal trading memory"
Cohesion: 0.29
Nodes (6): ADR-0008: Graphiti as the temporal trading memory, Alternatives considered, Consequences, Context, Decision, Validation

### Community 216 - "ADR-0009: Graphify as development context tooling only"
Cohesion: 0.29
Nodes (6): ADR-0009: Graphify as development context tooling only, Alternatives considered, Consequences, Context, Decision, Validation

### Community 217 - "ADR-0010: PostgreSQL as the transactional source of truth"
Cohesion: 0.29
Nodes (6): ADR-0010: PostgreSQL as the transactional source of truth, Alternatives considered, Consequences, Context, Decision, Validation

### Community 218 - "ADR-0011: MinIO + Parquet for large historical datasets"
Cohesion: 0.29
Nodes (6): ADR-0011: MinIO + Parquet for large historical datasets, Alternatives considered, Consequences, Context, Decision, Validation

### Community 219 - "ADR-0012: Redis Streams as the initial event bus"
Cohesion: 0.29
Nodes (6): ADR-0012: Redis Streams as the initial event bus, Alternatives considered, Consequences, Context, Decision, Validation

### Community 220 - "ADR-0013: Langfuse for AI observability"
Cohesion: 0.29
Nodes (6): ADR-0013: Langfuse for AI observability, Alternatives considered, Consequences, Context, Decision, Validation

### Community 221 - "ADR-0014: Prometheus + Grafana for operational observability"
Cohesion: 0.29
Nodes (6): ADR-0014: Prometheus + Grafana for operational observability, Alternatives considered, Consequences, Context, Decision, Validation

### Community 222 - "ADR-0015: Deterministic Risk Engine (no LLM authority over capital)"
Cohesion: 0.29
Nodes (6): ADR-0015: Deterministic Risk Engine (no LLM authority over capital), Alternatives considered, Consequences, Context, Decision, Validation

### Community 223 - "ADR-0016: MT4 as execution venue only"
Cohesion: 0.29
Nodes (6): ADR-0016: MT4 as execution venue only, Alternatives considered, Consequences, Context, Decision, Validation

### Community 224 - "ADR-0017: Point-in-time market data semantics (medallion pipeline)"
Cohesion: 0.29
Nodes (6): ADR-0017: Point-in-time market data semantics (medallion pipeline), Alternatives considered, Consequences, Context, Decision, Validation

### Community 225 - "ADR-0018: Risk Engine — RESIZE decision and exposure denomination"
Cohesion: 0.29
Nodes (6): ADR-0018: Risk Engine — RESIZE decision and exposure denomination, Alternatives considered, Consequences, Context, Decision, Validation

### Community 226 - "ADR-0019: Signal Fusion Engine — calibrated weights, signed components, regime-specific models"
Cohesion: 0.29
Nodes (6): ADR-0019: Signal Fusion Engine — calibrated weights, signed components, regime-specific models, Alternatives considered, Consequences, Context, Decision, Validation

### Community 227 - "ADR-0020: MT4 execution protocol v1.0 (versioned ZeroMQ, emulator-first)"
Cohesion: 0.29
Nodes (6): ADR-0020: MT4 execution protocol v1.0 (versioned ZeroMQ, emulator-first), Alternatives considered, Consequences, Context, Decision, Validation

### Community 228 - "Context Strategy — OpenTrading"
Cohesion: 0.29
Nodes (6): Cheap context bootstrap, Context Strategy — OpenTrading, Correctness override, Graphify policy, Priority order, Token discipline

### Community 229 - "30. Testing"
Cohesion: 0.29
Nodes (7): 30. Testing, Chaos tests, Integration, Leakage tests, Property-based, Replay tests, Unit

### Community 230 - "Gap Analysis — Current vs Target Architecture"
Cohesion: 0.29
Nodes (6): 1. Component-by-component gap, 2. Documentation-level gaps (closed or remaining), 3. Where the repository is AHEAD of the target, 4. Structural risks of the gap, 5. Verdict, Gap Analysis — Current vs Target Architecture

### Community 231 - "Implementation Order — OpenTrading"
Cohesion: 0.29
Nodes (6): 1. Guiding constraints, 2. Implementation dependency graph, 3. Phase-by-phase order with deliverables and gates, 4. Cross-cutting workstreams (interleaved, not phases), 5. Immediate next actions (still non-feature), Implementation Order — OpenTrading

### Community 232 - "Phase 7 — Autonomous PAPER pipeline"
Cohesion: 0.29
Nodes (6): Components, Definitions of Done (verified by tests), Operating modes, Phase 7 — Autonomous PAPER pipeline, Recovery guarantees, The lifecycle

### Community 233 - "Production Readiness — OpenTrading"
Cohesion: 0.29
Nodes (6): Blocking issues: status after this audit, Open items before live capital (gates), Production Readiness — OpenTrading, Verdict, Verification matrix (how to re-audit), What is production-grade today

### Community 234 - "Runbook — Autonomous PAPER pipeline"
Cohesion: 0.29
Nodes (6): 1. Quick start (no infrastructure), 2. Full stack (Redis Streams + PostgreSQL), 3. Key configuration (OT_* env / .env), 4. Operations & recovery, 5. Stop safely, Runbook — Autonomous PAPER pipeline

### Community 236 - "mt4/config.py"
Cohesion: 0.50
Nodes (3): Mt4Settings, BaseSettings, MT4 execution settings (OT_MT4_* environment variables). Mirrors the pattern of…

### Community 237 - "engines/signal_fusion — Signal Fusion Engine (Phase 7, INV-16)"
Cohesion: 0.29
Nodes (6): Calibration & research evaluation, engines/signal_fusion — Signal Fusion Engine (Phase 7, INV-16), Fusion law, Guarantees, Modules, Usage

### Community 238 - "OpenTrading — GitHub Copilot instructions"
Cohesion: 0.29
Nodes (6): Always start here, Context, Hard rules, OpenTrading — GitHub Copilot instructions, Reporting, Routing (do not wait for the user to name an agent)

### Community 239 - "Postmortem — EURUSD LONG"
Cohesion: 0.29
Nodes (6): Expected vs actual, Lessons, Metrics, Postmortem — EURUSD LONG, Signal quality, Trace

### Community 240 - "adapters/mt4 — MT4 execution protocol (Phase 6, ADR-0020)"
Cohesion: 0.33
Nodes (5): adapters/mt4 — MT4 execution protocol (Phase 6, ADR-0020), Guarantees implemented, Modules, Topology, Usage

### Community 241 - "adapters/nautilus — NautilusTrader event-driven backtest engine (ADR-0007)"
Cohesion: 0.33
Nodes (5): adapters/nautilus — NautilusTrader event-driven backtest engine (ADR-0007), BACKTEST mode on the virtual clock, Definition of Done, Extending to PAPER / LIVE, Layout

### Community 242 - "Research context — $instrument_id @ $as_of"
Cohesion: 0.33
Nodes (5): Point-in-time market context (valid strictly at or before $as_of), Question, Research context — $instrument_id @ $as_of, Scope, Supplementary context

### Community 243 - "AGENTS.md — OpenTrading (Codex & generic agent adapters)"
Cohesion: 0.29
Nodes (6): AGENTS.md — OpenTrading (Codex & generic agent adapters), Context, Hard rules, Managed engineering policy, Read first (cheap bootstrap), Routing

### Community 244 - "Repository Map (OpenTrading)"
Cohesion: 0.33
Nodes (5): Canonical sources of truth, Domain glossary, Key facts for agents, Repository Map (OpenTrading), Target repository layout (architecture §27 — created in Phase 0)

### Community 245 - "Definition of Done"
Cohesion: 0.33
Nodes (5): Definition of Done, Evidence standard, Mandatory gates (all that apply to the task), Reporting, Review gates

### Community 246 - "initialize_vault"
Cohesion: 0.50
Nodes (4): initialize_vault(), Path, Create the canonical vault directory topology without touching data stores., test_initialize_vault_creates_the_canonical_layout()

### Community 247 - "Routing Rules — OpenTrading"
Cohesion: 0.33
Nodes (5): Anti-routing rules, Change classes → mandatory reviewers, Examples (canonical), Primary-agent matrix, Routing Rules — OpenTrading

### Community 248 - "10. Kill switch y Dead Man Switch"
Cohesion: 0.33
Nodes (6): 10. Kill switch y Dead Man Switch, Dead man, Emergency kill, Instrument kill, Portfolio kill, Strategy kill

### Community 249 - "Inspiración FinMem"
Cohesion: 0.33
Nodes (6): 11. Memoria: Graphiti + conceptos de FinMem, Inspiración FinMem, Long-term memory, Medium-term memory, Ontología de trading, Short-term memory

### Community 250 - "13. Arquitectura de datos"
Cohesion: 0.33
Nodes (6): 13. Arquitectura de datos, FalkorDB + Graphiti, MLflow, Parquet + MinIO, PostgreSQL + TimescaleDB, Redis

### Community 251 - "8. MetaTrader 4: solamente capa de ejecución"
Cohesion: 0.33
Nodes (6): 8. MetaTrader 4: solamente capa de ejecución, Canales propuestos, Por qué no WebRequest, Protocol, Transporte, Validaciones dentro del EA

### Community 252 - "Phase 7 — Execution state: broker reconciliation & Safe Mode (implemented)"
Cohesion: 0.33
Nodes (5): DoD evidence, Phase 7 — Execution state: broker reconciliation & Safe Mode (implemented), Reconciliation resolution matrix, State machine, What was built

### Community 253 - "engines/risk — Deterministic Risk & Policy Engine (Phase 5)"
Cohesion: 0.33
Nodes (5): Checks, Decision model (ADR-0018), Determinism, engines/risk — Deterministic Risk & Policy Engine (Phase 5), Usage

### Community 255 - "WireGuard — private transport for remote Windows MT4 deployments"
Cohesion: 0.33
Nodes (5): Hardening rules, Layout, Setup, Topology, WireGuard — private transport for remote Windows MT4 deployments

### Community 257 - "OpenTrading — Autonomous Quantitative Trading & Research Platform"
Cohesion: 0.33
Nodes (5): Canonical documents, Development, OpenTrading — Autonomous Quantitative Trading & Research Platform, Repository layout (per `docs/architecture.md` §27), Status

### Community 258 - "tests/conftest.py"
Cohesion: 0.53
Nodes (5): clock(), fixed_start(), datetime, fixture, Shared pytest fixtures.

### Community 259 - "test_import_guard.py"
Cohesion: 0.47
Nodes (4): _forbidden_imports(), AST, DoD guard: the domain layer (core/) imports no external trading framework.…, test_core_imports_no_external_trading_framework()

### Community 260 - "Cross-Review Rules"
Cohesion: 0.40
Nodes (4): Anti-patterns, Cross-Review Rules, Escalation ladder, How to detect the change class

### Community 261 - "apps/worker — Autonomous PAPER pipeline (Phase 7, ADR-0022)"
Cohesion: 0.40
Nodes (4): apps/worker — Autonomous PAPER pipeline (Phase 7, ADR-0022), Delivery & recovery, Layout, Run

### Community 262 - "CLAUDE.md — OpenTrading (Claude Code adapter)"
Cohesion: 0.33
Nodes (5): Bootstrap (read before working), CLAUDE.md — OpenTrading (Claude Code adapter), Managed engineering policy, Report, Working rules

### Community 265 - "ADR-0022: Autonomous PAPER pipeline — Redis Streams stages, idempotent run ledger, recovery semantics"
Cohesion: 0.40
Nodes (4): ADR-0022: Autonomous PAPER pipeline — Redis Streams stages, idempotent run ledger, recovery semantics, Consequences, Context, Decision

### Community 266 - "ADR-0023: Post-trade analysis & learning engine — deterministic postmortems with four sinks"
Cohesion: 0.40
Nodes (4): ADR-0023: Post-trade analysis & learning engine — deterministic postmortems with four sinks, Consequences, Context, Decision

### Community 267 - "ADR-0024: Emergency control system — kill switches and dead man switch"
Cohesion: 0.40
Nodes (4): ADR-0024: Emergency control system — kill switches and dead man switch, Consequences, Context, Decision

### Community 268 - "ADR-0025 — Security hardening milestone: trust zones, least privilege, secret lifecycle"
Cohesion: 0.40
Nodes (4): ADR-0025 — Security hardening milestone: trust zones, least privilege, secret lifecycle, Consequences, Context, Decision

### Community 269 - "ADR-0026 — LIVE_AUTO governance: automated live trading, disabled by default"
Cohesion: 0.40
Nodes (4): ADR-0026 — LIVE_AUTO governance: automated live trading, disabled by default, Consequences, Context, Decision

### Community 270 - "7. Risk Engine: componente más importante"
Cohesion: 0.40
Nodes (5): 7. Risk Engine: componente más importante, Controles, Entradas, Invariante, Resultado

### Community 271 - "Phase 7 — Post-trade analysis & learning engine (ADR-0023)"
Cohesion: 0.40
Nodes (4): Files, Key design points, Phase 7 — Post-trade analysis & learning engine (ADR-0023), Tests

### Community 272 - "engines/posttrade — Post-trade analysis & learning engine (Phase 7, ADR-0023)"
Cohesion: 0.40
Nodes (4): engines/posttrade — Post-trade analysis & learning engine (Phase 7, ADR-0023), Invariants, Layout, Metric definitions

### Community 273 - "mt4/ — MetaTrader 4 execution-only layer (Phase 6, INV-5)"
Cohesion: 0.40
Nodes (4): Layout, mt4/ — MetaTrader 4 execution-only layer (Phase 6, INV-5), Run the emulator / lifecycle, Status

### Community 274 - "tests/chaos — dedicated chaos/recovery suite"
Cohesion: 0.40
Nodes (4): Deterministic construction rules, Scenario matrix, tests/chaos — dedicated chaos/recovery suite, Validation properties (DoD)

### Community 275 - "Trade — 2c7c2d4f-fec5-5bdb-a428-4ebde0e0f237"
Cohesion: 0.40
Nodes (4): Canonical event snapshot, Summary, Trace, Trade — 2c7c2d4f-fec5-5bdb-a428-4ebde0e0f237

### Community 276 - "Context Usage Rules"
Cohesion: 0.50
Nodes (3): Budget discipline, Context Usage Rules, Maintenance

### Community 277 - "ADR Template"
Cohesion: 0.50
Nodes (3): ADR Template, Process, When an ADR is required

### Community 280 - "Routing Validation — OpenTrading"
Cohesion: 0.50
Nodes (3): Checks performed, Routing Validation — OpenTrading, Verified by design (not yet executable)

### Community 281 - "Strategy Validation Factory"
Cohesion: 0.50
Nodes (3): Evidence and PAPER eligibility, Required stages, Strategy Validation Factory

### Community 289 - "29. Seguridad"
Cohesion: 0.67
Nodes (3): 29. Seguridad, MT4, Secrets

### Community 290 - "4. Qlib + RD-Agent: fábrica cuantitativa autónoma"
Cohesion: 0.67
Nodes (3): 4. Qlib + RD-Agent: fábrica cuantitativa autónoma, Entorno separado, Qué podrá hacer nuestro Quant Factory

### Community 291 - "5. NautilusTrader: columna vertebral del trading"
Cohesion: 0.67
Nodes (3): 5. NautilusTrader: columna vertebral del trading, Función, Regla fundamental

## Knowledge Gaps
- **1062 isolated node(s):** `Read first (cheap bootstrap)`, `Routing`, `Context`, `Hard rules`, `Managed engineering policy` (+1057 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **101 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MarketSnapshot` connect `MarketSnapshot` to `DomainEvent`, `VirtualClock`, `worker/cli.py`, `repository.py`, `SignalDirection`, `mapper.py`, `mapping.py`, `Provenance`, `Timeframe`, `tradingagents/client.py`, `factories.py`, `make_market_snapshot`, `test_hashing.py`, `ConfigurableSlippageFillModel`, `test_client.py`, `evaluator.py`, `MarketDataRepository`, `test_versioning.py`, `build_domain_event`, `schemas/__init__.py`, `RepositorySnapshotSource`?**
  _High betweenness centrality (0.030) - this node is a cross-community bridge._
- **Why does `Clock` connect `Clock` to `schemas/execution.py`, `protocol.py`, `DomainEvent`, `OperatingMode`, `VirtualClock`, `SystemClock`, `SequenceTracker`, `execution_helpers.py`, `worker/cli.py`, `repository.py`, `FusionInputs`, `OrderRecord`, `OrderType`, `Settings`, `SimulatedBroker`, `make_submit`, `Provenance`, `normalization.py`, `OrderIntent`, `EmergencyController`, `Stack`, `LiveAutoRegistry`, `MemoryRecord`, `market_data/pipeline.py`, `test_hashing.py`, `Bar`, `MarketDataRepository`, `service.py`, `build_domain_event`, `StageWorker`, `datetime`, `RepositorySnapshotSource`, `ConnectionHealth`, `create_app`?**
  _High betweenness centrality (0.024) - this node is a cross-community bridge._
- **Why does `VirtualClock` connect `VirtualClock` to `tests/conftest.py`, `OperatingMode`, `SystemClock`, `execution_helpers.py`, `Clock`, `make_submit`, `Provenance`, `Timeframe`, `test_export.py`, `make_memory_episode`, `PositionSide`, `make_record`, `MemoryRecord`, `test_hashing.py`, `make_bar`, `MarketDataRepository`, `test_live_auto_api.py`, `test_versioning.py`, `build_domain_event`, `test_registry.py`, `test_process_crash.py`, `test_readyz.py`, `datetime`, `ConnectionHealth`, `create_app`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Are the 45 inferred relationships involving `VirtualClock` (e.g. with `_long_adapter()` and `_snapshot_event()`) actually correct?**
  _`VirtualClock` has 45 INFERRED edges - model-reasoned connections that need verification._
- **Are the 81 inferred relationships involving `Stack` (e.g. with `TestPostgresRestart` and `_service()`) actually correct?**
  _`Stack` has 81 INFERRED edges - model-reasoned connections that need verification._
- **Are the 83 inferred relationships involving `SignalDirection` (e.g. with `trade_outcome_from_position_closed()` and `build_committee()`) actually correct?**
  _`SignalDirection` has 83 INFERRED edges - model-reasoned connections that need verification._
- **Are the 40 inferred relationships involving `Clock` (e.g. with `Memory` and `MarketDataPipeline`) actually correct?**
  _`Clock` has 40 INFERRED edges - model-reasoned connections that need verification._