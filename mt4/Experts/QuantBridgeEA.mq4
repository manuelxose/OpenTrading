//+------------------------------------------------------------------+
//|                                              QuantBridgeEA.mq4    |
//| OpenTrading — execution-only MT4 bridge (Phase 6, ADR-0020)      |
//+------------------------------------------------------------------+
// Mechanical MQL4 port of the Python emulator (adapters/mt4/):
//   Receive command → Validate command → Broker validation → Send order
//   → Return event.
//
// INV-5: this EA contains NO strategy intelligence. It is exactly
// receive → validate → broker validation → send → report.
//
// Wire spec: mt4/protocol/README.md (normative). Same validation order,
// same error codes, same idempotency/sequence semantics as the emulator.
//
// Transport: private ZeroMQ (REP commands / PUSH events / PUB quotes),
// loopback by default — never internet-exposed (§29). To run against a
// remote Core, point the *_Addr inputs at the WireGuard interface and
// align them with the Core's OT_MT4_*_ADDR settings.
//
// Prerequisite: the mql-zmq binding (dingmaotu/mql-zmq) installed under
// MQL4/Include + DLLs under MQL4/Libraries, and QUANT_BRIDGE_ZMQ defined
// in Include/QuantBridgeZmq.mqh. Without it the EA compiles and logs
// traffic instead of sending it (useful for MetaEditor validation).
//
// Known limitations (see mt4/Experts/README.md):
//  - STOP_LIMIT is rejected (BROKER_ERROR): OrderSend cannot express the
//    two-price stop-limit without broker-side support.
//  - The idempotency ledger is in-memory: after an EA restart the Core
//    must reconcile (INV-6) before resyncing sequences.
#property strict
#property version   "1.0"
#property description "OpenTrading QuantBridge EA — execution-only (ADR-0020)"

#include <QuantBridgeProtocol.mqh>
#include <QuantBridgeZmq.mqh>

// ── Inputs ────────────────────────────────────────────────────────────────
input string InputCommandAddr       = "tcp://127.0.0.1:5555";  // REP bind
input string InputEventsAddr        = "tcp://127.0.0.1:5556";  // PUSH bind
input string InputQuotesAddr        = "tcp://127.0.0.1:5557";  // PUB bind
input bool   InputSafeMode          = false;   // operator-controlled: blocks new entries
input bool   InputVerifyChecksums   = true;    // SHA-256 canonical-body verification
input string InputSymbolWhitelist   = "EURUSD";// comma list; "" = allow all
input double InputMaxSpreadPoints   = 30.0;    // spread cap (points)
input int    InputMaxQuoteAgeSeconds = 5;      // STALE_QUOTES threshold
input double InputHeartbeatSeconds  = 1.0;     // heartbeat cadence
input int    InputPollMilliseconds  = 100;     // REP polling cadence
input string InputBridgeId          = "mt4-bridge-1";

// ── State ─────────────────────────────────────────────────────────────────
string   g_bridgeUuid = "";
datetime g_lastHeartbeat = 0;
long     g_eventSeq = 0;

#define QB_MAX_WORKING 1024
struct QbTicketRecord
{
   int    ticket;
   string intent;
   string strategy;
};
QbTicketRecord g_tickets[QB_MAX_WORKING];
int g_ticketCount = 0;

//+------------------------------------------------------------------+
//| Deterministic MagicNumber: SHA-256(strategy_id)[0:4] & 0x7FFFFFFF|
//| (same derivation as adapters/mt4/broker.py strategy_magic).      |
//+------------------------------------------------------------------+
int QbStrategyMagic(string strategyId)
{
   string hex = QbSha256Hex(strategyId);
   if(StringLen(hex) < 8)
      return 0;
   return (int)StringToInteger(StringSubstr(hex, 0, 8) + "h") & 0x7FFFFFFF;
}

//+------------------------------------------------------------------+
//| Ticket ↔ intent mapping (in-memory; reconcile after restarts)     |
//+------------------------------------------------------------------+
int QbTicketByIntent(string intent)
{
   for(int i = 0; i < g_ticketCount; i++)
   {
      if(g_tickets[i].intent == intent)
         return g_tickets[i].ticket;
   }
   return -1;
}

string QbIntentByTicket(int ticket)
{
   for(int i = 0; i < g_ticketCount; i++)
   {
      if(g_tickets[i].ticket == ticket)
         return g_tickets[i].intent;
   }
   return "";
}

void QbAddTicket(int ticket, string intent, string strategy)
{
   if(g_ticketCount >= QB_MAX_WORKING)
      return;
   int idx = -1;
   for(int i = 0; i < g_ticketCount; i++)
   {
      if(g_tickets[i].intent == intent)
      {
         idx = i;
         break;
      }
   }
   if(idx < 0)
   {
      idx = g_ticketCount;
      g_ticketCount++;
      g_tickets[idx].intent = intent;
   }
   g_tickets[idx].ticket = ticket;
   g_tickets[idx].strategy = strategy;
}

void QbRemoveTicket(int ticket)
{
   for(int i = 0; i < g_ticketCount; i++)
   {
      if(g_tickets[i].ticket == ticket)
      {
         g_tickets[i] = g_tickets[g_ticketCount - 1];
         g_ticketCount--;
         return;
      }
   }
}

