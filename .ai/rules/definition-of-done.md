# Definition of Done

No agent may declare a task complete merely because code was generated.

## Mandatory gates (all that apply to the task)

1. **Implemented** — code exists and is wired into the real path (no dead scaffolding).
2. **Lint passes** — repository-standard linter/formatting clean.
3. **Type checks pass** — mypy/pyright/tsc as applicable.
4. **Unit tests pass** — relevant coverage, written or updated.
5. **Integration tests pass** — where the change crosses boundaries (Redis, Postgres,
   Nautilus, TradingAgents mock, Graphiti, MT4 emulator).
6. **Domain-specific evidence**:
   - data-time work → leakage tests still fail-on-violation correctly;
   - backtest work → deterministic replay (same input → same output);
   - risk work → property-based tests hold (`risk > limit → never approve`,
     duplicate `order_intent_id` → never a second order);
   - execution work → idempotency, reconciliation, chaos tests updated.
7. **Architecture respected** — check against `.ai/rules/architecture-invariants.md`;
   cite the invariants touched and why they still hold.
8. **Security implications checked** — secrets, trust zones, privilege boundaries.
   For execution/LLM-boundary work this is mandatory, not optional.
9. **No placeholder implementations** — no TODO-stubs, no mock returns left in
   production paths, no `NotImplementedError` in live code paths.
10. **No unrelated regressions** — the rest of the suite still passes.

## Review gates

- **Substantial tasks** (cross-cutting, risk-sensitive, execution-sensitive,
  data-time, LLM-boundary, architecture-wide): a **Verification agent** independent
  review is mandatory before completion is claimed.
- Reviewer requirements come from `.ai/rules/cross-review-rules.md`.

## Evidence standard

State the exact commands run and their results (not claims):
`pytest`, `mypy`, `ruff`, `tsc`, `npm run build`, replay runs, etc.

## Reporting

Use `.ai/templates/agent-output.md`. Keep prose short; prioritize implementation and
verification evidence.
