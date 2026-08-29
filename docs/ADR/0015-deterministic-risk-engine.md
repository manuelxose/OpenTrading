# ADR-0015: Deterministic Risk Engine (no LLM authority over capital)

- Status: accepted
- Date: 2026-08-26
- Deciders: principal-architect (+ risk + verification for risk-sensitive class)

## Context

The single most important component of the platform. The decision combines frozen item
§34.19 ("Los LLM nunca controlarán directamente lotaje o capital") with §7 and the
absolute rule of §1. Carried by INV-1 and INV-4.

## Decision

**The Risk Engine + Policy Engine are 100% own deterministic code** (§7):

```text
TradeProposal → Policy Engine → Risk Engine → APPROVE / REJECT
```

- No LLM, no agent, no prompt, no probabilistic interpretation, no bare
  `{"approved": true}`.
- Inputs: NAV, equity, free margin, open positions, pending orders, market price, spread,
  volatility, correlations, liquidity, proposed stop, instrument rules, strategy and
  portfolio risk budgets, daily PnL, drawdown, quote freshness, heartbeat,
  reconciliation state.
- Controls (minimum set): per-trade risk, total exposure, per-instrument/asset-class/
  currency exposure, correlated clusters, leverage, simultaneous orders/positions, daily
  loss, rolling drawdown, max spread/slippage, min stop, min/max size, lot step, margin,
  turnover, loss-sequence cooldown, trading hours, event restrictions, strategy active,
  symbol whitelist, broker connected, heartbeat, reconciliation (§7).
- Outputs: `REJECT {reason_codes[]}` or
  `APPROVE {approved_quantity, approved_stop, risk_amount, policy_version}`.

Even a hypothetical LLM instruction "BUY EURUSD, 100 lots" can only become `REJECT` or
a reduced size — the LLM never has the last word (§7, INV-1).

## Alternatives considered

- **LLM-assisted risk judgment** — rejected absolutely: §1/§7/INV-1; interpretability,
  auditability and property-testability require determinism.
- **Rule engine framework (Drools-style)** — rejected: a Python-native, unit/property
  tested engine is mandated (§7, §30) and avoids a second runtime.
- **Outsource risk to MT4/broker** — rejected: INV-5 keeps MT4 dumb; the broker is not
  our risk system.

## Consequences

- Positive: the authority-over-capital barrier is mechanical, testable, auditable.
- Negative: full control set is substantial engineering — scheduled as Phase 5 with
  property-based tests (`risk > limit → NEVER APPROVE`; `approved lot <= configured max`;
  duplicate `order_intent_id → NEVER SECOND ORDER`).
- Follow-ups: policy versions recorded (`policy_version`), kill switches (INV-7) owned
  by this engine; any limit change is risk-sensitive class → `risk` + `verification`.

## Validation

- Frozen decisions §34.19 + §34.20 context; §7 (inputs/controls/outputs); §1 absolute
  rule; INV-1, INV-4.
- `.ai/agents/risk.md`: forbidden LLM-based decisions and bare approvals.
- Repo evidence: no risk code yet (PRE-00) — this ADR binds its first implementation.
