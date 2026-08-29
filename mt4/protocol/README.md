# mt4/protocol — MT4 execution protocol v1.0 (ADR-0020, §34.18)

This is the **normative wire spec** for the bridge between the Python Core and
MetaTrader 4. `QuantBridgeEA.mq4` will be a mechanical port of the Python
emulator in `adapters/mt4/` (`guards.py`, `broker.py`, `emulator.py`) — this
document is what the MQL4 implementer codes against. ADR-0020 is the decision
record; `adapters/mt4/protocol.py` is the executable definition.

## 1. Transport

Private ZeroMQ only. Sockets are **never** internet-exposed (§29); when MT4 runs
on a separate Windows host, all three channels ride the WireGuard tunnel
(§34.18, ADR-0016). `WebRequest` is rejected as the execution transport (§8).

| Channel | Sockets | Direction | Purpose |
|---|---|---|---|
| command | Core REQ → MT4 REP | request/response | submit / cancel / modify / reconcile |
| event | MT4 PUSH → Core PULL | one-way | heartbeat, account, position, fills |
| market | MT4 PUB → Core SUB | one-way fan-out | market_quote (topic = symbol) |

Framing: **flat JSON, UTF-8, single frame** (except market quotes: multipart
`[topic, payload]`). Default loopback endpoints: command `tcp://127.0.0.1:5555`,
events `:5556`, quotes `:5557` (env-overridable via `OT_MT4_*`).

## 2. Envelope (every message)

| Field | Type | Notes |
|---|---|---|
| `protocol_version` | string | `"1.0"`; MAJOR mismatch → `PROTOCOL_VERSION_MISMATCH` |
| `message_type` | string | one of §3 |
| `message_id` | uuid | unique per frame |
| `trace_id` | uuid \| null | end-to-end correlation (§31) |
| `timestamp` | ISO-8601 UTC | timezone-aware, e.g. `2026-08-26T10:00:00Z` |
| `sequence` | int ≥ 0 | commands: per-strategy command sequence; events: global event sequence |
| `correlation_id` | uuid \| null | replies echo the request `message_id` |
| `checksum` | string | SHA-256 hex of the canonical body (fields in definition order, compact JSON, excluding `checksum`) |

## 3. Messages

Commands (Core→MT4) — every command carries the full §8 field set:
`order_intent_id, strategy_id, strategy_version, timestamp, expires_at,
sequence, symbol, side, quantity, order_type, price, stop_loss, take_profit,
max_slippage` (+ envelope fields). Cancel/modify echo the original order's
context fields.

| `message_type` | Extra fields | Notes |
|---|---|---|
| `submit_order` | `time_in_force` | price required unless MARKET; `expires_at > timestamp` |
| `cancel_order` | `reason`? | order context echoed; one-shot per intent |
| `modify_order` | `new_price`?, `new_stop_loss`?, `new_take_profit`? | ≥1 new value; may repeat with new fields |
| `reconciliation_request` | `scope` ("ALL") | stateless query; `strategy_id` is the sequence namespace (conventionally `CORE`) |

Replies (MT4→Core, REP):

| `message_type` | Key fields |
|---|---|
| `order_ack` | `order_intent_id`, `status` (SUBMITTED/ACKNOWLEDGED/CANCELLED/FILLED/MODIFIED), `venue_order_id`, `duplicate` (true = replay from idempotency ledger) |
| `order_reject` | `order_intent_id`?, `error` {`code`, `message`, `detail`, `trace_id`, `order_intent_id`, `symbol`, `sequence`, `produced_at`} |
| `reconciliation_response` | `account`, `positions[]`, `open_order_intent_ids[]`, `last_sequences{}`, `broker_connected`, `trading_enabled` |

Events (MT4→Core, PUSH):

| `message_type` | Key fields |
|---|---|
| `heartbeat` | `broker_connected`, `trading_enabled`, `mode` |
| `account_snapshot` | `account` {account_id, currency, balance, equity, margin, free_margin, as_of} |
| `position_snapshot` | `account_id`, `positions[]` (venue_position_id, magic, canonical PositionSnapshot) |
| `partial_fill` | `order_intent_id`, `venue_order_id`, `filled_quantity`, `remaining_quantity`, `average_fill_price`, `commission`, `slippage`, `symbol` |
| `fill` | same as partial_fill minus `remaining_quantity`, plus `side` |

