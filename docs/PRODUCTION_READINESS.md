# Production Readiness — OpenTrading

- **Audit date:** 2026-08-29
- **Scope:** full platform audit (architecture, dependencies, data correctness,
  point-in-time guarantees, TradingAgents / Graphiti / Qlib-RD-Agent isolation,
  Nautilus consistency, Risk Engine, MT4 execution, reconciliation, idempotency,
  promotion governance, security, observability, disaster recovery, testing,
  documentation, performance).
- **Evidence run this audit:** full test suite, chaos suite, a complete
  deterministic PAPER cycle, the LIVE_GATED / LIVE_AUTO demo-account lifecycle
  suites, the MT4 protocol smoke lifecycle over real ZeroMQ loopback, static
  searches (secrets, TODOs, dead code, `datetime.now`, trace IDs, unversioned
  schemas), and three specialist code audits (Risk/Nautilus/Quant-R&D;
  TradingAgents/Graphiti/Fusion/Posttrade/Worker; Security/Infra/Observability/DR).

## Verdict

**The platform is NOT declared production-ready for live capital.**

The deterministic core (data platform, Risk Engine, MT4 protocol + emulator,
execution state + reconciliation, paper pipeline, emergency controls,
LIVE_GATED / LIVE_AUTO governance) is implemented, heavily tested and
audit-grade. What is missing for a production declaration is operational
maturity around live trading, not architecture:

1. **No production path produces live OrderIntents yet.** The worker pipeline is
   hard-blocked from LIVE_GATED / LIVE_AUTO modes by design (INV-1, ADR-0025);
   the human-approval gate, the live-auto registry and the MT4 client are fully
   built and tested in-process and against the emulator, but no production
   service wires a live signal → risk → intent → gate → MT4 flow today. This is
   intentional sequencing, and it means live readiness has not been exercised
   outside the emulator.
2. **No automated backups and no restore runbook existed before this audit**
   (scripts + runbook added here, still not exercised against a production host).
3. **No real MT4 / demo broker has ever been connected** — the wire protocol is
   verified only against the Python emulator and `QuantBridgeEA.mq4` remains to
   be built against the protocol spec.
4. **INV-16 calibration governance** was not enforced at runtime until this
   audit (uncalibrated fusion configs are now rejected).
5. **DB-level immutability of the audit trail** was a code convention only
   (now enforced by migration `0009_audit_trail_immutability`).
6. The `OrderIntent.quantity` unit convention (base units on simulated venues,
   lots on live venues) is now documented but must be re-verified when the live
   producer path is wired.

> Definition of Done for live capital remains: connect a reconciled demo account,
> replay the live lifecycle through the real bridge, run the backup/restore
> drill, and complete the Phase 8 wiring with the quantity-unit check.

## What is production-grade today

| Area | Status | Evidence |
|---|---|---|
| Domain contracts + event envelope | ✅ | All 20 contracts + `DomainEvent` carry `schema_version`, `trace_id`, `produced_at`, provenance; schema pinning validators reject mismatches |
| Point-in-time data platform | ✅ | RAW→BRONZE→SILVER→GOLD→`MarketSnapshot` with three timestamps per record, hash-sealed gold versions, single INV-3 filter choke point, leakage suite |
| Risk Engine (INV-4) | ✅ | Pure deterministic function, zero LLM/clock imports, `APPROVE/RESIZE/REJECT` with `reason_codes` + `policy_version`, exact-arithmetic size gate, property tests |
| MT4 protocol (ADR-0020) | ✅ | Versioned 13-message ZeroMQ vocabulary, idempotency ledger, sequence validation, checksums, expiry; emulator implements the full lifecycle; 100× same `order_intent_id` ⇒ one trade |
| Execution state + reconciliation (INV-6) | ✅ | SUBMITTED persisted before wire send; 7-step restart reconciliation; SAFE_MODE on material divergence; crash/partition/duplicate-fill chaos tests |
| Emergency controls + dead man switch (INV-7) | ✅ | 4 kill levels, persisted policy, cron-able `check-emergency`, deterministic emergency authorizer for flatten/cancel |
| LIVE_GATED human gate | ✅ | HMAC-bound approvals, TTL, quote-drift revalidation, fail-closed mutation authorizer, operator API behind constant-time token auth |
| LIVE_AUTO governance (Phase 11) | ✅ | Disabled by default; promotion only LIVE_GATED→LIVE_AUTO via authenticated operator action writing an immutable audit event; per-submission registry checks + loss ledger |
| Paper pipeline (Phase 7) | ✅ | Full research→fusion→proposal→risk→intent→execution→positions→posttrade loop, idempotent stages, PEL reclaim + dead-lettering, restart recovery tests |
| Isolation (INV-1/9/11/13) | ✅ | TradingAgents advisory-only; Graphiti PIT double-filtered; qlib/rdagent confined to a 3.11 runtime without execution imports, env guards, read-only container; worker refuses live modes |
| Security (ADR-0025) | ✅ | Least-privilege DB roles, Redis ACL, scoped MinIO policies, FalkorDB requirepass, redacting logging, gitleaks + pip-audit in CI, threat model with controls C1–C13 |
| Testing | ✅ | 1 200+ tests green: unit, property-based risk, leakage, determinism, replay, execution, security, chaos (25 in-process chaos scenarios), integration markers for the compose stack |

