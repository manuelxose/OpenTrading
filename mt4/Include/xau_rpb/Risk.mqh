//+------------------------------------------------------------------+
//| Risk.mqh - broker-aware sizing and kill switches (spec §7)         |
//|                                                                   |
//| Two rules carry the whole safety argument:                         |
//|   1. ALWAYS round DOWN to the broker lot step.                     |
//|   2. NEVER round up to reach the broker minimum - if the minimum   |
//|      lot implies more risk than the mandate allows, DO NOT TRADE.  |
//|                                                                   |
//| Risk is computed independently of signal generation. Martingale,   |
//| averaging down, grid recovery and post-loss multipliers are not    |
//| merely disabled here - they are unrepresentable, because size is   |
//| always an OUTPUT of the stop distance.                             |
//|                                                                   |
//| Part of XAU_RPB_V1.0.0.                                            |
//+------------------------------------------------------------------+
#property strict

#ifndef XAU_RPB_RISK_MQH
#define XAU_RPB_RISK_MQH

#include "Config.mqh"
#include "BrokerSpec.mqh"

//--- Reject reasons (spec §5.5 / §9), mirrored from the Python RejectReason enum.
#define RPB_REJ_NONE               ""
#define RPB_REJ_SCORE              "SCORE_BELOW_THRESHOLD"
#define RPB_REJ_SIZE_ZERO          "RISK_SIZE_ZERO"
#define RPB_REJ_SPREAD             "SPREAD_TOO_WIDE"
#define RPB_REJ_SESSION            "SESSION_BLOCKED"
#define RPB_REJ_NEWS               "NEWS_BLACKOUT"
#define RPB_REJ_DAILY              "DAILY_LOSS_STOP"
#define RPB_REJ_WEEKLY             "WEEKLY_LOSS_STOP"
#define RPB_REJ_HARD_DD            "HARD_DRAWDOWN_KILL"
#define RPB_REJ_POSITION_OPEN      "POSITION_ALREADY_OPEN"
#define RPB_REJ_SPEC_INVALID       "BROKER_SPEC_INVALID"
#define RPB_REJ_STOP_LEVEL         "STOP_LEVEL_VIOLATION"
#define RPB_REJ_MARGIN             "INSUFFICIENT_MARGIN"
#define RPB_REJ_HISTORY            "INSUFFICIENT_HISTORY"
#define RPB_REJ_ATR                "ATR_INVALID"
#define RPB_REJ_DUPLICATE          "DUPLICATE_SIGNAL"
#define RPB_REJ_SAFE_MODE          "SAFE_MODE"
#define RPB_REJ_TRADE_DISABLED     "TRADING_DISABLED"
#define RPB_REJ_QUOTE_STALE        "QUOTE_STALE"

struct SizingResult
{
   double lots;
   double riskMoney;
   double riskPerLot;
   double stopDistance;
   double actualRisk;
   string rejectReason;
};

//+------------------------------------------------------------------+
//| Round DOWN to a multiple of `step`.                               |
//|                                                                   |
//| The relative epsilon compensates float representation only: a true |
//| 1.0 can arrive as 0.999999999 after division, and flooring that    |
//| would silently discard a whole lot step. It is never a rounding-up |
//| rule - the caller still re-checks realized risk against the budget.|
//+------------------------------------------------------------------+
double FloorToStep(const double value, const double step)
{
   if(step <= 0.0 || value <= 0.0)
      return(0.0);
   double ratio  = value / step;
   double nudged = MathFloor(ratio + 1.0e-9 * MathMax(1.0, MathAbs(ratio)));
   return(NormalizeDouble(nudged * step, 8));
}

//+------------------------------------------------------------------+
//| Derive lot size from equity, risk budget and the ACTUAL stop.     |
//+------------------------------------------------------------------+
SizingResult CalculateLots(const double equity, const double riskPct,
                           const double entryPrice, const double stopPrice,
                           const BrokerSpec &s)
{
   SizingResult r;
   r.lots         = 0.0;
   r.riskMoney    = 0.0;
   r.riskPerLot   = 0.0;
   r.stopDistance = 0.0;
   r.actualRisk   = 0.0;
   r.rejectReason = RPB_REJ_SIZE_ZERO;

   if(!s.valid)
   { r.rejectReason = RPB_REJ_SPEC_INVALID; return(r); }
   if(equity <= 0.0 || riskPct <= 0.0)
      return(r);

   r.stopDistance = MathAbs(entryPrice - stopPrice);
   if(r.stopDistance <= 0.0)
      return(r);

   // MODE_TICKSIZE is a PRICE increment, not a count of points. Multiplying it
   // by Point understates size by 1/Point (100x on a 2-digit gold feed).
   double tickSizePrice = s.tickSize;
   if(tickSizePrice <= 0.0)
   { r.rejectReason = RPB_REJ_SPEC_INVALID; return(r); }

   r.riskMoney  = equity * riskPct / 100.0;
   double ticks = r.stopDistance / tickSizePrice;
   r.riskPerLot = ticks * s.tickValue;
   if(r.riskPerLot <= 0.0)
   { r.rejectReason = RPB_REJ_SPEC_INVALID; return(r); }

   double lots = FloorToStep(r.riskMoney / r.riskPerLot, s.lotStep);

   if(lots > s.maxLot)
      lots = FloorToStep(s.maxLot, s.lotStep);

   // The mandate rule: below the minimum we do NOT trade. We never round up.
   if(lots < s.minLot)
      return(r);

   double actual = lots * r.riskPerLot;
   if(actual > r.riskMoney * (1.0 + 1.0e-9))
      return(r);   // flooring cannot increase risk; a hit here means a broken spec

   r.lots         = NormalizeDouble(lots, LotDigits(s.lotStep));
   r.actualRisk   = actual;
   r.rejectReason = RPB_REJ_NONE;
   return(r);
}