//+------------------------------------------------------------------+
//| Envelope prefix for replies/events (checksum:null like Python).   |
//+------------------------------------------------------------------+
string QbEnvelope(string messageType, string messageId, string traceId,
                  long sequence, string correlationId)
{
   string out = "{\"protocol_version\":\"" + QB_PROTOCOL_VERSION + "\"";
   out += ",\"message_type\":\"" + messageType + "\"";
   out += ",\"message_id\":\"" + messageId + "\"";
   if(traceId == "" || traceId == "null")
      out += ",\"trace_id\":null";
   else
      out += ",\"trace_id\":\"" + traceId + "\"";
   out += ",\"timestamp\":\"" + QbUtcNowIso() + "\"";
   out += ",\"sequence\":" + IntegerToString(sequence);
   if(correlationId == "")
      out += ",\"correlation_id\":null";
   else
      out += ",\"correlation_id\":\"" + correlationId + "\"";
   out += ",\"checksum\":null";
   return out;
}

string QbEventFrame(string messageType, string bodyFields)
{
   g_eventSeq++;
   string id = QbUuid5(g_bridgeUuid, "event-" + IntegerToString(g_eventSeq));
   string out = QbEnvelope(messageType, id, "null", g_eventSeq, "");
   if(bodyFields != "")
      out += "," + bodyFields;
   out += "}";
   return out;
}

//+------------------------------------------------------------------+
//| order_reject frame                                                |
//+------------------------------------------------------------------+
string QbRejectFrame(string cmdMessageId, string traceId, string intentId,
                     long sequence, string errorJson)
{
   string id = QbUuid5(cmdMessageId, QB_MSG_ORDER_REJECT);
   string out = QbEnvelope(QB_MSG_ORDER_REJECT, id, traceId, sequence, cmdMessageId);
   if(intentId == "" || intentId == "null")
      out += ",\"order_intent_id\":null";
   else
      out += ",\"order_intent_id\":\"" + intentId + "\"";
   out += ",\"error\":" + errorJson + "}";
   return out;
}

//+------------------------------------------------------------------+
//| order_ack frame                                                  |
//+------------------------------------------------------------------+
string QbAckFrame(string cmdMessageId, string traceId, string intentId,
                  long sequence, string status, string venueOrderId,
                  bool duplicate, string message)
{
   string id = QbUuid5(cmdMessageId, QB_MSG_ORDER_ACK);
   string out = QbEnvelope(QB_MSG_ORDER_ACK, id, traceId, sequence, cmdMessageId);
   out += ",\"order_intent_id\":\"" + intentId + "\"";
   out += ",\"status\":\"" + status + "\"";
   if(venueOrderId == "")
      out += ",\"venue_order_id\":null";
   else
      out += ",\"venue_order_id\":\"" + QbJsonEscape(venueOrderId) + "\"";
   out += ",\"duplicate\":" + (duplicate ? "true" : "false");
   if(message == "")
      out += ",\"message\":null";
   else
      out += ",\"message\":\"" + QbJsonEscape(message) + "\"";
   out += "}";
   return out;
}

//+------------------------------------------------------------------+
//| Ledger reply spec: stored body (rebuilt on duplicate replay).     |
//|   ack spec:    "order_ack|status|venue|message"                   |
//|   reject spec: "order_reject|errorJson"                          |
//+------------------------------------------------------------------+
string QbAckSpec(string status, string venue, string message)
{
   return "order_ack|" + status + "|" + venue + "|" + message;
}

string QbRejectSpec(string errorJson)
{
   return "order_reject|" + errorJson;
}

string QbReplayFrame(string spec, string cmdMessageId, string traceId,
                     string intentId, long sequence)
{
   string parts[];
   StringSplit(spec, '|', parts);
   if(ArraySize(parts) >= 4 && parts[0] == "order_ack")
      return QbAckFrame(cmdMessageId, traceId, intentId, sequence,
                        parts[1], parts[2], true, parts[3]);
   if(ArraySize(parts) >= 2 && parts[0] == "order_reject")
      return QbRejectFrame(cmdMessageId, traceId, intentId, sequence, parts[1]);
   return QbRejectFrame(cmdMessageId, traceId, intentId, sequence,
                        QbBuildError(QB_ERR_INTERNAL_ERROR, "cannot replay stored outcome",
                                     "", traceId, intentId, "", sequence));
}

//+------------------------------------------------------------------+
//| Broker-side error mapping (MT4 GetLastError → protocol code)      |
//+------------------------------------------------------------------+
string QbBrokerErrorCode(int error)
{
   if(error == 138) return QB_ERR_SLIPPAGE_CAP_EXCEEDED;  // ERR_REQUOTE
   if(error == 134) return QB_ERR_INSUFFICIENT_MARGIN;    // ERR_NOT_ENOUGH_MONEY
   if(error == 133) return QB_ERR_TRADING_DISABLED;       // ERR_TRADE_DISABLED
   if(error == 130) return QB_ERR_STOP_LEVEL_VIOLATION;   // ERR_INVALID_STOPS
   if(error == 129) return QB_ERR_INVALID_MODIFICATION;   // ERR_INVALID_PRICE
   if(error == 131) return QB_ERR_LOT_LIMIT_EXCEEDED;     // ERR_INVALID_TRADE_VOLUME
   if(error == 4108) return QB_ERR_BROKER_DISCONNECTED;   // ERR_TRADE_TIMEOUT? — 4108 trade context busy, keep generic
   return QB_ERR_BROKER_ERROR;
}

