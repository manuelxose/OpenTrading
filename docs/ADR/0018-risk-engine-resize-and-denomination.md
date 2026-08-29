# ADR-0018: Risk Engine — RESIZE decision and exposure denomination

- Status: accepted
- Date: 2026-08-26
- Deciders: principal-architect (+ risk + verification for risk-sensitive class)

## Context

ADR-0015 fixes the Risk Engine as 100% deterministic code with `APPROVE` /
`REJECT` outputs. Implementing it surfaced two decisions the frozen
architecture does not answer: (a) what happens when a proposal's size is
reducible to a safe quantity instead of being rejected outright, and (b) in
which currency monetary limits are denominated before an FX-rate feed exists.

## Decision

**Three decision types.** `RiskDecisionType` gains `RESIZE`:

- `APPROVE` — the proposal quantity is accepted unchanged (no reason codes).
- `RESIZE` — the engine approves a reduced, engine-computed quantity and
  carries both the approved values and the `reason_codes` that bounded the
  size (e.g. `RISK_LIMIT_EXCEEDED`, `EXPOSURE_LIMIT_EXCEEDED`,
  `INSUFFICIENT_MARGIN`, `LOT_STEP_INVALID`).
- `REJECT` — a hard violation that resizing cannot fix (stale quotes, daily
  loss breach, disabled strategy, cooldown, …); never carries approved values.

The approved quantity is **always** computed by the Risk Engine (INV-1): the
engine derives a maximum quantity from every soft limit, floors it to the
instrument lot step, clamps it to the effective min/max, and re-verifies every
limit with exact Decimal arithmetic before approving. An LLM "BUY 100 lots"
can only become a REJECT or a reduced RESIZE. New reason codes:
`RISK_LIMIT_EXCEEDED`, `MAX_POSITIONS_REACHED`, `MAX_ORDERS_REACHED`.

**Exposure denomination.** Monetary limits (`max_risk_per_trade`,
exposure limits, leverage, margin) are denominated in the account currency;
the proposal's notional is approximated in the instrument **quote currency**
until an FX-rate feed exists (follow-up: FX conversion via the market-data
platform). Portfolio aggregates (`PortfolioExposure`) are produced by the
portfolio engine and consumed by the Risk Engine; the Risk Engine re-verifies
the proposed trade against them with exact arithmetic.

**Determinism.** The engine is a pure function of its inputs (no state, no IO,
no wall clock). `inputs_hash` is a SHA-256 over the canonical JSON of all
decision-relevant fields; the decision id is a UUIDv5 over that hash, so
identical inputs produce identical decisions. Checks are evaluated in a fixed
canonical order, so reason-code lists are deterministic.

## Alternatives considered

- **REJECT whenever a limit is exceeded** — rejected: it would make any
  marginally oversized proposal untradeable and push users to game the system;
  RESIZE keeps the LLM advisory while the engine decides capital (INV-1).
- **Convert currencies today** — rejected: no FX-rate feed exists yet; building
  one inside the Risk Engine would couple it to market data and break its
  purity. The quote-currency approximation is explicit and fail-closed.
- **Trust portfolio aggregates without re-verification** — rejected: the
  engine re-checks every soft limit with exact arithmetic (multiplication
  only, no rounded division), so a one-ulp rounding of a derived cap can never
  let a size through.

## Consequences

- Positive: capital authority is mechanical; RESIZE makes the engine usable
  without weakening any limit; every decision is reproducible and auditable
  via `inputs_hash`.
- Negative: denomination approximation until FX rates land; `PortfolioExposure`
  is a trust boundary (produced by our own portfolio engine).
- Follow-ups: FX conversion (ADR when implemented), turnover and correlated-
  cluster controls, safe-mode event payload (`system.safe_mode.*`), policy
  versioning service.

## Validation

- INV-1, INV-4, §7 inputs/controls/outputs; ADR-0015.
- `tests/risk/`: unit, boundary, invariant, Hypothesis property-based and
  seeded-fuzz suites enforce "approved risk ≤ policy risk", "approved
  quantity ≤ configured maximum", and the blocking invariants (daily loss
  breach, stale data, disabled strategy) for arbitrary inputs.
- 682 tests green in `make ci` (2026-08-26).
