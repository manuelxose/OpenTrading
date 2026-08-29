# Known Limitations — OpenTrading

- **Date:** 2026-08-29
- **Convention:** each entry is classified `BLOCKING` / `MAJOR` / `MINOR` /
  `INFO`. `BLOCKING` items must be resolved before live capital (none remain
  open — see `PRODUCTION_READINESS.md` for the closed list). MAJOR items are
  tolerable for paper/demo operation but must be closed before live. MINOR/INFO
  items are tracked here so they are never mistaken for unknown behavior.

## Execution & venues

1. **No real broker has ever been connected.** The MT4 protocol is verified
   against the Python emulator (`adapters/mt4/emulator.py`) only;
   `QuantBridgeEA.mq4` is not yet built. *(MAJOR, pre-live gate)*
2. **`OrderIntent.quantity` unit convention.** Simulated venues
   (BACKTEST/PAPER) carry **base units** (approved lots × contract_size);
   live venues (LIVE_GATED/LIVE_AUTO) carry **lots** and the live gates compare
   `quantity == approved_quantity`. Both are fail-closed today, but the live
   producer (not yet built) must convert at the boundary — re-verify at wiring.
   *(MAJOR, pre-live gate; documented on the schema field)*
3. **Backtest path bypasses the Risk Engine** by design: the backtest baseline
   emits intents with a synthetic `risk_decision_id` and strategy-config
   quantity. Simulation-only; must never be copied into the paper/live path.
   *(INFO)*
4. **Nautilus `StrategyContext` exposes `bars_remaining` / `is_last_bar`**, which
   are horizon lookahead for any strategy other than the baseline exit. The
   leakage suite would flag any other consumer; restrict to the baseline or
   document explicitly. *(MINOR)*
5. **Nautilus/FX-only scope.** `instrument_to_nautilus` supports FX only, and
   `PositionLedger` supports accounts quoted in the pair's quote or base
   currency; anything else raises `NotImplementedError` loudly. *(INFO, by
   design — ADR-0007 Phase 4 scope)*
6. **Commission model is quote-currency-denominated**, matching the documented
   USD-account / EURUSD scope; cross-currency accounts need a model extension.
   *(MINOR)*
7. **`code_sha()` shells out to `git rev-parse HEAD`** for the backtest input
   fingerprint; degrades to a constant outside a git repo. *(INFO)*
8. **Live intent producers do not exist in production code.** LIVE_GATED /
   LIVE_AUTO are fully implemented and tested as engines, API surfaces and
   client-side authorizers, but the signal→risk→live-intent producer is a
   Phase 8 wiring task (see `PRODUCTION_READINESS.md` open items). *(MAJOR,
   pre-live gate)*

## Worker pipeline

9. **Stage output publishing is at-least-once with downstream dedupe.** After
   the publish-before-SUCCEEDED fix, a crash mid-publish re-runs the stage and
   re-publishes; downstream stages dedupe on `(trace_id, stage)`, but the
   stream can contain duplicate envelope copies. *(INFO)*
10. **Redis PEL reclaim pages only the first 100 pending entries per pass**
    (`bus.pending()` default cap) — deep backlogs delay dead-lettering of
    poisoned messages beyond the first page. *(MINOR)*
11. **Graphiti live store keeps an in-process `_envelopes` index**; after a
    worker restart, previously ingested LONG_TERM episodes are invisible
    (fail-closed) until re-ingested. *(MINOR)*
12. **Episode content schema is unversioned** (`content.direction` lessons
    written by the posttrade stage are read back by `MemoryContextProducer`);
    version the lesson schema before changing the loop. *(MINOR)*
13. **Timed-out TradingAgents threads keep burning upstream cost** (they cannot
    be killed); add a run-level token/cost cap before long unattended runs.
    *(MINOR)*

## Risk & fusion

14. **Fusion weights in the paper pipeline are hand-set equal weights**
    (`paper-fusion-v1`, 2500 bp each). Legal under the new INV-16 validator but
    not historically calibrated; calibrate on labeled history before live
    (INV-16 requires quant-only / llm-only / quant+llm / baseline comparison).
    *(MAJOR, pre-live)*