//+------------------------------------------------------------------+
//| Venue checks — port of broker._venue_checks + _stop_level_check   |
//| Returns "" when the order may proceed, else an error JSON.       |
//+------------------------------------------------------------------+
string QbVenueChecks(string symbol, string side, string orderType,
                     double qty, double price, double stopLoss, double takeProfit,
                     string intentId, string traceId, long sequence)
{
   // 1. trading enabled
   if(AccountInfoInteger(ACCOUNT_TRADE_EXPERT) == 0)
      return QbBuildError(QB_ERR_TRADING_DISABLED, "trading disabled", "",
                          traceId, intentId, symbol, sequence);
   // 2. market open for this symbol
   if(MarketInfo(symbol, MODE_TRADEALLOWED) == 0)
      return QbBuildError(QB_ERR_MARKET_CLOSED, "market closed", "",
                          traceId, intentId, symbol, sequence);
   // 3. symbol whitelist
   if(InputSymbolWhitelist != "")
   {
      string items[];
      StringSplit(InputSymbolWhitelist, ',', items);
      bool allowed = false;
      for(int i = 0; i < ArraySize(items); i++)
      {
         if(QbTrim(items[i]) == symbol)
         {
            allowed = true;
            break;
         }
      }
      if(!allowed)
         return QbBuildError(QB_ERR_SYMBOL_NOT_ALLOWED, "symbol not whitelisted", "",
                             traceId, intentId, symbol, sequence);
   }
   // 4. lot limits and step
   double minLot = MarketInfo(symbol, MODE_MINLOT);
   double maxLot = MarketInfo(symbol, MODE_MAXLOT);
   double lotStep = MarketInfo(symbol, MODE_LOTSTEP);
   if(qty < minLot)
      return QbBuildError(QB_ERR_LOT_LIMIT_EXCEEDED, "below min_lot", "",
                          traceId, intentId, symbol, sequence);
   if(qty > maxLot)
      return QbBuildError(QB_ERR_LOT_LIMIT_EXCEEDED, "above max_lot", "",
                          traceId, intentId, symbol, sequence);
   double remainder = qty - MathRound(qty / lotStep) * lotStep;
   if(MathAbs(remainder) > 1e-9)
      return QbBuildError(QB_ERR_LOT_STEP_INVALID, "not a lot_step multiple", "",
                          traceId, intentId, symbol, sequence);
   // 5. quote freshness
   datetime lastQuote = (datetime)MarketInfo(symbol, MODE_TIME);
   if(lastQuote > 0 && (TimeGMT() - lastQuote) > InputMaxQuoteAgeSeconds)
      return QbBuildError(QB_ERR_STALE_QUOTES, "quotes too old", "",
                          traceId, intentId, symbol, sequence);
   // 6. spread cap
   double spreadPoints = (MarketInfo(symbol, MODE_ASK) - MarketInfo(symbol, MODE_BID)) / Point;
   if(spreadPoints > InputMaxSpreadPoints)
      return QbBuildError(QB_ERR_SPREAD_TOO_HIGH, "spread over limit", "",
                          traceId, intentId, symbol, sequence);
   // 7. stop levels (buy SL below ref, TP above; sell reversed; distance >= stop level)
   double reference = price;
   if(orderType == "MARKET")
      reference = (side == "BUY") ? MarketInfo(symbol, MODE_ASK) : MarketInfo(symbol, MODE_BID);
   double stopLevel = MarketInfo(symbol, MODE_STOPLEVEL) * Point;
   if(stopLoss != 0.0)
   {
      if(side == "BUY" && stopLoss >= reference)
         return QbBuildError(QB_ERR_STOP_LEVEL_VIOLATION, "buy stop_loss must be below price", "",
                             traceId, intentId, symbol, sequence);
      if(side == "SELL" && stopLoss <= reference)
         return QbBuildError(QB_ERR_STOP_LEVEL_VIOLATION, "sell stop_loss must be above price", "",
                             traceId, intentId, symbol, sequence);
      if(MathAbs(reference - stopLoss) < stopLevel)
         return QbBuildError(QB_ERR_STOP_LEVEL_VIOLATION, "stop_loss within stop_level", "",
                             traceId, intentId, symbol, sequence);
   }
   if(takeProfit != 0.0)
   {
      if(side == "BUY" && takeProfit <= reference)
         return QbBuildError(QB_ERR_STOP_LEVEL_VIOLATION, "buy take_profit must be above price", "",
                             traceId, intentId, symbol, sequence);
      if(side == "SELL" && takeProfit >= reference)
         return QbBuildError(QB_ERR_STOP_LEVEL_VIOLATION, "sell take_profit must be below price", "",
                             traceId, intentId, symbol, sequence);
      if(MathAbs(reference - takeProfit) < stopLevel)
         return QbBuildError(QB_ERR_STOP_LEVEL_VIOLATION, "take_profit within stop_level", "",
                             traceId, intentId, symbol, sequence);
   }
   // 8. free margin (MQL4: MODE_MARGINREQUIRED = margin for 1.0 lot)
   double required = qty * MarketInfo(symbol, MODE_MARGINREQUIRED);
   if(required > AccountFreeMargin())
      return QbBuildError(QB_ERR_INSUFFICIENT_MARGIN, "free margin too low", "",
                          traceId, intentId, symbol, sequence);
   return "";
}

