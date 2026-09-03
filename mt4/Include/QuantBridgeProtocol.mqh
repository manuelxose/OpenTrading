//+------------------------------------------------------------------+
//|                                  QuantBridgeProtocol.mqh          |
//| OpenTrading — MT4 execution protocol v1.0 (ADR-0020)             |
//| Mechanical MQL4 port of adapters/mt4/{protocol,errors,guards}.py |
//+------------------------------------------------------------------+
// Normative spec: mt4/protocol/README.md.
// This include is pure and deterministic: constants, flat-JSON helpers,
// canonical checksum verification, the command gate (expiration → duplicate
// detection → per-strategy sequence) and the idempotency ledger.
// NO trading logic (INV-5). No ZeroMQ (see QuantBridgeZmq.mqh).
#ifndef QUANT_BRIDGE_PROTOCOL_MQH
#define QUANT_BRIDGE_PROTOCOL_MQH

// ── Protocol constants (mirror adapters/mt4/protocol.py) ────────────────
#define QB_PROTOCOL_VERSION            "1.0"

#define QB_MSG_SUBMIT_ORDER            "submit_order"
#define QB_MSG_CANCEL_ORDER            "cancel_order"
#define QB_MSG_MODIFY_ORDER            "modify_order"
#define QB_MSG_RECONCILIATION_REQUEST  "reconciliation_request"
#define QB_MSG_ORDER_ACK               "order_ack"
#define QB_MSG_ORDER_REJECT            "order_reject"
#define QB_MSG_RECONCILIATION_RESPONSE "reconciliation_response"
#define QB_MSG_HEARTBEAT               "heartbeat"
#define QB_MSG_ACCOUNT_SNAPSHOT        "account_snapshot"
#define QB_MSG_POSITION_SNAPSHOT       "position_snapshot"
#define QB_MSG_PARTIAL_FILL            "partial_fill"
#define QB_MSG_FILL                    "fill"
#define QB_MSG_MARKET_QUOTE            "market_quote"

// ── Error-code vocabulary (mirror adapters/mt4/errors.py) ────────────────
#define QB_ERR_NOT_CONNECTED          "NOT_CONNECTED"
#define QB_ERR_TIMEOUT                "TIMEOUT"
#define QB_ERR_CONNECTION_LOST        "CONNECTION_LOST"
#define QB_ERR_SCHEMA_INVALID         "SCHEMA_INVALID"
#define QB_ERR_CHECKSUM_MISMATCH      "CHECKSUM_MISMATCH"
#define QB_ERR_VERSION_MISMATCH       "PROTOCOL_VERSION_MISMATCH"
#define QB_ERR_UNKNOWN_MESSAGE_TYPE   "UNKNOWN_MESSAGE_TYPE"
#define QB_ERR_SEQUENCE_VIOLATION     "SEQUENCE_VIOLATION"
#define QB_ERR_COMMAND_EXPIRED        "COMMAND_EXPIRED"
#define QB_ERR_DUPLICATE_INTENT       "DUPLICATE_INTENT"
#define QB_ERR_INTENT_CONFLICT        "INTENT_CONFLICT"
#define QB_ERR_UNKNOWN_ORDER          "UNKNOWN_ORDER"
#define QB_ERR_ORDER_NOT_ACTIVE       "ORDER_NOT_ACTIVE"
#define QB_ERR_INVALID_MODIFICATION   "INVALID_MODIFICATION"
#define QB_ERR_TRADING_DISABLED       "TRADING_DISABLED"
#define QB_ERR_SAFE_MODE_ACTIVE       "SAFE_MODE_ACTIVE"
#define QB_ERR_BROKER_DISCONNECTED    "BROKER_DISCONNECTED"
#define QB_ERR_SYMBOL_NOT_ALLOWED     "SYMBOL_NOT_ALLOWED"
#define QB_ERR_LOT_STEP_INVALID       "LOT_STEP_INVALID"
#define QB_ERR_LOT_LIMIT_EXCEEDED     "LOT_LIMIT_EXCEEDED"
#define QB_ERR_INSUFFICIENT_MARGIN    "INSUFFICIENT_MARGIN"
#define QB_ERR_SPREAD_TOO_HIGH        "SPREAD_TOO_HIGH"
#define QB_ERR_STALE_QUOTES           "STALE_QUOTES"
#define QB_ERR_MARKET_CLOSED          "MARKET_CLOSED"
#define QB_ERR_STOP_LEVEL_VIOLATION   "STOP_LEVEL_VIOLATION"
#define QB_ERR_INVALID_MAGIC          "INVALID_MAGIC"
#define QB_ERR_SLIPPAGE_CAP_EXCEEDED  "SLIPPAGE_CAP_EXCEEDED"
#define QB_ERR_BROKER_ERROR           "BROKER_ERROR"
#define QB_ERR_INTERNAL_ERROR         "INTERNAL_ERROR"

