//+------------------------------------------------------------------+
//| Execution.mqh - order execution and reconciliation (spec §9, §13)  |
//|                                                                   |
//| "Signal is valid" and "order is executable" are SEPARATE concerns. |
//| A valid signal that fails a guard is rejected and logged - never   |
//| rescued by relaxing the signal, widening the stop, or increasing   |
//| risk to obtain broker acceptance.                                  |
//|                                                                   |
//| Retries are bounded and error-aware: only genuinely transient MT4  |
//| errors are retried. Invalid stops, invalid volume and insufficient |
//| margin are TERMINAL - retrying them is how EAs spin forever.       |
//|                                                                   |
//| Part of XAU_RPB_V1.0.0.                                            |
//+------------------------------------------------------------------+
#property strict

#ifndef XAU_RPB_EXECUTION_MQH
#define XAU_RPB_EXECUTION_MQH

#include "Config.mqh"
#include "BrokerSpec.mqh"
#include "Risk.mqh"

//+------------------------------------------------------------------+
//| Is an MT4 error worth another attempt?                            |
//+------------------------------------------------------------------+
bool IsTransientError(const int code)
{
   switch(code)
   {
      case ERR_SERVER_BUSY:            // 4
      case ERR_NO_CONNECTION:          // 6
      case ERR_TRADE_TIMEOUT:          // 128
      case ERR_INVALID_PRICE:          // 129 (requote-adjacent: price moved)
      case ERR_PRICE_CHANGED:          // 135
      case ERR_OFF_QUOTES:             // 136
      case ERR_BROKER_BUSY:            // 137
      case ERR_REQUOTE:                // 138
      case ERR_TRADE_CONTEXT_BUSY:     // 146
         return(true);
   }
   return(false);
}

//--- Terminal errors: retrying cannot help and would only spin.
bool IsTerminalError(const int code)
{
   switch(code)
   {
      case ERR_INVALID_STOPS:          // 130
      case ERR_INVALID_TRADE_VOLUME:   // 131
      case ERR_NOT_ENOUGH_MONEY:       // 134
      case ERR_TRADE_DISABLED:         // 133
      case ERR_LONG_POSITIONS_ONLY_ALLOWED: // 140
         return(true);
   }
   return(false);
}

struct ExecutionContext
{
   BrokerSpec   spec;
   RpbExecution ex;
   RpbMode      mode;
};

//+------------------------------------------------------------------+
//| Broker-side validation of a prospective order (spec §9).          |
//| Returns "" when every guard passes.                               |
//+------------------------------------------------------------------+
string ValidateOrderPreconditions(const ExecutionContext &ctx, const int orderType,
                                  const double lots, const double price,
                                  const double stopLoss)
{
   if(!IsTradeAllowed())
      return(RPB_REJ_TRADE_DISABLED);
   if(!ctx.spec.valid)
      return(RPB_REJ_SPEC_INVALID);

   if(lots < ctx.spec.minLot || lots > ctx.spec.maxLot)
      return(RPB_REJ_SIZE_ZERO);

   // Lot must sit on a valid step boundary.
   double steps = lots / ctx.spec.lotStep;
   if(MathAbs(steps - MathRound(steps)) > 1.0e-6)
      return(RPB_REJ_SIZE_ZERO);

   // Broker minimum stop distance (MODE_STOPLEVEL) and freeze band.
   double minDistance = ctx.spec.stopLevelPoints * ctx.spec.point;
   if(minDistance > 0.0 && MathAbs(price - stopLoss) < minDistance)
      return(RPB_REJ_STOP_LEVEL);

   double freezeDistance = ctx.spec.freezeLevelPoints * ctx.spec.point;
   if(freezeDistance > 0.0 && MathAbs(price - stopLoss) < freezeDistance)
      return(RPB_REJ_STOP_LEVEL);

   // Free margin must survive the order. Leverage determines margin, never risk.
   double freeMargin = AccountFreeMarginCheck(ctx.spec.symbol, orderType, lots);
   if(freeMargin <= 0.0 || GetLastError() == ERR_NOT_ENOUGH_MONEY)
      return(RPB_REJ_MARGIN);

   return(RPB_REJ_NONE);
}