//+------------------------------------------------------------------+
//| side + order type → MQL4 order operation code                    |
//+------------------------------------------------------------------+
int QbOrderOp(string side, string orderType)
{
   if(side == "BUY")
   {
      if(orderType == "MARKET")     return OP_BUY;
      if(orderType == "LIMIT")      return OP_BUYLIMIT;
      if(orderType == "STOP")       return OP_BUYSTOP;
   }
   else
   {
      if(orderType == "MARKET")     return OP_SELL;
      if(orderType == "LIMIT")      return OP_SELLLIMIT;
      if(orderType == "STOP")       return OP_SELLSTOP;
   }
   return -1;   // STOP_LIMIT / unknown: rejected by caller
}

bool QbIsPendingOp(int op)
{
   return op == OP_BUYLIMIT || op == OP_SELLLIMIT || op == OP_BUYSTOP || op == OP_SELLSTOP;
}

//+------------------------------------------------------------------+
//| Canonical PositionSnapshot for one MT4 position                  |
//+------------------------------------------------------------------+
string QbPositionJson(int ticket, int magic, string strategyId, string intentId)
{
   string symbol = OrderSymbol();
   string side = (OrderType() == OP_BUY) ? "LONG" : "SHORT";
   double qty = OrderLots();
   double entry = OrderOpenPrice();
   double mark = (OrderType() == OP_BUY) ? MarketInfo(symbol, MODE_BID)
                                         : MarketInfo(symbol, MODE_ASK);
   string sourceIds = (intentId != "")
                    ? "{\"order_intent_id\":\"" + intentId + "\"}"
                    : "{}";
   string out = "{\"position_id\":\"mt4-" + IntegerToString(ticket) + "\"";
   out += ",\"trace_id\":\"" + (intentId != "" ? intentId : QbUuid5(g_bridgeUuid, "pos-" + IntegerToString(ticket))) + "\"";
   out += ",\"produced_at\":\"" + QbUtcNowIso() + "\"";
   out += ",\"provenance\":{\"producer\":\"mt4-quantbridge\",\"produced_at\":\"" + QbUtcNowIso() + "\",\"source_ids\":" + sourceIds + "}";
   out += ",\"account_id\":\"" + IntegerToString((int)AccountInfoInteger(ACCOUNT_LOGIN)) + "\"";
   out += ",\"strategy_id\":\"" + QbJsonEscape(strategyId) + "\"";
   out += ",\"instrument_id\":\"" + QbJsonEscape(symbol) + "\"";
   out += ",\"side\":\"" + side + "\"";
   out += ",\"quantity\":\"" + QbNumStr(qty) + "\"";
   out += ",\"average_entry_price\":\"" + QbNumStr(entry) + "\"";
   out += ",\"mark_price\":\"" + QbNumStr(mark) + "\"";
   out += ",\"as_of\":\"" + QbUtcNowIso() + "\"}";
   return out;
}

//+------------------------------------------------------------------+
//| position_snapshot event: all positions carrying a bridge magic   |
//+------------------------------------------------------------------+
string QbPositionsListJson()
{
   string list = "[";
   int count = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      int op = OrderType();
      if(op != OP_BUY && op != OP_SELL)
         continue;
      string intent = QbIntentByTicket(OrderTicket());
      string strategy = "";
      if(intent != "")
      {
         for(int k = 0; k < g_ticketCount; k++)
         {
            if(g_tickets[k].ticket == OrderTicket())
            {
               strategy = g_tickets[k].strategy;
               break;
            }
         }
      }
      if(count > 0)
         list += ",";
      list += "{\"venue_position_id\":\"" + IntegerToString(OrderTicket()) + "\"";
      list += ",\"magic\":" + IntegerToString(OrderMagicNumber());
      list += ",\"position\":" + QbPositionJson(OrderTicket(), OrderMagicNumber(), strategy, intent);
      list += "}";
      count++;
   }
   list += "]";
   return list;
}

string QbPositionSnapshotEvent()
{
   return QbEventFrame(QB_MSG_POSITION_SNAPSHOT,
      "\"account_id\":\"" + IntegerToString((int)AccountInfoInteger(ACCOUNT_LOGIN))
      + "\",\"positions\":" + QbPositionsListJson());
}

//+------------------------------------------------------------------+
//| account_snapshot event                                           |
//+------------------------------------------------------------------+
string QbAccountJson()
{
   string out = "{\"account_id\":\"" + IntegerToString((int)AccountInfoInteger(ACCOUNT_LOGIN)) + "\"";
   bool isDemo = AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO;
   out += ",\"is_demo\":" + (isDemo ? "true" : "false");
   out += ",\"currency\":\"" + AccountInfoString(ACCOUNT_CURRENCY) + "\"";
   out += ",\"balance\":\"" + QbNumStr(AccountInfoDouble(ACCOUNT_BALANCE)) + "\"";
   out += ",\"equity\":\"" + QbNumStr(AccountInfoDouble(ACCOUNT_EQUITY)) + "\"";
   out += ",\"margin\":\"" + QbNumStr(AccountInfoDouble(ACCOUNT_MARGIN)) + "\"";
   out += ",\"free_margin\":\"" + QbNumStr(AccountInfoDouble(ACCOUNT_MARGIN_FREE)) + "\"";
   out += ",\"as_of\":\"" + QbUtcNowIso() + "\"}";
   return out;
}

