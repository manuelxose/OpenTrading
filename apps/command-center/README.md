# OpenTrading Command Center

Production TypeScript/React monitoring UI for the platform. It consumes read-only FastAPI
projections and contains no trading business logic.

```bash
npm install
npm run dev
```

The dev server proxies `/api` to `http://127.0.0.1:8000`. Set `VITE_API_ROOT` at build time when
the API is hosted elsewhere. Start the API with:

```bash
uv run uvicorn apps.api.main:app --reload
```

Pages report empty or unavailable capabilities truthfully; no fixtures or fake production data
are bundled.

Decision (ADR-0002): the Command Center is a TypeScript web application
(Overview, Research, Signals, Risk, Orders & Trades, Memory, Backtests, Agents,
System). **No trading logic client-side** (architecture §26).

Not implemented in Phase 0 — the UI is built once the API surface exists (Phases 5+).