//+------------------------------------------------------------------+
//| Submit a market order with bounded, error-aware retries.          |
//| Returns the ticket, or -1. In SHADOW mode nothing is ever sent.   |
//+------------------------------------------------------------------+
int SendMarketOrder(const ExecutionContext &ctx, const int orderType, const double lots,
                    const double stopLoss, const double takeProfit, string &outError)
{
   outError = RPB_REJ_NONE;

   if(ctx.mode == MODE_SHADOW)
   {
      Print("XAU_RPB SHADOW: would send ", (orderType == OP_BUY ? "BUY" : "SELL"),
            " lots=", DoubleToString(lots, 2),
            " sl=", DoubleToString(stopLoss, ctx.spec.digits),
            " tp=", DoubleToString(takeProfit, ctx.spec.digits),
            " - no order submitted");
      return(-1);
   }

   int attempt = 0;
   while(attempt < ctx.ex.maxRetries)
   {
      attempt++;
      RefreshRates();

      double price = (orderType == OP_BUY)
                     ? MarketInfo(ctx.spec.symbol, MODE_ASK)
                     : MarketInfo(ctx.spec.symbol, MODE_BID);
      if(price <= 0.0)
      {
         outError = RPB_REJ_QUOTE_STALE;
         return(-1);
      }

      string guard = ValidateOrderPreconditions(ctx, orderType, lots, price, stopLoss);
      if(StringLen(guard) > 0)
      {
         outError = guard;
         Print("XAU_RPB ORDER_BLOCKED reason=", guard,
               " lots=", DoubleToString(lots, 2),
               " price=", DoubleToString(price, ctx.spec.digits),
               " sl=", DoubleToString(stopLoss, ctx.spec.digits));
         return(-1);
      }

      ResetLastError();
      int ticket = OrderSend(
         ctx.spec.symbol,
         orderType,
         NormalizeDouble(lots, LotDigits(ctx.spec.lotStep)),
         NormalizeDouble(price, ctx.spec.digits),
         ctx.ex.maxSlippagePoints,
         NormalizeDouble(stopLoss, ctx.spec.digits),
         (takeProfit > 0.0 ? NormalizeDouble(takeProfit, ctx.spec.digits) : 0.0),
         XAU_RPB_COMMENT_PREFIX,
         ctx.ex.magicNumber,
         0,
         clrNONE);

      if(ticket >= 0)
      {
         Print("XAU_RPB ORDER_SENT ticket=", ticket,
               " type=", (orderType == OP_BUY ? "BUY" : "SELL"),
               " lots=", DoubleToString(lots, 2),
               " requested=", DoubleToString(price, ctx.spec.digits),
               " sl=", DoubleToString(stopLoss, ctx.spec.digits),
               " attempt=", attempt);
         return(ticket);
      }

      int err = GetLastError();
      Print("XAU_RPB ORDER_REJECTED error=", err,
            " attempt=", attempt, "/", ctx.ex.maxRetries,
            " spread=", DoubleToString(MarketInfo(ctx.spec.symbol, MODE_SPREAD), 1),
            " lots=", DoubleToString(lots, 2),
            " price=", DoubleToString(price, ctx.spec.digits),
            " sl=", DoubleToString(stopLoss, ctx.spec.digits));
      ResetLastError();

      if(IsTerminalError(err) || !IsTransientError(err))
      {
         // NOTE: we do NOT widen the stop or shrink risk to force acceptance.
         outError = "BROKER_ERROR_" + IntegerToString(err);
         return(-1);
      }
      Sleep(ctx.ex.retryDelayMs);
   }

   outError = "BROKER_RETRIES_EXHAUSTED";
   return(-1);
}