// ── Flat-JSON storage ───────────────────────────────────────────────────
// The wire spec is flat by design: one object level, no nesting (except the
// `error` object inside order_reject, handled by the EA directly). Parsed
// values keep their RAW substring so the canonical checksum can be rebuilt
// byte-exact (no number-round-trip drift).
#define QB_MAX_JSON_FIELDS 64

string g_qbKeys[QB_MAX_JSON_FIELDS];
string g_qbVals[QB_MAX_JSON_FIELDS];
int    g_qbCount = 0;

//+------------------------------------------------------------------+
//| Trim leading/trailing spaces/tabs/newlines                        |
//+------------------------------------------------------------------+
string QbTrim(string text)
{
   int start = 0;
   int end = StringLen(text) - 1;
   while(start <= end && (StringGetCharacter(text, start) <= 32))
      start++;
   while(end >= start && (StringGetCharacter(text, end) <= 32))
      end--;
   if(end < start)
      return "";
   return StringSubstr(text, start, end - start + 1);
}

//+------------------------------------------------------------------+
//| Parse a flat JSON object into g_qbKeys/g_qbVals (raw values).     |
//| Returns false on malformed input (SCHEMA_INVALID upstream).       |
//+------------------------------------------------------------------+
bool QbJsonParse(string text)
{
   g_qbCount = 0;
   text = QbTrim(text);
   int len = StringLen(text);
   if(len < 2)
      return false;
   if(StringGetCharacter(text, 0) != '{' || StringGetCharacter(text, len - 1) != '}')
      return false;

   int pos = 1;
   while(pos < len - 1)
   {
      ushort c;
      // skip separators
      while(pos < len - 1)
      {
         c = StringGetCharacter(text, pos);
         if(c == ',' || c <= 32)
            pos++;
         else
            break;
      }
      if(pos >= len - 1)
         break;

      // key: expect a quoted string
      if(StringGetCharacter(text, pos) != '"')
         return false;
      pos++;
      string key = "";
      while(pos < len)
      {
         c = StringGetCharacter(text, pos);
         if(c == '"')
            break;
         if(c == '\\')          // tolerate escapes in keys (never emitted)
            pos++;
         key += ShortToString(c);
         pos++;
      }
      pos++;
      while(pos < len && StringGetCharacter(text, pos) <= 32)
         pos++;
      if(pos >= len || StringGetCharacter(text, pos) != ':')
         return false;
      pos++;
      while(pos < len && StringGetCharacter(text, pos) <= 32)
         pos++;

      // value: raw substring
      int vstart = pos;
      c = StringGetCharacter(text, pos);
      if(c == '"')                       // string value (raw keeps the quotes)
      {
         pos++;
         bool closed = false;
         while(pos < len)
         {
            c = StringGetCharacter(text, pos);
            if(c == '\\')
               pos += 2;
            else
            {
               if(c == '"')
               {
                  closed = true;
                  pos++;
                  break;
               }
               pos++;
            }
         }
         if(!closed)
            return false;
      }
      else if(c == 't' || c == 'f' || c == 'n')   // true/false/null literal
      {
         while(pos < len && ((c = StringGetCharacter(text, pos)) != ',' && c != '}'))
            pos++;
      }
      else                                         // number
      {
         while(pos < len && ((c = StringGetCharacter(text, pos)) != ',' && c != '}'))
            pos++;
      }

      if(g_qbCount >= QB_MAX_JSON_FIELDS)
         return false;
      g_qbKeys[g_qbCount] = key;
      g_qbVals[g_qbCount] = QbTrim(StringSubstr(text, vstart, pos - vstart));
      g_qbCount++;
   }
   return true;
}

