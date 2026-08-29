# ADR-0020: MT4 execution protocol v1.0 (versioned ZeroMQ, emulator-first)

- Status: accepted
- Date: 2026-08-26
- Deciders: principal-architect (+ execution-mt4 + risk + security + verification for
  execution-sensitive class)

## Context

Phase 6 builds the MT4 bridge (ADR-0003, ADR-0016, INV-5). Before
`QuantBridgeEA.mq4` exists, the Core needs a *versioned* wire protocol between itself
and the bridge so that:

- both sides share one message vocabulary and one set of validation semantics;
- the full execution lifecycle (submit → ack/reject → partial/fill → position →
  reconcile) is testable against a Python emulator, with no MetaTrader installed;
- the MQL4 EA is a mechanical port of the emulator's behavior, not a parallel design.

Transport is private ZeroMQ (§34.18, frozen; `WebRequest` rejected in §8/ADR-0016).

## Decision

**Protocol `mt4-exec` v1.0** — flat JSON (UTF-8, single frame) over three ZeroMQ
channels on a private network (WireGuard when MT4 is remote; sockets never
internet-exposed, §29):

| Channel | Sockets | Direction | Messages |
|---|---|---|---|
| command | REQ → REP | Core → MT4 | submit_order, cancel_order, modify_order, reconciliation_request |
| command | REP → REQ | MT4 → Core | order_ack, order_reject, reconciliation_response |
| event | PUSH → PULL | MT4 → Core | heartbeat, account_snapshot, position_snapshot, partial_fill, fill |
| market | PUB → SUB | MT4 → Core | market_quote (topic = symbol, multipart) |

REQ/REP was chosen over PUSH for commands so every command gets a synchronous,
correlated reply and PUSH/PUB remain for one-way event/market streams — the same
socket types the common MQL4 ZeroMQ bindings expose.

**Envelope (every message).** `protocol_version`, `message_type`, `message_id`,
`trace_id`, `timestamp`, `sequence`, `correlation_id` (replies only), `checksum`
(SHA-256 of the canonical body). A MAJOR version mismatch is a hard reject
(`PROTOCOL_VERSION_MISMATCH`); MINOR bumps are backward compatible.

**Command fields (every command, §8).** `protocol_version`, `trace_id`,
`order_intent_id`, `strategy_id`, `strategy_version`, `timestamp`, `expires_at`,
`sequence`, `symbol`, `side`, `quantity`, `order_type`, `price`, `stop_loss`,
`take_profit`, `max_slippage`. Cancel/modify echo the original order context;
modify adds `new_price` / `new_stop_loss` / `new_take_profit` (≥1 required).

**Guarantees, checked in this frozen order** (emulator code =
`adapters/mt4/guards.py`; the EA must match):

1. schema validation (unknown `message_type` → `UNKNOWN_MESSAGE_TYPE`,
   malformed field → `SCHEMA_INVALID`);
2. `protocol_version` compatibility;
3. checksum (transport integrity);
4. command expiration (`expires_at` < now → `COMMAND_EXPIRED`);
5. duplicate detection — keyed by `(order_intent_id, message_type)`: submit and
   cancel are one-shot per intent (identical re-delivery replays the stored
   outcome; different fields → `INTENT_CONFLICT`), modify may repeat with new
   fields (identical re-delivery replays, new fields are a new amendment);
6. sequence validation — strict monotonic per `strategy_id` namespace
   (`SEQUENCE_VIOLATION` carries the expected value).

`order_intent_id` is the idempotency key for every venue (INV-2). Reconciliation
is a stateless query: no idempotency/sequence semantics, never advances a
namespace — so a restart can always reconcile before resyncing.

