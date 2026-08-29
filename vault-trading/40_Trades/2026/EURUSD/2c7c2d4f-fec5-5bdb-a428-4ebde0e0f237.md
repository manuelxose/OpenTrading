---
generated: true
authoritative: false
generator: OpenTrading Obsidian export
note_type: trade
canonical_id_type: trade_id
canonical_id: "2c7c2d4f-fec5-5bdb-a428-4ebde0e0f237"
event_id: 50079370-f1f9-4880-961b-a6d64dbd95f7
trace_id: b8a2496e-a0db-432e-98a6-024f0119bbac
event_name: trade.closed
event_time: 2026-08-29T00:05:12.398436+00:00
---

# Trade — 2c7c2d4f-fec5-5bdb-a428-4ebde0e0f237

> [!WARNING] AUTOMATICALLY GENERATED MIRROR
> This note is for human inspection only. Canonical trading data lives in the platform stores.

## Summary

- **Instrument Id:** "EURUSD"
- **Direction:** "LONG"
- **Realized Pnl:** "-92.00000"
- **Exit Reason:** "position_closed"

## Canonical event snapshot

```json
{
  "closed_at": "2026-08-29T00:05:12.398198Z",
  "costs": "5.5",
  "direction": "LONG",
  "entry_price": "1.10161",
  "exit_price": "1.10069",
  "exit_reason": "position_closed",
  "expected_vs_actual": {},
  "holding_seconds": null,
  "instrument_id": "EURUSD",
  "mae": null,
  "mfe": null,
  "opened_at": "2026-08-29T00:05:10.443865Z",
  "order_intent_ids": [
    "cf8b5c30-82f6-5e5d-932e-2359826af0b9",
    "4ec0d783-1263-502a-8d1a-297a82a7bcd8"
  ],
  "position_id": "paper:EURUSD:38d7b066f76f",
  "produced_at": "2026-08-29T00:05:12.398198Z",
  "provenance": {
    "code_version": null,
    "notes": {},
    "produced_at": "2026-08-29T00:05:12.398198Z",
    "producer": "apps.worker.ledger",
    "source_ids": {}
  },
  "quantity": "100000",
  "r_multiple": null,
  "realized_pnl": "-92.00000",
  "regime_at_entry": null,
  "schema_version": "1.0.0",
  "slippage_total": null,
  "trace_id": "b8a2496e-a0db-432e-98a6-024f0119bbac",
  "trade_id": "2c7c2d4f-fec5-5bdb-a428-4ebde0e0f237"
}
```

## Trace

- Event: `50079370-f1f9-4880-961b-a6d64dbd95f7`
- Trace: `b8a2496e-a0db-432e-98a6-024f0119bbac`
- Producer: `apps.worker.execution`