//+------------------------------------------------------------------+
//| Index of a key, or -1                                             |
//+------------------------------------------------------------------+
int QbJsonIndexOf(string key)
{
   for(int i = 0; i < g_qbCount; i++)
   {
      if(g_qbKeys[i] == key)
         return i;
   }
   return -1;
}

//+------------------------------------------------------------------+
//| Raw value for a key ("null" when absent)                          |
//+------------------------------------------------------------------+
string QbJsonGetRaw(string key)
{
   int idx = QbJsonIndexOf(key);
   if(idx < 0)
      return "null";
   return g_qbVals[idx];
}

//+------------------------------------------------------------------+
//| Unescape a JSON string value (quotes stripped)                    |
//+------------------------------------------------------------------+
string QbJsonGetString(string key)
{
   string raw = QbJsonGetRaw(key);
   if(raw == "null")
      return "";
   int len = StringLen(raw);
   if(len >= 2 && StringGetCharacter(raw, 0) == '"')
   {
      string out = "";
      for(int i = 1; i < len - 1; i++)
      {
         ushort c = StringGetCharacter(raw, i);
         if(c == '\\' && i + 1 < len - 1)
         {
            ushort e = StringGetCharacter(raw, i + 1);
            if(e == '"' || e == '\\' || e == '/')
            {
               out += ShortToString(e);
               i++;
               continue;
            }
            if(e == 'n') { out += "\n"; i++; continue; }
            if(e == 't') { out += "\t"; i++; continue; }
            if(e == 'r') { out += "\r"; i++; continue; }
            if(e == 'b') { out += ShortToString(8); i++; continue; }
            if(e == 'f') { out += ShortToString(12); i++; continue; }
            // \uXXXX never emitted by the Core (ensure_ascii=False); keep raw.
            out += ShortToString(c);
            continue;
         }
         out += ShortToString(c);
      }
      return out;
   }
   return raw;
}

//+------------------------------------------------------------------+
//| Numeric helpers: Decimal fields travel as JSON strings.           |
//+------------------------------------------------------------------+
double QbJsonGetDouble(string key)
{
   string raw = QbJsonGetString(key);
   if(raw == "")
      return 0.0;
   return StringToDouble(raw);
}

long QbJsonGetLong(string key)
{
   string raw = QbJsonGetRaw(key);
   if(raw == "null")
      return 0;
   return (long)StringToInteger(raw);
}

//+------------------------------------------------------------------+
//| Escape a string for JSON output                                   |
//+------------------------------------------------------------------+
string QbJsonEscape(string s)
{
   string out = "";
   int len = StringLen(s);
   for(int i = 0; i < len; i++)
   {
      ushort c = StringGetCharacter(s, i);
      if(c == '"')        out += "\\\"";
      else if(c == '\\')  out += "\\\\";
      else if(c == '\n')  out += "\\n";
      else if(c == '\r')  out += "\\r";
      else if(c == '\t')  out += "\\t";
      else if(c < 32)     out += StringFormat("\\u%04x", c);
      else                out += ShortToString(c);
   }
   return out;
}