**Structured error codes.** One vocabulary for Python and MQL4
(`adapters/mt4/errors.py`): transport (`NOT_CONNECTED`, `TIMEOUT`,
`CONNECTION_LOST`), framing (`SCHEMA_INVALID`, `CHECKSUM_MISMATCH`,
`PROTOCOL_VERSION_MISMATCH`, `UNKNOWN_MESSAGE_TYPE`), ordering
(`SEQUENCE_VIOLATION`, `COMMAND_EXPIRED`, `DUPLICATE_INTENT`, `INTENT_CONFLICT`,
`UNKNOWN_ORDER`, `ORDER_NOT_ACTIVE`, `INVALID_MODIFICATION`), venue
(`TRADING_DISABLED`, `SAFE_MODE_ACTIVE`, `BROKER_DISCONNECTED`,
`SYMBOL_NOT_ALLOWED`, `LOT_STEP_INVALID`, `LOT_LIMIT_EXCEEDED`,
`INSUFFICIENT_MARGIN`, `SPREAD_TOO_HIGH`, `STALE_QUOTES`, `MARKET_CLOSED`,
`STOP_LEVEL_VIOLATION`, `INVALID_MAGIC`, `SLIPPAGE_CAP_EXCEEDED`,
`BROKER_ERROR`, `INTERNAL_ERROR`). Rejections are returned as `order_reject`
messages (never exceptions); transport failures raise `Mt4ProtocolError`.

**Connection health.** Derived from the heartbeat stream:
CONNECTED → DEGRADED → DOWN; when DOWN, the Core refuses new commands
(`NOT_CONNECTED`) — INV-7 dead-man semantics.

**Reconciliation.** `reconciliation_request` →
`reconciliation_response(account, positions, open_order_intent_ids,
last_sequences, broker_connected, trading_enabled)`. `last_sequences` lets a
restarted Core resync per-strategy sequence counters (INV-6). Divergence between
Core DB state and the response → `SAFE_MODE` (emulator supports `safe_mode`).

**Emulator first.** `adapters/mt4/` ships `Mt4ExecutionClient` (Core side),
`Mt4Emulator` + `SimulatedBroker` (MT4 side stand-in: seeded deterministic quotes,
exact Decimal arithmetic, the full EA defense-in-depth validation list from §8,
MagicNumber = deterministic hash of strategy_id, max_slippage enforcement). The
Phase 6 DoD — 100× the same `order_intent_id` → exactly one trade — is executed
end-to-end over real loopback ZeroMQ sockets in
`tests/unit/mt4/test_lifecycle.py`, with no MetaTrader and no Docker.

## Alternatives considered

- **Flat JSON vs nested envelope** — flat chosen: MQL4 JSON parsers stay minimal,
  and every command literally carries the §8 field set at top level.
- **DEALER/ROUTER for commands** — rejected: MQL4 ZeroMQ bindings widely expose
  REQ/REP/PUSH/PULL/PUB/SUB but rarely DEALER/ROUTER; REQ/REP gives a correlated
  reply per command.
- **Multipart framing for commands/events** — rejected: single-frame JSON is
  simpler on both sides; only PUB quotes use a symbol topic frame.
- **Emulator as a separate package** — rejected: the emulator lives next to the
  client in `adapters/mt4` so protocol and emulator cannot drift apart.
- **WebRequest transport** — rejected by §8/ADR-0016 (blocking, unavailable in
  Strategy Tester).

## Consequences

- Positive: the full lifecycle is executable and CI-testable before any MQL4
  exists; the EA becomes a mechanical port of the emulator's gate + broker
  checks; one error vocabulary across Python and MQL4.
- Negative: the EA must now match v1.0 semantics exactly (checksum, sequences,
  expiry, type-scoped idempotency) — non-trivial in MQL4.
- Follow-ups: `QuantBridgeEA.mq4` + `Include/QuantBridgeProtocol.mqh` as the
  MQL4 port of this spec; Phase 8 exercises disconnect/restart/duplicate/broker
  rejection/partial fills against the real venue.

## Validation

- Frozen §34.18 (private ZeroMQ), §8 (channels/fields/EA validations), §9
  (reconciliation), INV-2/INV-5/INV-6/INV-7.
- `mt4/protocol/README.md` is the normative wire spec for the MQL4 implementer.
- Repo evidence: `adapters/mt4/` (protocol, guards, ledger, broker, transport,
  client, emulator, CLI), `tests/unit/mt4/` (53 tests incl. the lifecycle DoD),
  `pyproject.toml` gains `pyzmq>=26,<27`.
