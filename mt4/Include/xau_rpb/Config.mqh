//+------------------------------------------------------------------+
//| Config.mqh - parameter structs, split by the categories of spec §14|
//|                                                                   |
//| The split is not cosmetic. Keeping RISK POLICY in its own struct   |
//| is what stops a future optimizer sweep from quietly treating the   |
//| risk mandate as an alpha variable.                                 |
//|                                                                   |
//| Part of XAU_RPB_V1.0.0.                                            |
//+------------------------------------------------------------------+
#property strict

#ifndef XAU_RPB_CONFIG_MQH
#define XAU_RPB_CONFIG_MQH

#define XAU_RPB_SPEC_VERSION "XAU_RPB_V1.0.0"
#define XAU_RPB_COMMENT_PREFIX "XAU_RPB_V1"

//--- Market regime (spec §4.1)
enum MarketRegime
{
   REGIME_INVALID = 0,
   REGIME_TREND_UP,
   REGIME_TREND_DOWN,
   REGIME_RANGE,
   REGIME_HIGH_VOLATILITY
};

//--- Setup state machine (spec §5)
enum SetupState
{
   STATE_SCANNING = 0,
   STATE_ARMED,
   STATE_PULLBACK_ACTIVE,
   STATE_BREAKOUT_WINDOW,
   STATE_SIGNAL_READY,
   STATE_ORDER_SUBMITTED,
   STATE_IN_POSITION
};

//--- Operating mode (INV-8 ladder; SHADOW submits no orders at all)
enum RpbMode
{
   MODE_SHADOW = 0,
   MODE_LIVE
};

//--- Spec §14 RESEARCH: the ONLY parameters an optimizer may vary.
struct RpbResearch
{
   int    emaFastPeriod;
   int    emaSlowPeriod;
   int    adxPeriod;
   double adxTrendMin;
   double adxRangeMax;
   double spreadTrendMin;
   double slopeTrendMin;
   int    slopeLookback;
   int    erWindow;
   double erTrendMin;
   int    atrPeriodH1;
   int    atrPeriodM15;
   int    atrPctWindow;
   double atrPctHigh;
   double atrPctFloor;

   int    impulseLookback;
   int    minPullbackBars;
   int    maxPullbackBars;
   double minPullbackDepthAtr;
   double maxPullbackDepthAtr;
   int    breakoutWindowBars;
   double breakoutBufferAtr;
   int    maxSetupBars;

   int    entryScoreThreshold;
   double scoreSlopeMin;

   double slAtrMult;
   double tpRMultiple;
   double trailAtrMult;
   double trailActivateR;
   double beTriggerR;
   int    maxBarsInTrade;
};

//--- Spec §14 RISK POLICY: mandate values. NEVER an optimization target.
struct RpbRisk
{
   double riskPct;
   double maxAggregateRiskPct;
   double dailyLossStopPct;
   double weeklyLossStopPct;
   double softDdPct;
   double hardDdPct;
   double softDdRiskMultiplier;
   int    maxConcurrentPositions;
};

//--- Spec §14 EXECUTION: venue-dependent, tuned to the broker, never to the P&L.
struct RpbExecution
{
   double spreadAtrMax;
   double spreadAbsMaxPoints;
   int    maxSlippagePoints;
   int    maxRetries;
   int    retryDelayMs;
   int    quoteMaxAgeSec;
   int    magicNumber;
   string symbolAliases;
};

//--- Spec §14 OPERATIONAL: no effect on signal generation.
struct RpbOperational
{
   RpbMode mode;
   bool    sessionExitEnabled;
   bool    newsRequired;
   string  newsCsvPath;
   int     newsBlockBeforeMin;
   int     newsBlockAfterMin;
   double  brokerUtcOffsetHours;
   bool    autoDetectOffset;
   bool    allowAsianSession;
   bool    blockRollover;
   bool    telemetryEnabled;
   string  telemetryFile;
};