//+------------------------------------------------------------------+
//| Decimal → string, no scientific notation, trailing zeros trimmed  |
//| (Decimal str() parity for JSON string fields).                    |
//+------------------------------------------------------------------+
string QbNumStr(double value)
{
   string s = DoubleToString(value, 8);
   // trim trailing zeros, keep at least one decimal
   int cut = StringLen(s);
   while(cut > 1 && StringGetCharacter(s, cut - 1) == '0')
      cut--;
   if(cut > 1 && StringGetCharacter(s, cut - 1) == '.')
      cut++;
   return StringSubstr(s, 0, cut);
}

//+------------------------------------------------------------------+
//| ISO-8601 UTC now: 2026-08-29T18:00:00Z                            |
//+------------------------------------------------------------------+
string QbUtcNowIso()
{
   string s = TimeToString(TimeGMT(), TIME_DATE | TIME_SECONDS);
   StringReplace(s, " ", "T");
   StringReplace(s, ".", "-");
   return s + "Z";
}

//+------------------------------------------------------------------+
//| ISO-8601 UTC string → MQL4 datetime (0 on parse failure)          |
//+------------------------------------------------------------------+
datetime QbIsoToTime(string iso)
{
   if(iso == "" || iso == "null")
      return 0;
   StringReplace(iso, "T", " ");
   StringReplace(iso, "Z", "");
   iso = QbTrim(iso);
   return StringToTime(iso);
}

//+------------------------------------------------------------------+
//| Canonical key order per message type (pydantic field definition   |
//| order — MUST stay frozen; the checksum depends on it).            |
//+------------------------------------------------------------------+
int QbCanonicalKeys(string messageType, string &keys[])
{
   string base[];
   ArrayResize(base, 20);
   base[0]  = "protocol_version";
   base[1]  = "message_type";
   base[2]  = "message_id";
   base[3]  = "trace_id";
   base[4]  = "timestamp";
   base[5]  = "sequence";
   base[6]  = "correlation_id";
   base[7]  = "checksum";
   base[8]  = "order_intent_id";
   base[9]  = "strategy_id";
   base[10] = "strategy_version";
   base[11] = "expires_at";
   base[12] = "symbol";
   base[13] = "side";
   base[14] = "quantity";
   base[15] = "order_type";
   base[16] = "price";
   base[17] = "stop_loss";
   base[18] = "take_profit";
   base[19] = "max_slippage";

   int count = 20;
   if(messageType == QB_MSG_SUBMIT_ORDER)
   {
      ArrayResize(base, 21);
      base[20] = "time_in_force";
      count = 21;
   }
   else if(messageType == QB_MSG_CANCEL_ORDER)
   {
      ArrayResize(base, 21);
      base[20] = "reason";
      count = 21;
   }
   else if(messageType == QB_MSG_MODIFY_ORDER)
   {
      ArrayResize(base, 23);
      base[20] = "new_price";
      base[21] = "new_stop_loss";
      base[22] = "new_take_profit";
      count = 23;
   }
   else if(messageType == QB_MSG_RECONCILIATION_REQUEST)
   {
      ArrayResize(base, 21);
      base[20] = "scope";
      count = 21;
   }

   ArrayResize(keys, count);
   for(int i = 0; i < count; i++)
      keys[i] = base[i];
   return count;
}

//+------------------------------------------------------------------+
//| Rebuild the canonical body from RAW parsed segments.              |
//| skipMode 0: exclude `checksum` (checksum verification).           |
//| skipMode 1: exclude the fingerprint-excluded set (idempotency).   |
//+------------------------------------------------------------------+
bool QbSkipKey(int skipMode, string key)
{
   if(skipMode == 0)
      return (key == "checksum");
   return (key == "checksum" || key == "correlation_id" || key == "message_id"
        || key == "sequence" || key == "timestamp" || key == "trace_id");
}

string QbCanonicalBody(string messageType, int skipMode)
{
   string keys[];
   int n = QbCanonicalKeys(messageType, keys);
   string out = "{";
   bool first = true;
   for(int i = 0; i < n; i++)
   {
      string key = keys[i];
      if(QbSkipKey(skipMode, key))
         continue;
      if(!first)
         out += ",";
      first = false;
      out += "\"" + key + "\":" + QbJsonGetRaw(key);
   }
   out += "}";
   return out;
}

