//+------------------------------------------------------------------+
//| Regime.mqh - H1 market regime engine (spec §4)                     |
//|                                                                   |
//| Deterministic and interpretable: no ML, no fitted classifier, no   |
//| probability. The classification ORDER is normative - HIGH_VOL      |
//| dominates trend, and INVALID is the catch-all for the band between |
//| adxRangeMax and adxTrendMin.                                       |
//|                                                                   |
//| Every input comes from a CLOSED H1 bar (spec §2).                  |
//|                                                                   |
//| Part of XAU_RPB_V1.0.0.                                            |
//+------------------------------------------------------------------+
#property strict

#ifndef XAU_RPB_REGIME_MQH
#define XAU_RPB_REGIME_MQH

#include "Config.mqh"
#include "Indicators.mqh"

struct RegimeFeatures
{
   MarketRegime regime;
   double       emaFast;
   double       emaSlow;
   double       atrH1;
   double       adx;
   double       er;
   double       atrPct;
   double       normalizedSpread;
   double       normalizedSlope;
   datetime     barTime;
   bool         valid;
};

void ResetRegimeFeatures(RegimeFeatures &f)
{
   f.regime           = REGIME_INVALID;
   f.emaFast          = 0.0;
   f.emaSlow          = 0.0;
   f.atrH1            = 0.0;
   f.adx              = 0.0;
   f.er               = 0.0;
   f.atrPct           = 0.0;
   f.normalizedSpread = 0.0;
   f.normalizedSlope  = 0.0;
   f.barTime          = 0;
   f.valid            = false;
}

//+------------------------------------------------------------------+
//| Pure classification (spec §4.1). First match wins; order matters. |
//+------------------------------------------------------------------+
MarketRegime ClassifyRegime(const double adxValue, const double normalizedSpread,
                            const double normalizedSlope, const double er,
                            const double atrPct, const RpbResearch &p)
{
   if(!IsUsable(adxValue) || !IsUsable(normalizedSpread) || !IsUsable(normalizedSlope) ||
      !IsUsable(er) || !IsUsable(atrPct))
      return(REGIME_INVALID);

   // Risk-off dominates: a violent trend is still a regime we do not trade.
   if(atrPct >= p.atrPctHigh)
      return(REGIME_HIGH_VOLATILITY);

   bool trending = (adxValue >= p.adxTrendMin && er >= p.erTrendMin);
   if(trending)
   {
      if(normalizedSpread >= p.spreadTrendMin && normalizedSlope >= p.slopeTrendMin)
         return(REGIME_TREND_UP);
      if(normalizedSpread <= -p.spreadTrendMin && normalizedSlope <= -p.slopeTrendMin)
         return(REGIME_TREND_DOWN);
   }

   if(adxValue < p.adxRangeMax)
      return(REGIME_RANGE);

   // Transition band, and trending-but-not-aligned: explicitly not tradeable.
   return(REGIME_INVALID);
}

//+------------------------------------------------------------------+
//| Recompute the regime from the last CLOSED H1 bar.                 |
//|                                                                   |
//| Called once per new H1 bar, not per tick (spec §58). The window is |
//| recomputed wholesale rather than updated incrementally: it costs   |
//| about a millisecond an hour and removes a whole class of           |
//| incremental-state bugs that would break parity silently.           |
//+------------------------------------------------------------------+
bool ComputeRegime(const string symbol, const RpbResearch &p, RegimeFeatures &out)
{
   ResetRegimeFeatures(out);

   int warmup = WarmupBarsH1(p);
   int count  = warmup + 8;            // headroom for the slope lookback
   if(iBars(symbol, PERIOD_H1) < count + 2)
   {
      Print("XAU_RPB: insufficient H1 history (need ", count + 2,
            ", have ", iBars(symbol, PERIOD_H1), ") - regime INVALID");
      return(false);
   }

   double openA[], highA[], lowA[], closeA[];
   datetime timeA[];
   if(!CopySeriesChronological(symbol, PERIOD_H1, count, openA, highA, lowA, closeA, timeA))
      return(false);

   double emaFast[], emaSlow[], atrA[], adxA[], erA[], atrPctA[];
   CalcEMA(closeA, p.emaFastPeriod, emaFast);
   CalcEMA(closeA, p.emaSlowPeriod, emaSlow);
   CalcATR(highA, lowA, closeA, p.atrPeriodH1, atrA);
   CalcADX(highA, lowA, closeA, p.adxPeriod, adxA);
   CalcEfficiencyRatio(closeA, p.erWindow, erA);
   CalcATRPercentile(atrA, p.atrPctWindow, atrPctA);

   int last  = count - 1;              // the newest CLOSED bar
   int slopeIdx = last - p.slopeLookback;
   if(slopeIdx < 0)
      return(false);

   double fast     = emaFast[last];
   double slow     = emaSlow[last];
   double fastPrev = emaFast[slopeIdx];
   double atrH1    = atrA[last];
   double adxValue = adxA[last];
   double er       = erA[last];
   double atrPct   = atrPctA[last];

   if(!IsUsable(fast) || !IsUsable(slow) || !IsUsable(fastPrev) || !IsUsable(atrH1) ||
      !IsUsable(adxValue) || !IsUsable(er) || !IsUsable(atrPct) || atrH1 <= 0.0)
      return(false);

   out.emaFast          = fast;
   out.emaSlow          = slow;
   out.atrH1            = atrH1;
   out.adx              = adxValue;
   out.er               = er;
   out.atrPct           = atrPct;
   out.normalizedSpread = (fast - slow) / atrH1;
   out.normalizedSlope  = (fast - fastPrev) / (p.slopeLookback * atrH1);
   out.barTime          = timeA[last];
   out.regime = ClassifyRegime(out.adx, out.normalizedSpread, out.normalizedSlope,
                               out.er, out.atrPct, p);
   out.valid = true;
   return(true);
}

bool RegimeIsTradeable(const MarketRegime regime)
{
   return(regime == REGIME_TREND_UP || regime == REGIME_TREND_DOWN);
}

#endif // XAU_RPB_REGIME_MQH