//+------------------------------------------------------------------+
//| Reject an internally contradictory parameter set BEFORE trading.  |
//+------------------------------------------------------------------+
bool ValidateResearch(const RpbResearch &r, string &problem)
{
   if(r.emaFastPeriod >= r.emaSlowPeriod)
   { problem = "emaFastPeriod must be < emaSlowPeriod"; return(false); }
   if(r.adxRangeMax > r.adxTrendMin)
   { problem = "adxRangeMax must be <= adxTrendMin"; return(false); }
   if(r.minPullbackBars > r.maxPullbackBars)
   { problem = "minPullbackBars must be <= maxPullbackBars"; return(false); }
   if(r.minPullbackDepthAtr >= r.maxPullbackDepthAtr)
   { problem = "minPullbackDepthAtr must be < maxPullbackDepthAtr"; return(false); }
   if(r.atrPctFloor >= r.atrPctHigh)
   { problem = "atrPctFloor must be < atrPctHigh"; return(false); }
   if(r.entryScoreThreshold < 0 || r.entryScoreThreshold > 9)
   { problem = "entryScoreThreshold must be within 0..9"; return(false); }
   if(r.slAtrMult <= 0.0)
   { problem = "slAtrMult must be > 0"; return(false); }
   if(r.emaFastPeriod < 1 || r.emaSlowPeriod < 1 || r.adxPeriod < 1 ||
      r.erWindow < 1 || r.atrPeriodH1 < 1 || r.atrPeriodM15 < 1 ||
      r.atrPctWindow < 1 || r.impulseLookback < 1 || r.slopeLookback < 1 ||
      r.breakoutWindowBars < 1)
   { problem = "every period/window parameter must be >= 1"; return(false); }
   return(true);
}

bool ValidateRisk(const RpbRisk &k, string &problem)
{
   if(k.riskPct <= 0.0 || k.riskPct > 2.0)
   { problem = "riskPct outside the 0-2% mandate band"; return(false); }
   if(k.softDdPct >= k.hardDdPct)
   { problem = "softDdPct must be < hardDdPct"; return(false); }
   if(k.dailyLossStopPct >= k.weeklyLossStopPct)
   { problem = "dailyLossStopPct must be < weeklyLossStopPct"; return(false); }
   if(k.maxConcurrentPositions < 1)
   { problem = "maxConcurrentPositions must be >= 1"; return(false); }
   return(true);
}

//+------------------------------------------------------------------+
//| Closed H1 bars required before the regime engine may emit a state.|
//+------------------------------------------------------------------+
int WarmupBarsH1(const RpbResearch &r)
{
   int need = r.emaSlowPeriod + 1;
   need = MathMax(need, r.emaFastPeriod + r.slopeLookback + 1);
   need = MathMax(need, r.adxPeriod * 2 + 1);
   need = MathMax(need, r.erWindow + 1);
   need = MathMax(need, r.atrPeriodH1 + 1);
   need = MathMax(need, r.atrPctWindow);
   return(need);
}

int WarmupBarsM15(const RpbResearch &r)
{
   return(MathMax(r.atrPeriodM15 + 1, r.impulseLookback + 2));
}

string RegimeName(const MarketRegime regime)
{
   switch(regime)
   {
      case REGIME_TREND_UP:        return("REGIME_TREND_UP");
      case REGIME_TREND_DOWN:      return("REGIME_TREND_DOWN");
      case REGIME_RANGE:           return("REGIME_RANGE");
      case REGIME_HIGH_VOLATILITY: return("REGIME_HIGH_VOLATILITY");
      default:                     return("REGIME_INVALID");
   }
}

string StateName(const SetupState state)
{
   switch(state)
   {
      case STATE_ARMED:            return("ARMED");
      case STATE_PULLBACK_ACTIVE:  return("PULLBACK_ACTIVE");
      case STATE_BREAKOUT_WINDOW:  return("BREAKOUT_WINDOW");
      case STATE_SIGNAL_READY:     return("SIGNAL_READY");
      case STATE_ORDER_SUBMITTED:  return("ORDER_SUBMITTED");
      case STATE_IN_POSITION:      return("IN_POSITION");
      default:                     return("SCANNING");
   }
}

#endif // XAU_RPB_CONFIG_MQH