//+------------------------------------------------------------------+
//| SHA-256 hex digest (CryptEncode, MT4 build 1600+).                |
//+------------------------------------------------------------------+
string QbSha256Hex(string text)
{
   uchar data[];
   uchar key[];
   uchar hash[];
   StringToCharArray(text, data, 0, WHOLE_ARRAY);
   // MQL4 StringToCharArray appends a trailing '\0' — the Python side hashes
   // the exact payload bytes without it (SHA-256 parity).
   if(ArraySize(data) > 0 && data[ArraySize(data) - 1] == 0)
      ArrayResize(data, ArraySize(data) - 1);
   int n = CryptEncode(CRYPT_HASH_SHA256, data, key, hash);
   if(n <= 0)
      return "";
   string out = "";
   for(int i = 0; i < ArraySize(hash); i++)
      out += StringFormat("%02x", hash[i]);
   return out;
}

//+------------------------------------------------------------------+
//| Idempotency fingerprint: SHA-256 of canonical body minus frame     |
//| fields (same field set the Python CommandMessage.fingerprint uses).|
//+------------------------------------------------------------------+
string QbFingerprint(string messageType)
{
   return QbSha256Hex(QbCanonicalBody(messageType, 1));
}

//+------------------------------------------------------------------+
//| Checksum verification (mirrors WireMessage.verify_checksum).      |
//| Returns "" when valid, else the checksum error JSON fragment.     |
//+------------------------------------------------------------------+
string QbVerifyChecksum()
{
   string checksum = QbJsonGetString("checksum");
   if(checksum == "")
      return "missing checksum";
   string body = QbCanonicalBody(QbJsonGetString("message_type"), 0);
   string recomputed = QbSha256Hex(body);
   if(recomputed == "")
      return "sha256 unavailable";
   if(checksum != recomputed)
      return "checksum mismatch (frame=" + checksum + " recomputed=" + recomputed + " body=" + body + ")";
   return "";
}

//+------------------------------------------------------------------+
//| Error object JSON (ProtocolErrorDetail, extra="forbid" field set) |
//+------------------------------------------------------------------+
string QbBuildError(string code, string message, string detail,
                    string traceId, string intentId, string symbol, long sequence)
{
   string out = "{\"code\":\"" + code + "\"";
   out += ",\"message\":\"" + QbJsonEscape(message) + "\"";
   if(detail != "")
      out += ",\"detail\":\"" + QbJsonEscape(detail) + "\"";
   if(traceId == "" || traceId == "null")
      out += ",\"trace_id\":null";
   else
      out += ",\"trace_id\":\"" + traceId + "\"";
   if(intentId == "" || intentId == "null")
      out += ",\"order_intent_id\":null";
   else
      out += ",\"order_intent_id\":\"" + intentId + "\"";
   if(symbol == "")
      out += ",\"symbol\":null";
   else
      out += ",\"symbol\":\"" + QbJsonEscape(symbol) + "\"";
   out += ",\"sequence\":" + IntegerToString(sequence);
   out += ",\"produced_at\":\"" + QbUtcNowIso() + "\"}";
   return out;
}