string QbAccountSnapshotEvent()
{
   return QbEventFrame(QB_MSG_ACCOUNT_SNAPSHOT, "\"account\":" + QbAccountJson());
}

//+------------------------------------------------------------------+
//| heartbeat event                                                  |
//+------------------------------------------------------------------+
string QbHeartbeatEvent()
{
   bool connected = TerminalInfoInteger(TERMINAL_CONNECTED) != 0;
   bool trading = AccountInfoInteger(ACCOUNT_TRADE_EXPERT) != 0;
   return QbEventFrame(QB_MSG_HEARTBEAT,
      "\"broker_connected\":" + (connected ? "true" : "false")
      + ",\"trading_enabled\":" + (trading ? "true" : "false"));
}

//+------------------------------------------------------------------+
//| fill / partial_fill events (market fills are full fills in MT4)  |
//+------------------------------------------------------------------+
string QbFillEvent(string intentId, string venueOrderId, double filledQty,
                   double fillPrice, double slippage, string symbol, string side)
{
   string out = "\"order_intent_id\":\"" + intentId + "\"";
   out += ",\"venue_order_id\":\"" + venueOrderId + "\"";
   out += ",\"filled_quantity\":\"" + QbNumStr(filledQty) + "\"";
   out += ",\"average_fill_price\":\"" + QbNumStr(fillPrice) + "\"";
   out += ",\"commission\":\"" + QbNumStr(OrderCommission()) + "\"";
   out += ",\"slippage\":\"" + QbNumStr(slippage) + "\"";
   out += ",\"symbol\":\"" + QbJsonEscape(symbol) + "\"";
   out += ",\"side\":\"" + side + "\"";
   return QbEventFrame(QB_MSG_FILL, out);
}

//+------------------------------------------------------------------+
//| ── Command handlers ──────────────────────────────────────────────|
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//| submit_order                                                     |
//+------------------------------------------------------------------+
string QbHandleSubmit(string &specOut)
{
   string intentId = QbJsonGetString("order_intent_id");
   string strategyId = QbJsonGetString("strategy_id");
   long sequence = QbJsonGetLong("sequence");
   string symbol = QbJsonGetString("symbol");
   string side = QbJsonGetString("side");
   string orderType = QbJsonGetString("order_type");
   double qty = QbJsonGetDouble("quantity");
   double price = QbJsonGetDouble("price");
   double stopLoss = QbJsonGetDouble("stop_loss");
   double takeProfit = QbJsonGetDouble("take_profit");
   double maxSlippage = QbJsonGetDouble("max_slippage");
   string traceId = QbJsonGetString("trace_id");
   string cmdId = QbJsonGetString("message_id");

   int op = QbOrderOp(side, orderType);
   if(op < 0)
   {
      string err = QbBuildError(QB_ERR_BROKER_ERROR, "order type not supported by OrderSend",
                                "STOP_LIMIT requires broker stop-limit support", traceId, intentId, symbol, sequence);
      specOut = QbRejectSpec(err);
      return QbRejectFrame(cmdId, traceId, intentId, sequence, err);
   }

   // EA defense-in-depth venue checks (INV-5, §8) — before any OrderSend.
   string venueError = QbVenueChecks(symbol, side, orderType, qty, price,
                                     stopLoss, takeProfit, intentId, traceId, sequence);
   if(venueError != "")
   {
      specOut = QbRejectSpec(venueError);
      return QbRejectFrame(cmdId, traceId, intentId, sequence, venueError);
   }

   double orderPrice = price;
   if(orderType == "MARKET")
      orderPrice = (side == "BUY") ? MarketInfo(symbol, MODE_ASK) : MarketInfo(symbol, MODE_BID);
   int slippagePoints = (int)MathRound(maxSlippage / Point);
   int magic = QbStrategyMagic(strategyId);
   string comment = "QB:" + QbSha256Hex(intentId);
   if(StringLen(comment) > 31)
      comment = StringSubstr(comment, 0, 31);

   int ticket = OrderSend(symbol, op, qty, orderPrice, slippagePoints,
                          stopLoss, takeProfit, comment, magic, 0, clrNONE);
   if(ticket < 0)
   {
      int brokerError = GetLastError();
      string err = QbBuildError(QbBrokerErrorCode(brokerError), "OrderSend failed",
                               "MT4 error " + IntegerToString(brokerError), traceId, intentId, symbol, sequence);
      specOut = QbRejectSpec(err);
      return QbRejectFrame(cmdId, traceId, intentId, sequence, err);
   }

   QbAddTicket(ticket, intentId, strategyId);

   if(orderType == "MARKET")
   {
      if(!OrderSelect(ticket, SELECT_BY_TICKET))
      {
         specOut = QbAckSpec("FILLED", IntegerToString(ticket), "");
         return QbAckFrame(cmdId, traceId, intentId, sequence, "FILLED",
                           IntegerToString(ticket), false, "");
      }
      double fillPrice = OrderOpenPrice();
      double slippage = (side == "BUY") ? (fillPrice - orderPrice) : (orderPrice - fillPrice);
      QbZmqPushEvent(QbFillEvent(intentId, IntegerToString(ticket), qty, fillPrice, slippage, symbol, side));
      QbZmqPushEvent(QbPositionSnapshotEvent());
      QbZmqPushEvent(QbAccountSnapshotEvent());
      specOut = QbAckSpec("FILLED", IntegerToString(ticket), "");
      return QbAckFrame(cmdId, traceId, intentId, sequence, "FILLED",
                        IntegerToString(ticket), false, "");
   }
   specOut = QbAckSpec("SUBMITTED", IntegerToString(ticket), "");
   return QbAckFrame(cmdId, traceId, intentId, sequence, "SUBMITTED",
                     IntegerToString(ticket), false, "");
}

