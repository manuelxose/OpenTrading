# ADR-0002: TypeScript for the Command Center

- Status: accepted
- Date: 2026-08-26
- Deciders: principal-architect (+ command-center + backend-platform as supporting)

## Context

The platform needs a web UI for human oversight: Overview, Research, Signals, Risk,
Orders & Trades, Memory, Backtests, Agents, System (`docs/architecture.md` §26). The
decision was frozen in §34.2 ("TypeScript será el Command Center").

## Decision

**The Command Center is a TypeScript web application** (`apps/command-center` in the
target layout, §27). It is a thin presentation layer over the Python backend APIs.

The browser holds **no business logic**: no risk/sizing reimplementation, no trading
logic client-side, no secrets, no execution sockets (per `.ai/agents/command-center.md`
forbidden list).

## Alternatives considered

- **Python-rendered UI (server templates)** — rejected: interactive charts, real-time
  updates, and agent-trace exploration favor a SPA; §26 explicitly calls for a custom
  web UI rather than log terminals.
- **Desktop app (Electron/Tauri)** — rejected: unnecessary; a web dashboard with proper
  auth serves the single-operator use case.
- **No UI, terminal only** — rejected by §26 ("No necesitamos una terminal llena de
  logs").

## Consequences

- Positive: clean client/server boundary matching the trust-zone model (§29); modern
  charting/UX ecosystem; TypeScript enforces API contracts on the client.
- Negative: a second language in the repo — mitigated by keeping the Command Center
  contract-first (`api-contract-review` skill, `backend-platform` collaboration).
- Follow-ups: API contracts between `apps/api` and `apps/command-center` are
  architecture-wide artifacts; UI changes receive proportional UI review
  (`.cursor/rules/00-canonical.mdc`).

## Validation

- Frozen decision §34.2; target layout §27 (`apps/command-center`).
- `.ai/agents/command-center.md` defines the exact screen set of §26 and the forbidden
  behaviors.
- Repo evidence: no UI exists yet (PRE-00), so no conflicting stack is present.
