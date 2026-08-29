# tests/security — trust zones, secret handling (INV-9, ADR-0025)

Security-regression suite for the hardening milestone. Canonical threat model:
`docs/threat-model/threat-model.md`.

- `test_trust_zones.py` — the Definition of Done: a compromised LLM worker cannot
  directly submit a broker order. Verifies the worker refuses live operating modes,
  never imports the MT4 execution client, and that the live client fails closed
  without a human-approval authorizer.
- `test_execution_boundary.py` — emergency closures must structurally close a
  persisted open position (MARKET, offsetting side, exact quantity); live-venue
  cancels/modifies require an active EMERGENCY_KILL and a matching live order.
- `test_secret_redaction.py` — secrets never appear in logs or settings reprs;
  env-style secret names, DSN passwords, `sk-*` keys, bearer tokens and age keys
  are masked by `core/security/redact.py` (filter + formatter).

CI additionally runs gitleaks (committed-secret scan) and pip-audit (dependency
audit) on every push — see `.github/workflows/ci.yml`.
