import hashlib

body = '{"protocol_version":"1.0","message_type":"reconciliation_request","message_id":"ae1327e5-f252-4808-bfd6-7599957bf479","trace_id":null,"timestamp":"2026-08-29T19:12:47.930827Z","sequence":1,"correlation_id":null,"order_intent_id":null,"strategy_id":"CORE","strategy_version":"CORE","expires_at":null,"symbol":null,"side":null,"quantity":null,"order_type":null,"price":null,"stop_loss":null,"take_profit":null,"max_slippage":"0","scope":"ALL"}'
print("sha:", hashlib.sha256(body.encode("utf-8")).hexdigest())
print("len:", len(body))