//+------------------------------------------------------------------+
//| Deterministic UUIDv5 (sha1) — same derivation the Python side     |
//| uses via uuid.uuid5(namespace, name).                             |
//+------------------------------------------------------------------+
string QbUuid5(string nsUuid, string name)
{
   // namespace UUID → 16 bytes (strip dashes, hex decode)
   string hex = nsUuid;
   StringReplace(hex, "-", "");
   uchar nsBytes[16];
   ArrayInitialize(nsBytes, 0);
   for(int i = 0; i < 16; i++)
      nsBytes[i] = (uchar)StringToInteger(StringSubstr(hex, i * 2, 2) + "h");
   uchar nameBytes[];
   StringToCharArray(name, nameBytes, 0, WHOLE_ARRAY);
   uchar data[];
   ArrayResize(data, 16 + ArraySize(nameBytes));
   for(int j = 0; j < 16; j++)
      data[j] = nsBytes[j];
   for(int k = 0; k < ArraySize(nameBytes); k++)
      data[16 + k] = nameBytes[k];
   uchar key[];
   uchar hash[];
   int n = CryptEncode(CRYPT_HASH_SHA1, data, key, hash);
   if(n <= 0)
      return "00000000-0000-5000-8000-000000000000";
   hash[6] = (uchar)((hash[6] & 0x0F) | 0x50);   // version 5
   hash[8] = (uchar)((hash[8] & 0x3F) | 0x80);   // RFC variant
   string out = "";
   for(int i = 0; i < 16; i++)
   {
      out += StringFormat("%02x", hash[i]);
      if(i == 3 || i == 5 || i == 7 || i == 9)
         out += "-";
   }
   return out;
}

//+------------------------------------------------------------------+
//| Idempotency ledger (IntentLedger port). Keyed by                  |
//| (order_intent_id, command_type); submit/cancel immutable, modify  |
//| replaceable by a newer amendment.                                 |
//+------------------------------------------------------------------+
struct QbIntentRecord
{
   string order_intent_id;
   string command_type;
   string fingerprint;
   string reply;         // serialized outcome, replayed on exact duplicate
};

#define QB_LEDGER_MAX 10000
QbIntentRecord g_qbLedger[QB_LEDGER_MAX];
int g_qbLedgerCount = 0;

int QbLedgerLookup(string intentId, string commandType)
{
   for(int i = 0; i < g_qbLedgerCount; i++)
   {
      if(g_qbLedger[i].order_intent_id == intentId
      && g_qbLedger[i].command_type == commandType)
         return i;
   }
   return -1;
}

void QbLedgerRecord(string intentId, string commandType, string fingerprint,
                    string reply, bool allowReplace)
{
   if(g_qbLedgerCount >= QB_LEDGER_MAX)
      return;    // bounded memory; reconciliation covers the gap (INV-6)
   int idx = QbLedgerLookup(intentId, commandType);
   if(idx >= 0 && !allowReplace)
      return;    // immutable submit/cancel record
   if(idx < 0)
   {
      idx = g_qbLedgerCount;
      g_qbLedgerCount++;
      g_qbLedger[idx].order_intent_id = intentId;
      g_qbLedger[idx].command_type = commandType;
   }
   g_qbLedger[idx].fingerprint = fingerprint;
   g_qbLedger[idx].reply = reply;
}

//+------------------------------------------------------------------+
//| Per-strategy sequence tracker (strict monotonic, starts at 1).    |
//+------------------------------------------------------------------+
#define QB_SEQ_MAX 256
string g_qbSeqKeys[QB_SEQ_MAX];
long   g_qbSeqLast[QB_SEQ_MAX];
int    g_qbSeqCount = 0;

int QbSeqIndex(string strategyId)
{
   for(int i = 0; i < g_qbSeqCount; i++)
   {
      if(g_qbSeqKeys[i] == strategyId)
         return i;
   }
   return -1;
}

long QbSeqExpected(string strategyId)
{
   int idx = QbSeqIndex(strategyId);
   if(idx < 0)
      return 1;
   return g_qbSeqLast[idx] + 1;
}

bool QbSeqIsNext(string strategyId, long sequence)
{
   return sequence == QbSeqExpected(strategyId);
}

void QbSeqAccept(string strategyId, long sequence)
{
   int idx = QbSeqIndex(strategyId);
   if(idx < 0)
   {
      if(g_qbSeqCount >= QB_SEQ_MAX)
         return;
      idx = g_qbSeqCount;
      g_qbSeqCount++;
      g_qbSeqKeys[idx] = strategyId;
      g_qbSeqLast[idx] = 0;
   }
   g_qbSeqLast[idx] = sequence;
}