//+------------------------------------------------------------------+
//| cancel_order                                                     |
//+------------------------------------------------------------------+
string QbHandleCancel(string &specOut)
{
   string intentId = QbJsonGetString("order_intent_id");
   string symbol = QbJsonGetString("symbol");
   string reason = QbJsonGetString("reason");
   long sequence = QbJsonGetLong("sequence");
   string traceId = QbJsonGetString("trace_id");
   string cmdId = QbJsonGetString("message_id");

   int ticket = QbTicketByIntent(intentId);
   if(ticket < 0 || !OrderSelect(ticket, SELECT_BY_TICKET, MODE_TRADES))
   {
      string err;
      if(ticket >= 0)
         err = QbBuildError(QB_ERR_ORDER_NOT_ACTIVE, "order already filled", "",
                            traceId, intentId, symbol, sequence);
      else
         err = QbBuildError(QB_ERR_UNKNOWN_ORDER, "no such order", "",
                            traceId, intentId, symbol, sequence);
      specOut = QbRejectSpec(err);
      return QbRejectFrame(cmdId, traceId, intentId, sequence, err);
   }
   if(!QbIsPendingOp(OrderType()))
   {
      string err = QbBuildError(QB_ERR_ORDER_NOT_ACTIVE, "order already filled", "",
                                traceId, intentId, symbol, sequence);
      specOut = QbRejectSpec(err);
      return QbRejectFrame(cmdId, traceId, intentId, sequence, err);
   }

   if(!OrderDelete(ticket))
   {
      int brokerError = GetLastError();
      string err = QbBuildError(QbBrokerErrorCode(brokerError), "OrderDelete failed",
                               "MT4 error " + IntegerToString(brokerError), traceId, intentId, symbol, sequence);
      specOut = QbRejectSpec(err);
      return QbRejectFrame(cmdId, traceId, intentId, sequence, err);
   }
   QbRemoveTicket(ticket);
   specOut = QbAckSpec("CANCELLED", IntegerToString(ticket), reason);
   return QbAckFrame(cmdId, traceId, intentId, sequence, "CANCELLED",
                     IntegerToString(ticket), false, reason);
}

//+------------------------------------------------------------------+
//| modify_order                                                     |
//+------------------------------------------------------------------+
string QbHandleModify(string &specOut)
{
   string intentId = QbJsonGetString("order_intent_id");
   string symbol = QbJsonGetString("symbol");
   string side = QbJsonGetString("side");
   long sequence = QbJsonGetLong("sequence");
   string traceId = QbJsonGetString("trace_id");
   string cmdId = QbJsonGetString("message_id");
   string newPriceRaw = QbJsonGetRaw("new_price");
   string newSlRaw = QbJsonGetRaw("new_stop_loss");
   string newTpRaw = QbJsonGetRaw("new_take_profit");

   int ticket = QbTicketByIntent(intentId);
   if(ticket < 0 || !OrderSelect(ticket, SELECT_BY_TICKET, MODE_TRADES))
   {
      string err = QbBuildError(QB_ERR_UNKNOWN_ORDER, "no such order", "",
                                traceId, intentId, symbol, sequence);
      specOut = QbRejectSpec(err);
      return QbRejectFrame(cmdId, traceId, intentId, sequence, err);
   }
   if(!QbIsPendingOp(OrderType()))
   {
      string err = QbBuildError(QB_ERR_ORDER_NOT_ACTIVE, "order already filled", "",
                                traceId, intentId, symbol, sequence);
      specOut = QbRejectSpec(err);
      return QbRejectFrame(cmdId, traceId, intentId, sequence, err);
   }

   double newPrice = (newPriceRaw != "null") ? QbJsonGetDouble("new_price") : OrderOpenPrice();
   double newSl = (newSlRaw != "null") ? QbJsonGetDouble("new_stop_loss") : OrderStopLoss();
   double newTp = (newTpRaw != "null") ? QbJsonGetDouble("new_take_profit") : OrderTakeProfit();

   // freeze-level guard on price moves (broker.py process_modify)
   if(newPriceRaw != "null" && MathAbs(newPrice - OrderOpenPrice()) < MarketInfo(symbol, MODE_FREEZELEVEL) * Point)
   {
      string err = QbBuildError(QB_ERR_STOP_LEVEL_VIOLATION, "price move within freeze_level", "",
                                traceId, intentId, symbol, sequence);
      specOut = QbRejectSpec(err);
      return QbRejectFrame(cmdId, traceId, intentId, sequence, err);
   }

   // stop-level re-check on the amended values (pending order: LIMIT checks)
   string stopError = QbVenueChecks(symbol, side, "LIMIT", OrderLots(), newPrice,
                                    newSl, newTp, intentId, traceId, sequence);
   if(stopError != "")
   {
      specOut = QbRejectSpec(stopError);
      return QbRejectFrame(cmdId, traceId, intentId, sequence, stopError);
   }

   if(!OrderModify(ticket, newPrice, newSl, newTp, 0))
   {
      int brokerError = GetLastError();
      string code = (brokerError == 130) ? QB_ERR_STOP_LEVEL_VIOLATION : QbBrokerErrorCode(brokerError);
      string err = QbBuildError(code, "OrderModify failed",
                                "MT4 error " + IntegerToString(brokerError), traceId, intentId, symbol, sequence);
      specOut = QbRejectSpec(err);
      return QbRejectFrame(cmdId, traceId, intentId, sequence, err);
   }
   specOut = QbAckSpec("MODIFIED", IntegerToString(ticket), "");
   return QbAckFrame(cmdId, traceId, intentId, sequence, "MODIFIED",
                     IntegerToString(ticket), false, "");
}