//+------------------------------------------------------------------+
//| Modify an open position's stop. Only ever in the SAFE direction.  |
//+------------------------------------------------------------------+
bool ModifyStop(const ExecutionContext &ctx, const int ticket, const double newStop)
{
   if(ctx.mode == MODE_SHADOW)
      return(true);
   if(!OrderSelect(ticket, SELECT_BY_TICKET))
      return(false);

   double current = OrderStopLoss();
   bool   isLong  = (OrderType() == OP_BUY);

   // A stop never moves against us. This is a hard invariant, not a preference.
   if(current > 0.0)
   {
      if(isLong  && newStop <= current) return(false);
      if(!isLong && newStop >= current) return(false);
   }

   double reference = isLong ? MarketInfo(ctx.spec.symbol, MODE_BID)
                             : MarketInfo(ctx.spec.symbol, MODE_ASK);
   double minDistance = ctx.spec.stopLevelPoints * ctx.spec.point;
   if(minDistance > 0.0 && MathAbs(reference - newStop) < minDistance)
      return(false);

   ResetLastError();
   bool ok = OrderModify(ticket, OrderOpenPrice(),
                         NormalizeDouble(newStop, ctx.spec.digits),
                         OrderTakeProfit(), 0, clrNONE);
   if(!ok)
   {
      int err = GetLastError();
      Print("XAU_RPB MODIFY_FAILED ticket=", ticket, " error=", err,
            " newStop=", DoubleToString(newStop, ctx.spec.digits));
      ResetLastError();
   }
   return(ok);
}

//+------------------------------------------------------------------+
//| Close a position, recording the machine-readable exit reason.     |
//+------------------------------------------------------------------+
bool ClosePosition(const ExecutionContext &ctx, const int ticket, const string exitReason)
{
   if(ctx.mode == MODE_SHADOW)
      return(true);
   if(!OrderSelect(ticket, SELECT_BY_TICKET))
      return(false);

   for(int attempt = 1; attempt <= ctx.ex.maxRetries; attempt++)
   {
      RefreshRates();
      double price = (OrderType() == OP_BUY)
                     ? MarketInfo(ctx.spec.symbol, MODE_BID)
                     : MarketInfo(ctx.spec.symbol, MODE_ASK);
      ResetLastError();
      if(OrderClose(ticket, OrderLots(), NormalizeDouble(price, ctx.spec.digits),
                    ctx.ex.maxSlippagePoints, clrNONE))
      {
         Print("XAU_RPB POSITION_CLOSED ticket=", ticket, " reason=", exitReason,
               " price=", DoubleToString(price, ctx.spec.digits));
         return(true);
      }
      int err = GetLastError();
      Print("XAU_RPB CLOSE_FAILED ticket=", ticket, " error=", err,
            " attempt=", attempt, "/", ctx.ex.maxRetries, " reason=", exitReason);
      ResetLastError();
      if(!IsTransientError(err))
         return(false);
      Sleep(ctx.ex.retryDelayMs);
   }
   return(false);
}

//+------------------------------------------------------------------+
//| Restart reconciliation (spec §13).                                |
//|                                                                   |
//| Identify our own positions by magic number AND comment prefix, so  |
//| a shared magic number cannot make us adopt somebody else's trade.  |
//| Returns the count found and fills the first ticket/direction.      |
//+------------------------------------------------------------------+
int ReconcileOpenPositions(const ExecutionContext &ctx, int &firstTicket, int &firstDirection)
{
   firstTicket    = -1;
   firstDirection = 0;
   int found      = 0;

   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      if(OrderMagicNumber() != ctx.ex.magicNumber)
         continue;
      if(OrderSymbol() != ctx.spec.symbol)
         continue;
      if(StringFind(OrderComment(), XAU_RPB_COMMENT_PREFIX) < 0)
         continue;
      if(OrderType() != OP_BUY && OrderType() != OP_SELL)
         continue;

      found++;
      if(firstTicket < 0)
      {
         firstTicket    = OrderTicket();
         firstDirection = (OrderType() == OP_BUY) ? 1 : -1;
      }
   }
   return(found);
}

#endif // XAU_RPB_EXECUTION_MQH
