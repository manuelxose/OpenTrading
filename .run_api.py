"""Dev-only launcher: run the OpenTrading API on Windows.

psycopg async (used by the readiness checks in apps/api/health.py) cannot run
on the default ProactorEventLoop on Windows. Force the SelectorEventLoop with
SelectSelector, then start uvicorn programmatically.

Usage: .venv\\Scripts\\python.exe .run_api.py
"""

from __future__ import annotations

import asyncio

import uvicorn

# Must run before any asyncio primitive is created by uvicorn.
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if __name__ == "__main__":
    # uvicorn's default loop factory is ProactorEventLoop on Windows, which
    # psycopg async (used by GET /readyz) cannot run on. Force a SelectorEventLoop.
    uvicorn.run(
        "apps.api.main:app",
        host="127.0.0.1",
        port=18000,
        loop="asyncio:SelectorEventLoop",
    )
