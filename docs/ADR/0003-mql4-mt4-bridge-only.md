# ADR-0003: MQL4 exists only in the MT4 execution bridge

- Status: accepted
- Date: 2026-08-26
- Deciders: principal-architect (+ execution-mt4 + security + risk + verification for
  execution-sensitive class)

## Context

MetaTrader 4 requires MQL4 for terminal-side code. The risk is strategy intelligence
migrating into the EA, creating an unmaintainable second implementation. The decision
was frozen in `docs/architecture.md` §34.3 ("MQL4 solo existirá en el Execution Bridge")
and is carried by INV-5 (MT4 is execution-only).

## Decision

**MQL4 is restricted to the execution bridge**, concretely one deliberately small EA:
`mt4/Experts/QuantBridgeEA.mq4` (§8, §27). Its entire function is:

```text
Receive command → Validate command → Broker validation → Send order → Return execution event
```

No signals, no strategy logic, no risk policy, no analytics in MQL4. The EA does carry
defense-in-depth validations (§8): trading enabled, symbol whitelist, lot limit/step,
spread limit, free margin, quote freshness, market open, stop/freeze level, duplicate
`order_intent_id`, MagicNumber, command expiry.

## Alternatives considered

- **Strategy logic inside the EA** — rejected: violates INV-5; duplicates the Python
  domain; impossible to test with the repository's Python test discipline (§30).
- **MQL5 / cTrader instead of MQL4** — rejected as a separate concern: the venue decision
  is MT4 (ADR-0016); the language follows the venue.
- **WebRequest()-based bridge** — rejected by §8: synchronous blocking call, unavailable
  in Strategy Tester; not a valid execution path.

## Consequences

- Positive: single Python source of truth for behavior; EA stays testable and reviewable
  as a dumb terminal; defense-in-depth remains even if the backend is compromised.
- Negative: MQL4 is a legacy C-like language with limited tooling — scope is kept
  minimal precisely to contain this.
- Follow-ups: Phase 6 delivers the EA plus protocol tests; execution-sensitive review
  is mandatory for every MQL4 change (`.ai/rules/cross-review-rules.md`).

## Validation

- Frozen decision §34.3; §8 (transport, channels, protocol fields, EA validations);
  INV-5.
- `.ai/agents/execution-mt4.md` scope: `mt4/`, protocol, idempotency, reconciliation;
  forbidden: strategy logic in MQL4.
- Repo evidence: no MQL4 files exist yet (PRE-00) — decision constrains the first ones.