string QbSeqSnapshotJson()
{
   string out = "{";
   for(int i = 0; i < g_qbSeqCount; i++)
   {
      if(i > 0)
         out += ",";
      out += "\"" + QbJsonEscape(g_qbSeqKeys[i]) + "\":" + IntegerToString(g_qbSeqLast[i]);
   }
   out += "}";
   return out;
}

//+------------------------------------------------------------------+
//| Command gate verdict (port of guards.CommandGate.evaluate).       |
//| accepted=true → caller executes and then calls QbGateRecord.      |
//| replay carries the stored serialized reply for exact duplicates.  |
//+------------------------------------------------------------------+
struct QbGateOutcome
{
   bool   accepted;
   string error;             // "" when none
   string replay;            // "" when none (serialized reply to resend)
   long   expected_sequence;
};

QbGateOutcome QbGateEvaluate(string messageType, string intentId, string strategyId,
                             long sequence, string expiresAt, string fingerprint)
{
   QbGateOutcome out;
   out.accepted = false;
   out.error = "";
   out.replay = "";
   out.expected_sequence = 0;

   // Reconciliation is a stateless query: skip expiry/duplicates/sequence (INV-6).
   if(messageType == QB_MSG_RECONCILIATION_REQUEST)
   {
      out.accepted = true;
      return out;
   }

   out.expected_sequence = QbSeqExpected(strategyId);

   // 4. Expiration — an expired command is dead even as a faithful duplicate.
   datetime exp = QbIsoToTime(expiresAt);
   if(expiresAt != "" && expiresAt != "null" && exp <= TimeGMT())
   {
      out.error = QbBuildError(QB_ERR_COMMAND_EXPIRED, "command expired",
                               "sequence=" + IntegerToString(sequence) + " strategy=" + strategyId,
                               QbJsonGetString("trace_id"), intentId, QbJsonGetString("symbol"), sequence);
      return out;
   }

   // 5. Duplicate detection scoped by (order_intent_id, command_type).
   if(intentId != "" && intentId != "null")
   {
      int idx = QbLedgerLookup(intentId, messageType);
      if(idx >= 0)
      {
         if(g_qbLedger[idx].fingerprint == fingerprint)
         {
            out.replay = g_qbLedger[idx].reply;
            return out;
         }
         if(messageType != QB_MSG_MODIFY_ORDER)
         {
            out.error = QbBuildError(QB_ERR_INTENT_CONFLICT,
                                     "order_intent_id " + intentId + " reused with different fields",
                                     "sequence=" + IntegerToString(sequence) + " strategy=" + strategyId,
                                     QbJsonGetString("trace_id"), intentId, QbJsonGetString("symbol"), sequence);
            return out;
         }
         // modify: a second amendment with new fields is legitimate
      }
   }

   // 6. Strict monotonic sequence per strategy namespace.
   if(!QbSeqIsNext(strategyId, sequence))
   {
      out.error = QbBuildError(QB_ERR_SEQUENCE_VIOLATION,
                               "expected sequence " + IntegerToString(out.expected_sequence),
                               "sequence=" + IntegerToString(sequence) + " strategy=" + strategyId,
                               QbJsonGetString("trace_id"), intentId, QbJsonGetString("symbol"), sequence);
      return out;
   }

   out.accepted = true;
   return out;
}

//+------------------------------------------------------------------+
//| Record an accepted command: ledger entry + sequence advance.      |
//+------------------------------------------------------------------+
void QbGateRecord(string messageType, string intentId, string strategyId,
                  long sequence, string fingerprint, string reply)
{
   if(messageType == QB_MSG_RECONCILIATION_REQUEST)
      return;
   if(intentId != "" && intentId != "null")
      QbLedgerRecord(intentId, messageType, fingerprint, reply,
                     messageType == QB_MSG_MODIFY_ORDER);
   QbSeqAccept(strategyId, sequence);
}

#endif // QUANT_BRIDGE_PROTOCOL_MQH
//+------------------------------------------------------------------+
