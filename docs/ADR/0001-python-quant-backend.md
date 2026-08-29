# ADR-0001: Python as the quantitative backend language

- Status: accepted
- Date: 2026-08-26
- Deciders: principal-architect (+ verification for architecture-wide class)

## Context

The platform needs one implementation language for the quantitative backend: domain
core, engines (risk, fusion, posttrade), workers, API, and execution gateway. The
decision was frozen in `docs/architecture.md` §34.1 ("Python es el lenguaje principal
del backend cuantitativo") and is carried by invariant INV-13 (two runtimes, never
merged).

## Decision

**Python is the sole backend language.**

- Core runtime: **Python 3.12** — TradingAgents adapters, Graphiti adapters, Nautilus,
  FastAPI, Risk Engine, workers, execution gateway.
- Quant R&D runtime: **Python 3.11 on Linux** — RD-Agent, Qlib, MLflow (§4). The two
  runtimes are never merged into one virtualenv.

## Alternatives considered

- **Python + Rust/C++ hybrid** — rejected: premature complexity; no latency requirement
  justifies it before profiling evidence exists (§5 gives Nautilus the execution-path
  role, which already covers performance-critical paths).
- **Full TypeScript backend** — rejected: Qlib/RD-Agent/TradingAgents/Nautilus are
  Python-native; reimplementation or interop would violate the "no rewriting upstream"
  decision (§3, §4).
- **Single runtime for everything** — rejected explicitly by §4/INV-13: RD-Agent's
  stack is safest on Python 3.10/3.11 while the core targets 3.12.

## Consequences

- Positive: direct integration with the four adopted upstream projects; one mental model
  for the domain; INV-13 gives a clean isolation boundary for the fragile R&D stack.
- Negative: two runtimes require a serialization contract between core and quant R&D
  (satisfied by the canonical domain objects, §15, and the event envelope, §14).
- Follow-ups: Phase 0 must establish both runtimes' skeletons and dependency pinning
  (`external-lock.yaml`, INV-14).

## Validation

- Frozen decision §34.1 unchanged since architecture v1.0 (2026-08-26).
- Consistent with INV-13, §4 (runtimes), §27 (target layout `services/`).
- No contradictory repository evidence: repo is PRE-00, no code exists yet
  (`docs/architecture/CURRENT_STATE.md`).