//+------------------------------------------------------------------+
//| Account-level kill switches (spec §7.2).                          |
//|                                                                   |
//| A breached daily/weekly stop blocks NEW ENTRIES only; open         |
//| positions keep being managed and stops are never widened. The hard |
//| drawdown kill latches and needs an operator reset. Nothing here    |
//| liquidates: forced liquidation turns a drawdown into a realized    |
//| loss at the worst possible moment.                                 |
//+------------------------------------------------------------------+
class CRiskGovernor
{
private:
   RpbRisk  m_p;
   double   m_dayStartEquity;
   double   m_weekStartEquity;
   double   m_peakEquity;
   int      m_currentDay;
   int      m_currentWeek;
   bool     m_hardKill;
   bool     m_softDd;
   bool     m_dailyHit;
   bool     m_weeklyHit;
   bool     m_safeMode;
   string   m_safeModeReason;

   int WeekKey(const datetime t) const
   {
      // Weeks are keyed off a fixed epoch Monday so the boundary is stable and
      // does not depend on the terminal's locale.
      return((int)MathFloor((double)(t + 259200) / 604800.0));
   }

public:
   void Init(const RpbRisk &p, const double equity, const datetime now)
   {
      m_p               = p;
      m_dayStartEquity  = equity;
      m_weekStartEquity = equity;
      m_peakEquity      = equity;
      m_currentDay      = (int)MathFloor((double)now / 86400.0);
      m_currentWeek     = WeekKey(now);
      m_hardKill        = false;
      m_softDd          = false;
      m_dailyHit        = false;
      m_weeklyHit       = false;
      m_safeMode        = false;
      m_safeModeReason  = "";
   }

   bool   SafeMode()      const { return(m_safeMode); }
   bool   HardKill()      const { return(m_hardKill); }
   bool   SoftDd()        const { return(m_softDd); }
   double PeakEquity()    const { return(m_peakEquity); }

   void EnterSafeMode(const string reason)
   {
      m_safeMode       = true;
      m_safeModeReason = reason;
      Print("XAU_RPB SAFE_MODE engaged: ", reason);
   }

   //--- Deliberate manual intervention only - never automatic (spec §7.2).
   void ResetHardKill(const string operatorName)
   {
      if(StringLen(operatorName) == 0)
      {
         Print("XAU_RPB: hard-kill reset refused - an operator identity is required");
         return;
      }
      m_hardKill = false;
      Print("XAU_RPB: hard-kill reset by ", operatorName);
   }

   //--- Roll period boundaries and update the high-water mark.
   void Observe(const datetime now, const double equity)
   {
      int day  = (int)MathFloor((double)now / 86400.0);
      int week = WeekKey(now);

      if(day != m_currentDay)
      {
         m_currentDay     = day;
         m_dayStartEquity = equity;
         m_dailyHit       = false;
      }
      if(week != m_currentWeek)
      {
         m_currentWeek     = week;
         m_weekStartEquity = equity;
         m_weeklyHit       = false;
      }
      if(equity > m_peakEquity)
         m_peakEquity = equity;

      if(m_dayStartEquity > 0.0)
      {
         double dailyDd = (m_dayStartEquity - equity) / m_dayStartEquity * 100.0;
         if(dailyDd >= m_p.dailyLossStopPct)
            m_dailyHit = true;
      }
      if(m_weekStartEquity > 0.0)
      {
         double weeklyDd = (m_weekStartEquity - equity) / m_weekStartEquity * 100.0;
         if(weeklyDd >= m_p.weeklyLossStopPct)
            m_weeklyHit = true;
      }
      if(m_peakEquity > 0.0)
      {
         double equityDd = (m_peakEquity - equity) / m_peakEquity * 100.0;
         m_softDd = (equityDd >= m_p.softDdPct);
         if(equityDd >= m_p.hardDdPct)
         {
            if(!m_hardKill)
               Print("XAU_RPB HARD DRAWDOWN KILL at ", DoubleToString(equityDd, 2),
                     "% from peak ", DoubleToString(m_peakEquity, 2),
                     " - new entries blocked until an operator resets");
            m_hardKill = true;   // latching
         }
      }
   }

   //--- Most severe active block, or "" when entries are permitted.
   string EntryBlockReason() const
   {
      if(m_safeMode)  return(RPB_REJ_SAFE_MODE);
      if(m_hardKill)  return(RPB_REJ_HARD_DD);
      if(m_weeklyHit) return(RPB_REJ_WEEKLY);
      if(m_dailyHit)  return(RPB_REJ_DAILY);
      return(RPB_REJ_NONE);
   }

   bool AllowsNewEntry() const
   {
      return(StringLen(EntryBlockReason()) == 0);
   }

   //--- Risk budget after the soft-drawdown de-risking step.
   double EffectiveRiskPct() const
   {
      if(m_softDd)
         return(m_p.riskPct * m_p.softDdRiskMultiplier);
      return(m_p.riskPct);
   }
};

#endif // XAU_RPB_RISK_MQH
