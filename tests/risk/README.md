# tests/risk — Risk Engine test suite (Phase 5, INV-4, ADR-0018)

Invariants enforced here (property-based + fuzz + boundary):

- `risk > limit → NEVER APPROVE` (approved risk ≤ effective budget, exact arithmetic)
- approved quantity ≤ configured maximum (policy and instrument)
- daily loss breach → no new positions
- stale market data → reject
- disabled strategy → reject
- no tested path bypasses any configured limit

| File | What it proves |
|---|---|
| `test_approve.py` | baseline + LIMIT/SHORT variants, determinism, `inputs_hash` |
| `test_reject.py` | every hard check rejects with its reason code |
| `test_resize.py` | every soft limit resizes to the exact allowed size |
| `test_risk_boundary.py` | exactly-at-limit vs one-epsilon-over boundaries |
| `test_invariants.py` | the five critical invariants + no-bypass grid |
| `test_property_based.py` | Hypothesis (~1100 arbitrary input bundles) |
| `test_fuzz.py` | 1500 seeded adversarial draws (deterministic seed) |
| `../unit/schemas/test_risk_contracts.py` | contract validation + RESIZE shape |

Shared builders live in `tests/risk_helpers.py` (baseline: EURUSD LONG 0.10
lots, stop 1.07000, contract size 100000, notional/lot 108002.50, risk/lot
1002.50).