Market (MT4→Core, PUB, topic = symbol): `market_quote` — `symbol, bid, ask,
spread, tradable`.

## 4. Validation order (frozen — EA must match)

1. **Schema** — unknown `message_type` → `UNKNOWN_MESSAGE_TYPE`; malformed →
   `SCHEMA_INVALID`.
2. **Version** — MAJOR mismatch → `PROTOCOL_VERSION_MISMATCH`.
3. **Checksum** — mismatch → `CHECKSUM_MISMATCH`.
4. **Expiration** — `expires_at` in the past → `COMMAND_EXPIRED` (even faithful
   duplicates are dead).
5. **Duplicates** — keyed by `(order_intent_id, message_type)`:
   submit/cancel one-shot (identical re-delivery → replay stored reply with
   `duplicate=true`; different fields → `INTENT_CONFLICT`); modify may repeat
   with new fields (identical re-delivery → replay; new fields → new amendment).
6. **Sequence** — strict monotonic per `strategy_id` namespace, starting at 1 →
   `SEQUENCE_VIOLATION` (detail carries the expected value).

`reconciliation_request` skips 4–6 (stateless query; restarts must reconcile
before resyncing, INV-6).

## 5. EA defense-in-depth venue checks (INV-5, §8)

Applied by the bridge before any `OrderSend`, even if the backend is
compromised: trading enabled, `SAFE_MODE`, broker connected, symbol whitelist,
lot min/max/step, spread limit, quote freshness, market open, stop/freeze level,
free margin, duplicate `order_intent_id`, MagicNumber (= deterministic hash of
`strategy_id`), command expiry, `max_slippage`.

## 6. Error codes

One vocabulary for Python and MQL4 (`adapters/mt4/errors.py`):

`NOT_CONNECTED`, `TIMEOUT`, `CONNECTION_LOST`, `SCHEMA_INVALID`,
`CHECKSUM_MISMATCH`, `PROTOCOL_VERSION_MISMATCH`, `UNKNOWN_MESSAGE_TYPE`,
`SEQUENCE_VIOLATION`, `COMMAND_EXPIRED`, `DUPLICATE_INTENT`, `INTENT_CONFLICT`,
`UNKNOWN_ORDER`, `ORDER_NOT_ACTIVE`, `INVALID_MODIFICATION`, `TRADING_DISABLED`,
`SAFE_MODE_ACTIVE`, `BROKER_DISCONNECTED`, `SYMBOL_NOT_ALLOWED`,
`LOT_STEP_INVALID`, `LOT_LIMIT_EXCEEDED`, `INSUFFICIENT_MARGIN`,
`SPREAD_TOO_HIGH`, `STALE_QUOTES`, `MARKET_CLOSED`, `STOP_LEVEL_VIOLATION`,
`INVALID_MAGIC`, `SLIPPAGE_CAP_EXCEEDED`, `BROKER_ERROR`, `INTERNAL_ERROR`.

Retryable (sender may safely resend the identical command): `TIMEOUT`,
`CONNECTION_LOST`, `BROKER_DISCONNECTED`, `INTERNAL_ERROR`.

## 7. Connection health

Core derives bridge liveness from the heartbeat stream: CONNECTED → DEGRADED
→ DOWN. When DOWN, the Core blocks new commands (`NOT_CONNECTED`) — dead-man
semantics (INV-7). Broker-side SL/TP remain.

## 8. Versioning policy

- MINOR bump: add optional fields/messages (backward compatible, both sides
  ignore unknown *optional* fields).
- MAJOR bump: change/remove fields or semantics; requires both sides to upgrade
  and an ADR amending this one.

## 9. MQL4 implementation notes

- REP is served from `OnTimer`; JSON via a minimal parser (JAson-style); SHA-256
  checksum verification only where a crypto include is available — the Core
  always sends and verifies checksums.
- The EA never contains strategy intelligence (INV-5); it is exactly
  `receive → validate → broker validation → send → report`.
