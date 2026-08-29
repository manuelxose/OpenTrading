# ADR-0016: MT4 as execution venue only

- Status: accepted
- Date: 2026-08-26
- Deciders: principal-architect (+ execution-mt4 + risk + security + verification for
  execution-sensitive class)

## Context

MetaTrader 4 is the execution venue, but it must never become the system's brain. The
decision was frozen in `docs/architecture.md` §34.17 ("MT4 será execution venue, no
cerebro") and detailed in §8; carried by INV-5.

## Decision

**MT4 hosts only a minimal execution bridge** — `mt4/Experts/QuantBridgeEA.mq4` (§8,
§27) — with the function:

```text
Receive command → Validate command → Broker validation → Send order → Return execution event
```

- All intelligence (signals, fusion, risk, sizing) lives in the Python core.
- Only Risk-Engine-approved `OrderIntent`s may ever reach the bridge (INV-1, INV-2).
- Transport is private ZeroMQ (frozen §34.18) over WireGuard when MT4 runs on a separate
  Windows host; sockets are never internet-exposed (§29).
- EA-side defense-in-depth validations apply even if the backend is compromised (§8):
  trading enabled, symbol whitelist, lot limit/step, spread limit, free margin, quote
  freshness, market open, stop/freeze level, duplicate `order_intent_id`, MagicNumber,
  command expiry.
- Execution is governed by mandatory reconciliation (§9): `send_order() !=
  executed_trade`; restart → reconcile DB vs broker; divergence → `SAFE_MODE`.

## Alternatives considered

- **Strategy logic inside MT4 (EAs as strategies)** — rejected: INV-5; untestable with
  our discipline; MQL4 is restricted to the bridge (ADR-0003).
- **Bypass MT4, trade via broker API/FIX directly** — rejected: frozen decision §34.17;
  the venue is MT4.
- **WebRequest-based transport** — rejected by §8: blocking, unavailable in Strategy
  Tester.
- **DWX Connect as production architecture** — rejected: reference only (§2, §8); its
  docs warn it is not meant for backtesting.

## Consequences

- Positive: broker layer is replaceable and contained; defense-in-depth at the last mile;
  clear authority boundary (Zone 3, §29).
- Negative: MQL4/ZeroMQ bridge engineering and Windows networking are non-trivial —
  Phase 6, demo account first.
- Follow-ups: Phase 6 DoD — sending the same `order_intent_id` 100 times never produces
  more than one trade; Phase 8 exercises disconnect/restart/duplicate/rejection/partial
  fill scenarios.

## Validation

- Frozen decisions §34.17 + §34.18; §8 (channels, protocol fields, EA validations);
  §9 (reconciliation); INV-5.
- `.ai/agents/execution-mt4.md`: forbidden strategy logic in MQL4 and internet-exposed
  sockets.
- Repo evidence: no MT4 artifacts yet (PRE-00) — this ADR binds their first version.