## Blocking issues: status after this audit

| # | Issue | Severity | Fix this audit |
|---|---|---|---|
| B1 | Empty/weak `OT_LIVE_OPERATOR_TOKEN` could admit `Authorization: Bearer ` | BLOCKING (security) | ✅ `Settings` now requires ≥32-char live secrets |
| B2 | `audit_events`/`system_events` were UPDATE/DELETE-able by app roles — immutability was convention-only | BLOCKING (governance) | ✅ migration `0009` revokes DML + adds append-only triggers |
| B3 | Stage outputs were published **after** the SUCCEEDED run record — a mid-publish crash silently lost downstream events | BLOCKING (data correctness) | ✅ publish now happens **before** the SUCCEEDED mark; downstream stages dedupe on `(trace_id, stage)` |
| B4 | Double-close race: SL/TP exits could be proposed twice while the first close chain was still pre-SUBMITTED | MAJOR (execution safety) | ✅ close-in-flight guard now covers `CANDIDATE/APPROVED/ORDER_INTENT` + pending close lifecycles |
| B5 | Future-dated quote timestamps bypassed the staleness gate (negative age) | MAJOR (risk) | ✅ negative age now fails closed as stale |
| B6 | Uncalibrated fusion configs (`version="uncalibrated"`) were executable — INV-16 convention-only | MAJOR (governance) | ✅ `FusionConfig` rejects uncalibrated versions |
| B7 | Unseeded random UUID for Nautilus `init_id` inside the deterministic backtest path | MINOR (reproducibility) | ✅ derived deterministically from `client_order_id` |
| B8 | Quant-R&D runtime never asserted Python 3.11 at runtime (INV-13) | MINOR (isolation) | ✅ `assert_runtime_version()` at bootstrap |
| B9 | `OrderIntent.quantity` unit semantics undocumented (base units vs lots) | MAJOR (latent, fail-closed today) | ✅ documented on the schema + known-limitation entry; re-verify at live wiring |
| B10 | No automated backup / restore tooling or RPO/RTO | MAJOR (DR) | ✅ `scripts/backup.sh` + `scripts/restore.sh` + `docs/DISASTER_RECOVERY.md` (drill still required) |

All remaining findings are non-blocking and recorded in `docs/KNOWN_LIMITATIONS.md`.

## Open items before live capital (gates)

1. **Real demo broker connection**: run `reconcile-once` and the live lifecycle
   against a real MT4 demo account through the WireGuard tunnel; build
   `QuantBridgeEA.mq4` per `mt4/protocol/README.md`.
2. **Live producer wiring**: implement the gated producer that builds
   LIVE_GATED intents in **lots** (per the documented unit convention) and feeds
   the human-approval API; add an end-to-end test with the emulator in
   LIVE_GATED mode.
3. **Backup/restore drill**: schedule `scripts/backup.sh` (e.g. systemd timer /
   cron), and restore into a scratch Postgres once per quarter.
4. **Prometheus scrape path for the core runtime** on the prod internal network
   (currently `host.docker.internal` in dev only).
5. **Resource limits** (`mem_limit`/`cpus`) in `docker-compose.prod.yml`.
6. **Calibrate fusion weights for production** (the paper pipeline currently
   runs `paper-fusion-v1` equal weights — legal under the new validator but
   hand-set; run the calibration engine on labeled history before live).
7. **RPO/RTO acceptance test** against the targets in `DISASTER_RECOVERY.md`.

## Verification matrix (how to re-audit)

```bash
make lint && make typecheck && make test          # static + full suite
uv run pytest tests/chaos                          # chaos (in-process)
uv run python -m apps.worker run-once --llm mock  # one deterministic PAPER cycle
uv run python -m adapters.mt4.cli smoke           # MT4 protocol lifecycle over ZeroMQ
uv run pytest tests/execution tests/live_auto tests/security tests/unit/apps   # LIVE_GATED/LIVE_AUTO lifecycle
uv run alembic heads                              # migration chain (0009 head)
bash -n scripts/backup.sh scripts/restore.sh
gitleaks git --redact && uvx pip-audit -r <(uv export --all-groups --format requirements-txt)
```

Any trade must be reconstructable end to end: `trace_id` →
`system_events` (event log) → `pipeline_runs` (stage attempts) →
`execution_orders` / `execution_positions` (authoritative execution state) →
`reconciliation_runs` (broker truth) → `audit_events` (append-only governance)
→ posttrade artifacts and memory episodes (learning trail). This chain is the
Definition of Done and is exercised by the test suite today.
