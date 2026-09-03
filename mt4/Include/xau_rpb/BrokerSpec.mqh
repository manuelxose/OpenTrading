//+------------------------------------------------------------------+
//| BrokerSpec.mqh - instrument specification layer (spec §10)        |
//|                                                                   |
//| Nothing about the instrument may be hardcoded. Every value below   |
//| is read from the server, and a specification that fails validation |
//| means NO TRADE (spec §15) - never a fallback default.              |
//|                                                                   |
//| Part of XAU_RPB_V1.0.0. See docs/strategy/XAUUSD_RPB_SPEC.md.      |
//+------------------------------------------------------------------+
#property strict

#ifndef XAU_RPB_BROKERSPEC_MQH
#define XAU_RPB_BROKERSPEC_MQH

struct BrokerSpec
{
   string symbol;
   double point;
   int    digits;
   double tickValue;      // account currency per tickSize move, per 1.00 lot
   double tickSize;       // MINIMAL PRICE INCREMENT - a price, not a point count
   double lotSize;        // contract size
   double minLot;
   double maxLot;
   double lotStep;
   int    stopLevelPoints;
   int    freezeLevelPoints;
   double swapLong;
   double swapShort;
   int    profitCalcMode;
   int    marginCalcMode;
   bool   valid;
};

//+------------------------------------------------------------------+
//| Load and validate the server-reported specification.              |
//|                                                                   |
//| NOTE on tickSize: MODE_TICKSIZE is the minimal PRICE change (0.01  |
//| on a 2-digit XAUUSD). It is NOT a count of points. Multiplying it  |
//| by Point - as several published gold EAs do - understates position |
//| size by a factor of 1/Point, i.e. 100x on a 2-digit feed.          |
//+------------------------------------------------------------------+
bool LoadBrokerSpec(const string symbol, BrokerSpec &s)
{
   s.symbol            = symbol;
   s.point             = MarketInfo(symbol, MODE_POINT);
   s.digits            = (int)MarketInfo(symbol, MODE_DIGITS);
   s.tickValue         = MarketInfo(symbol, MODE_TICKVALUE);
   s.tickSize          = MarketInfo(symbol, MODE_TICKSIZE);
   s.lotSize           = MarketInfo(symbol, MODE_LOTSIZE);
   s.minLot            = MarketInfo(symbol, MODE_MINLOT);
   s.maxLot            = MarketInfo(symbol, MODE_MAXLOT);
   s.lotStep           = MarketInfo(symbol, MODE_LOTSTEP);
   s.stopLevelPoints   = (int)MarketInfo(symbol, MODE_STOPLEVEL);
   s.freezeLevelPoints = (int)MarketInfo(symbol, MODE_FREEZELEVEL);
   s.swapLong          = MarketInfo(symbol, MODE_SWAPLONG);
   s.swapShort         = MarketInfo(symbol, MODE_SWAPSHORT);
   s.profitCalcMode    = (int)MarketInfo(symbol, MODE_PROFITCALCMODE);
   s.marginCalcMode    = (int)MarketInfo(symbol, MODE_MARGINCALCMODE);

   s.valid = (s.point     > 0.0 &&
              s.tickValue > 0.0 &&
              s.tickSize  > 0.0 &&
              s.minLot    > 0.0 &&
              s.lotStep   > 0.0 &&
              s.maxLot    >= s.minLot);

   if(!s.valid)
   {
      Print("XAU_RPB FAIL-CLOSED: invalid broker specification for ", symbol,
            " point=", s.point, " tickValue=", s.tickValue, " tickSize=", s.tickSize,
            " minLot=", s.minLot, " lotStep=", s.lotStep, " maxLot=", s.maxLot);
   }
   return(s.valid);
}

//+------------------------------------------------------------------+
//| Resolve the traded symbol from a configurable alias list.         |
//|                                                                   |
//| The literal name "XAUUSD" is never assumed: brokers ship GOLD,     |
//| XAUUSD.a, XAUUSDm and others. The first alias that both exists and |
//| returns a VALID specification wins. If none does, we do not trade. |
//+------------------------------------------------------------------+
bool ResolveSymbol(const string aliasCsv, BrokerSpec &s)
{
   string aliases[];
   ushort separator = StringGetCharacter(",", 0);
   int count = StringSplit(aliasCsv, separator, aliases);
   if(count <= 0)
   {
      Print("XAU_RPB FAIL-CLOSED: empty symbol alias list");
      return(false);
   }

   for(int i = 0; i < count; i++)
   {
      string candidate = aliases[i];
      StringTrimLeft(candidate);
      StringTrimRight(candidate);
      if(StringLen(candidate) == 0)
         continue;

      // MarketInfo returns 0 for an unknown symbol; a valid spec proves existence.
      if(MarketInfo(candidate, MODE_POINT) <= 0.0)
         continue;
      if(LoadBrokerSpec(candidate, s))
      {
         Print("XAU_RPB: resolved symbol '", candidate, "' digits=", s.digits,
               " point=", s.point, " tickSize=", s.tickSize,
               " tickValue=", s.tickValue, " minLot=", s.minLot,
               " lotStep=", s.lotStep, " stopLevel=", s.stopLevelPoints);
         return(true);
      }
   }

   Print("XAU_RPB FAIL-CLOSED: no symbol in '", aliasCsv, "' resolved to a valid spec");
   return(false);
}

//+------------------------------------------------------------------+
//| Decimal places implied by a lot step, for NormalizeDouble.        |
//+------------------------------------------------------------------+
int LotDigits(const double step)
{
   if(step >= 1.0)    return(0);
   if(step >= 0.1)    return(1);
   if(step >= 0.01)   return(2);
   if(step >= 0.001)  return(3);
   return(4);
}

#endif // XAU_RPB_BROKERSPEC_MQH
