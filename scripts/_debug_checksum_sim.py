"""Debug: simulate QuantBridgeEA canonical-body rebuild vs Python checksum."""
from __future__ import annotations

import hashlib
import json
import sys
from uuid import UUID

sys.path.insert(0, ".")
from adapters.mt4.protocol import ReconciliationRequestCommand, serialize_message  # noqa: E402
from core.clock.clocks import SystemClock  # noqa: E402

clock = SystemClock()
cmd = ReconciliationRequestCommand(
    message_id=UUID("c348abb0-f549-40c1-96c7-d3d5e2ce0819"),
    timestamp=clock.now(),
    sequence=1,
    strategy_id="CORE",
    strategy_version="CORE",
)
raw = serialize_message(cmd)
print("FRAME:", raw.decode())

frame = json.loads(raw.decode())

# EA canonical key order for reconciliation_request (skip checksum).
keys = [
    "protocol_version", "message_type", "message_id", "trace_id", "timestamp",
    "sequence", "correlation_id", "checksum", "order_intent_id", "strategy_id",
    "strategy_version", "expires_at", "symbol", "side", "quantity",
    "order_type", "price", "stop_loss", "take_profit", "max_slippage", "scope",
]

# EA rebuild: values as RAW substrings of the original JSON text.
text = raw.decode()
raw_vals = {}


def extract_raw(json_text: str, key: str) -> str:
    idx = json_text.find('"' + key + '"')
    if idx < 0:
        return "null"
    colon = json_text.find(":", idx)
    start = colon + 1
    while start < len(json_text) and json_text[start] in " \t":
        start += 1
    c = json_text[start]
    if c == '"':
        end = start + 1
        while True:
            if json_text[end] == "\\":
                end += 2
            elif json_text[end] == '"':
                end += 1
                break
            else:
                end += 1
        return json_text[start:end]
    end = start
    while end < len(json_text) and json_text[end] not in ",}":
        end += 1
    return json_text[start:end]


ea_body = "{"
first = True
for key in keys:
    if key == "checksum":
        continue
    if not first:
        ea_body += ","
    first = False
    ea_body += '"' + key + '":' + extract_raw(text, key)
ea_body += "}"
print("EA REBUILD:", ea_body)

py_body = json.dumps({k: v for k, v in frame.items() if k != "checksum"}, separators=(",", ":"))
print("PY BODY   :", py_body)
print("EQUAL     :", ea_body == py_body)
print("EA sha    :", hashlib.sha256(ea_body.encode()).hexdigest())
print("PY sha    :", hashlib.sha256(py_body.encode()).hexdigest())
print("frame chk :", frame["checksum"])
