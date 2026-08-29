# apps/api — Core API service (Python 3.12)

- `main.py` — FastAPI app factory + `/healthz` and `/api/v1/contracts` (Phase 0).
- Trading endpoints land in later phases: risk (Phase 5), paper (Phase 7),
  LIVE_GATED confirmation flow (Phase 8).
- Trust zones (INV-9): this service is Zone 2; it never holds broker or LLM secrets.