//+------------------------------------------------------------------+
//| reconciliation_request — stateless snapshot (INV-6)              |
//+------------------------------------------------------------------+
string QbHandleReconcile()
{
   string cmdId = QbJsonGetString("message_id");
   string traceId = QbJsonGetString("trace_id");
   string id = QbUuid5(cmdId, QB_MSG_RECONCILIATION_RESPONSE);
   string out = QbEnvelope(QB_MSG_RECONCILIATION_RESPONSE, id, traceId, 0, cmdId);
   out += ",\"account\":" + QbAccountJson();
   out += ",\"positions\":" + QbPositionsListJson();
   // open (pending) orders that carry a bridge magic, mapped to intents
   string openIntents = "[";
   int count = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      if(!QbIsPendingOp(OrderType()))
         continue;
      string intent = QbIntentByTicket(OrderTicket());
      if(intent == "")
         continue;
      if(count > 0)
         openIntents += ",";
      openIntents += "\"" + intent + "\"";
      count++;
   }
   openIntents += "]";
   out += ",\"open_order_intent_ids\":" + openIntents;
   out += ",\"last_sequences\":" + QbSeqSnapshotJson();
   bool connected = TerminalInfoInteger(TERMINAL_CONNECTED) != 0;
   bool trading = AccountInfoInteger(ACCOUNT_TRADE_EXPERT) != 0;
   out += ",\"broker_connected\":" + (connected ? "true" : "false");
   out += ",\"trading_enabled\":" + (trading ? "true" : "false");
   out += "}";
   return out;
}

//+------------------------------------------------------------------+
//| Safe-mode override: MQL4\Files\QuantBridgeSafeMode.txt           |
//|   "1" (or missing/other) → safe mode ON (blocks new entries)     |
//|   "0"                  → normal operation                       |
//| The operator pipeline flips this file after a clean              |
//| reconciliation (INV-6); the wire protocol can never clear it.    |
//+------------------------------------------------------------------+
bool QbSafeModeActive()
{
   int handle = FileOpen("QuantBridgeSafeMode.txt", FILE_READ | FILE_TXT);
   if(handle == INVALID_HANDLE)
      return InputSafeMode;
   string content = QbTrim(FileReadString(handle));
   FileClose(handle);
   if(content == "0")
      return false;
   return true;
}

//+------------------------------------------------------------------+
//| One inbound frame → reply frame (mirror of emulator._handle)      |
//+------------------------------------------------------------------+
string QbHandleCommand(string frame)
{
   if(!QbJsonParse(frame))
      return QbRejectFrame("", "null", "", 0,
         QbBuildError(QB_ERR_SCHEMA_INVALID, "malformed JSON frame", "", "null", "", "", 0));

   string messageType = QbJsonGetString("message_type");
   string traceId = QbJsonGetString("trace_id");
   string cmdId = QbJsonGetString("message_id");

   if(messageType == "")
      return QbRejectFrame(cmdId, traceId, "", 0,
         QbBuildError(QB_ERR_SCHEMA_INVALID, "missing message_type", "", traceId, "", "", 0));

   bool known = messageType == QB_MSG_SUBMIT_ORDER || messageType == QB_MSG_CANCEL_ORDER
             || messageType == QB_MSG_MODIFY_ORDER || messageType == QB_MSG_RECONCILIATION_REQUEST;
   if(!known)
      return QbRejectFrame(cmdId, traceId, "", 0,
         QbBuildError(QB_ERR_UNKNOWN_MESSAGE_TYPE, "expected a command message", "",
                      traceId, "", "", 0));

   // 2. protocol version: MAJOR mismatch is a hard reject.
   string version = QbJsonGetString("protocol_version");
   string parts[];
   StringSplit(version, '.', parts);
   if(ArraySize(parts) == 0 || parts[0] != "1")
      return QbRejectFrame(cmdId, traceId, "", 0,
         QbBuildError(QB_ERR_VERSION_MISMATCH, "protocol version incompatible", "",
                      traceId, "", "", 0));

   // 3. checksum (Core always sends one; verification is optional per spec §9).
   if(InputVerifyChecksums && QbJsonGetRaw("checksum") != "null")
   {
      string checksumError = QbVerifyChecksum();
      if(checksumError != "")
         return QbRejectFrame(cmdId, traceId, "", 0,
            QbBuildError(QB_ERR_CHECKSUM_MISMATCH, checksumError, "",
                         traceId, "", "", 0));
   }

   string intentId = QbJsonGetString("order_intent_id");
   string strategyId = QbJsonGetString("strategy_id");
   long sequence = QbJsonGetLong("sequence");
   string symbol = QbJsonGetString("symbol");

   // Safe mode blocks new entries (mirror emulator, before the gate).
   if(QbSafeModeActive() && messageType == QB_MSG_SUBMIT_ORDER)
      return QbRejectFrame(cmdId, traceId, intentId, sequence,
         QbBuildError(QB_ERR_SAFE_MODE_ACTIVE, "reconciliation divergence — new entries blocked (INV-6)", "",
                      traceId, intentId, symbol, sequence));

   // 4-6. Gate: expiration → duplicates → sequence (guards.py port).
   string fingerprint = QbFingerprint(messageType);
   string expiresAt = QbJsonGetString("expires_at");
   QbGateOutcome gate = QbGateEvaluate(messageType, intentId, strategyId,
                                       sequence, expiresAt, fingerprint);
   if(gate.replay != "")
      return QbReplayFrame(gate.replay, cmdId, traceId, intentId, sequence);
   if(gate.error != "")
      return QbRejectFrame(cmdId, traceId, intentId, sequence, gate.error);

   // Dispatch (handlers also return the ledger replay spec).
   string spec = "";
   string reply = "";
   if(messageType == QB_MSG_SUBMIT_ORDER)
      reply = QbHandleSubmit(spec);
   else if(messageType == QB_MSG_CANCEL_ORDER)
      reply = QbHandleCancel(spec);
   else if(messageType == QB_MSG_MODIFY_ORDER)
      reply = QbHandleModify(spec);
   else if(messageType == QB_MSG_RECONCILIATION_REQUEST)
      reply = QbHandleReconcile();
   else
      reply = QbRejectFrame(cmdId, traceId, intentId, sequence,
         QbBuildError(QB_ERR_UNKNOWN_MESSAGE_TYPE, "no dispatch for message type", "",
                      traceId, intentId, symbol, sequence));

   // Record the outcome (idempotency memory) — reconciliation is stateless.
   if(messageType != QB_MSG_RECONCILIATION_REQUEST)
      QbGateRecord(messageType, intentId, strategyId, sequence, fingerprint, spec);
   return reply;
}