15. **`ConfidenceMap` calibration is per-producer optional**; unknown producers
    keep raw confidence. *(INFO)*

## Security

16. **DB-level audit immutability is now enforced** (migration `0009`), but the
    dev compose's single `opentrading` user remains superuser-equivalent; use
    the least-privilege roles in production only. *(INFO)*
17. **`/metrics` is unauthenticated** by design; keep it behind the internal
    network / reverse proxy in live modes. *(MINOR, ops note)*
18. **`.sops.yaml` carries a placeholder age recipient**; encryption recipients
    are CLI-supplied. Add a CI `sops --decrypt` smoke test once a real recipient
    exists. *(MINOR)*
19. **Redis exporter ACL includes `+CONFIG|GET +CLIENT +SLOWLOG`** — broader than
    strictly needed for metrics; verify against the pinned exporter version.
    *(MINOR)*
20. **Langfuse dev `LANGFUSE_ENCRYPTION_KEY` is a sequential placeholder**; prod
    compose fails closed on it, but dev teams should generate a real one.
    *(MINOR)*
21. **`trace_id` is deliberately `NULL` on platform-level events** (safe-mode,
    reconciliation, emergency actions); the worker pipeline drops inbound
    events without trace IDs. Documented semantics, not a bug. *(INFO)*

## Infrastructure & observability

22. **No per-service resource limits** (`mem_limit` / `cpus`) in the compose
    files — a runaway Langfuse/ClickHouse can exhaust the host. *(MINOR)*
23. **Prod Prometheus cannot scrape the core runtime** (dev target
    `host.docker.internal:8000` is unreachable from the internal network).
    *(MINOR)*
24. **`services/core-runtime/` is a README-only placeholder** — the 3.12 side of
    INV-13 exists as package layout; no production Dockerfile/compose service
    for the core runtime yet. *(MAJOR, pre-live deployment)*
25. **Five upstream projects (TradingAgents, Graphiti, Qlib, RD-Agent, MLflow)
    are pinned by commit SHA in `external-lock.yaml` but installed outside
    `uv.lock`** via side `uv pip install` commands, so their transitive
    dependencies are not lockfile-verified. *(MAJOR, supply chain)*
26. **`external-lock.yaml` has contradictory Graphiti entries** (integrated
    `graphiti-core[falkordb]==0.29.3` vs a second not-integrated entry) and
    marks NautilusTrader "not integrated" although it is a locked runtime
    dependency. *(MINOR, doc hygiene)*
27. **`services/quant-rd` has no lockfile** (requirements.txt only). *(MINOR)*

## Documentation & repository

28. **`README.md` and `docs/architecture/CURRENT_STATE.md` / `IMPLEMENTATION_ORDER.md`
    status sections are stale** (they still claim Phases 2–12 are not started).
    Corrected references are in this audit's docs; the source files should be
    refreshed. *(MINOR, doc hygiene)*
29. **Git history is a single commit** (`01462f8`); everything else is
    uncommitted working tree. No tagged releases, no changelog. *(MINOR, release
    hygiene)*
30. **`AGENTS.md` / `CLAUDE.md` adapters still describe PRE-00** ("docs only, no
    code yet"). *(MINOR)*

## Performance

31. **No load/throughput benchmarks exist** (API, paper cycle, MT4 roundtrip,
    market-data ingestion). Paper cycle latency is dominated by the
    cycle interval (300 s default) and the LLM timeout budget (300 s); execution
    and reconciliation are measured per run but not under load. *(MINOR — add
    benchmarks before claiming performance characteristics)*

## Resolution policy

- `BLOCKING`: must be closed before live capital; tracked in
  `PRODUCTION_READINESS.md`.
- `MAJOR`: close before the corresponding milestone (live wiring, live
  deployment).
- `MINOR`/`INFO`: accepted for current modes (research/backtest/paper/live
  gates vs emulator), reviewed at each release.
