# ADR-0027 — Standalone XAUUSD Regime-Filtered Pullback→Breakout Expert Advisor

- Status: Accepted
- Date: 2026-08-31
- Deciders: Lead engineer (quant engineering mandate), Principal Architect review pending
- Supersedes: none
- Related: ADR-0020 (MT4 execution protocol), INV-1, INV-2, INV-4, INV-5, INV-8, INV-12

## Context

The mandate (`docs/strategy/XAUUSD_RPB_SPEC.md`) requires a professional, self-contained
XAUUSD Expert Advisor for MetaTrader 4 implementing the **Regime-Filtered
Pullback → Breakout** strategy family, including regime detection, a pullback state
machine, breakout confirmation, broker-aware position sizing, kill switches, restart
recovery, shadow mode and telemetry — all resident inside MQL4 and able to run without
the OpenTrading Core.

This collides with two standing rules of this repository:

- **INV-5 — MT4 is execution-only.** `QuantBridgeEA.mq4` must remain minimal
  (receive → validate → broker-validate → send → report) and *"strategy intelligence
  never migrates into MQL4"*.
- **INV-12** lists *"MQL4 only in bridge"* among the frozen decisions, which may only be
  revisited through an ADR — hence this document.

Doing nothing is not viable: the mandate is explicit and was reaffirmed in detail. Silently
violating INV-5 is also not viable: the invariant exists so that a single strategy
definition cannot fork into divergent implementations (INV-2) and so that capital decisions
stay in reviewable, testable, deterministic code (INV-1/INV-4).

## Decision

We introduce a **second, clearly separated MT4 artifact class** rather than weakening the
existing one.

1. `mt4/Experts/QuantBridgeEA.mq4` **remains execution-only and unchanged**. INV-5 continues
   to hold, without exception, for the bridge. Nothing in this ADR permits strategy logic to
   enter the bridge.

2. A new artifact `mt4/Experts/XauRpbEA.mq4` is added as a **standalone autonomous EA**. It
   is explicitly *outside* the Core execution path: it never speaks the ADR-0020 protocol,
   never receives an `OrderIntent`, and is never driven by the Core.

3. The **canonical strategy definition is the Python implementation** in
   `research/strategies/xau_rpb/`, frozen by `docs/strategy/XAUUSD_RPB_SPEC.md`. The MQL4 EA
   is a *mirror* of that specification, not an independent source of truth. Divergence is a
   defect, and **signal-parity tests** (`tests/parity/`) are the mechanism that keeps the two
   honest: identical OHLC input must produce identical regime, state, direction, entry bar
   and stop distance.

4. The standalone EA is bound to the operating-mode ladder of INV-8. It ships defaulting to
   `SHADOW` (signal-only, no `OrderSend`), and reaching real capital requires the normal
   promotion lifecycle. INV-1 is unaffected: **no LLM participates in this strategy at all** —
   every rule is deterministic arithmetic over closed bars.

## Consequences

**Positive**

- The mandate is satisfied without eroding the bridge or the Core architecture.
- The strategy is testable outside MetaTrader, in CI, at Python speed.
- Parity tests make the two implementations mutually verifying rather than divergent.
- INV-1/INV-4 are structurally preserved: risk arithmetic is deterministic and the EA
  fails closed.

**Negative / accepted costs**

- Two implementations of one strategy exist. This is a real duplication cost and is
  mitigated, not eliminated, by the parity fixtures. Any spec change must be applied to
  both implementations in the same change set.
- The standalone EA cannot reuse `engines/risk` at runtime; its risk controls are a
  re-implementation of the same policy and must be reviewed against
  `docs/strategy/RISK_POLICY.md` whenever either side changes.
- INV-5's scope narrows from "MQL4" to "the QuantBridge execution path". The invariants
  file must be read together with this ADR.

**Neutral**

- If the strategy is later promoted into the Core, the Python implementation is already the
  canonical one and can emit `OrderIntent` (INV-2) with no rewrite; the standalone EA would
  then become redundant rather than conflicting.

## Alternatives considered

- **Implement the strategy Core-side only, keep MT4 dumb.** Fully INV-5 compliant, but does
  not deliver the requested artifact: the mandate requires an EA that runs on MT4 without
  the Core, including on a broker VPS with no Python.
- **Put the strategy inside `QuantBridgeEA.mq4` behind a flag.** Rejected: it makes the
  audited execution bridge conditionally intelligent, which is precisely the failure mode
  INV-5 was written to prevent.
- **Amend INV-5 outright.** Rejected as disproportionate: the invariant is correct for the
  Core path; only a bounded, named exception is warranted.