//+------------------------------------------------------------------+
//| EA lifecycle                                                     |
//+------------------------------------------------------------------+
int OnInit()
{
   g_bridgeUuid = QbUuid5("00000000-0000-0000-0000-000000000000", InputBridgeId);
   g_eventSeq = 0;
   g_lastHeartbeat = 0;
   g_ticketCount = 0;

   if(InputPollMilliseconds > 0)
      EventSetMillisecondTimer(InputPollMilliseconds);

   bool up = QbZmqInit(InputCommandAddr, InputEventsAddr, InputQuotesAddr);
   Print("QuantBridgeEA ", QB_PROTOCOL_VERSION, " bridge=", InputBridgeId,
         " uuid=", g_bridgeUuid,
         " safeMode=", InputSafeMode, " transport=", up ? "up" : "disabled");
   if(InputSafeMode)
      Print("QuantBridgeEA: SAFE MODE — new entries blocked until reconciliation clears.");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   QbZmqDeinit();
   Print("QuantBridgeEA stopped (", reason, ")");
}

void OnTimer()
{
   // Command channel: one frame per poll cycle.
   string frame = QbZmqRecvCommand();
   if(frame != "")
   {
      string reply = QbHandleCommand(frame);
      QbZmqSendReply(reply);
   }

   // Heartbeat stream (dead-man semantics, INV-7).
   if((TimeGMT() - g_lastHeartbeat) >= InputHeartbeatSeconds)
   {
      QbZmqPushEvent(QbHeartbeatEvent());
      g_lastHeartbeat = TimeGMT();
   }
}

void OnTick()
{
   // Market quotes: topic = symbol, multipart PUB.
   if(InputSymbolWhitelist != "")
   {
      string items[];
      StringSplit(InputSymbolWhitelist, ',', items);
      for(int i = 0; i < ArraySize(items); i++)
         QbPublishQuoteFor(QbTrim(items[i]));
   }
   else
   {
      QbPublishQuoteFor(Symbol());
   }
}

//+------------------------------------------------------------------+
//| Publish one market_quote frame                                   |
//+------------------------------------------------------------------+
void QbPublishQuoteFor(string symbol)
{
   if(symbol == "")
      return;
   double bid = MarketInfo(symbol, MODE_BID);
   double ask = MarketInfo(symbol, MODE_ASK);
   if(bid <= 0.0 || ask <= 0.0)
      return;
   bool tradable = MarketInfo(symbol, MODE_TRADEALLOWED) != 0;
   g_eventSeq++;
   string id = QbUuid5(g_bridgeUuid, "quote-" + symbol + "-" + QbNumStr(bid) + "-" + QbNumStr(ask));
   string payload = QbEnvelope(QB_MSG_MARKET_QUOTE, id, "null", g_eventSeq, "");
   payload += ",\"symbol\":\"" + QbJsonEscape(symbol) + "\"";
   payload += ",\"bid\":\"" + QbNumStr(bid) + "\"";
   payload += ",\"ask\":\"" + QbNumStr(ask) + "\"";
   payload += ",\"spread\":\"" + QbNumStr(ask - bid) + "\"";
   payload += ",\"tradable\":" + (tradable ? "true" : "false");
   payload += "}";
   QbZmqPublishQuote(symbol, payload);
}
//+------------------------------------------------------------------+
