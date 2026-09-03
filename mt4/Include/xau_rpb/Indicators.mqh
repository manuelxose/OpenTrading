//+------------------------------------------------------------------+
//| Indicators.mqh - spec §3.1 indicators, implemented natively        |
//|                                                                   |
//| These are deliberately NOT iMA/iATR/iADX. The built-ins differ in  |
//| seeding (MT4's EMA does not seed with an SMA) and MetaQuotes may   |
//| change internals between builds. Implementing the spec directly is |
//| what makes the signal-parity tests against the Python reference    |
//| exact rather than approximate.                                     |
//|                                                                   |
//| Convention: every array here is CHRONOLOGICAL (index 0 = oldest),  |
//| matching the Python reference. MT4's own series are the reverse,   |
//| so CopySeriesChronological() flips them once at the boundary.      |
//|                                                                   |
//| Part of XAU_RPB_V1.0.0.                                            |
//+------------------------------------------------------------------+
#property strict

#ifndef XAU_RPB_INDICATORS_MQH
#define XAU_RPB_INDICATORS_MQH

#define XAU_RPB_NAN (EMPTY_VALUE)

//+------------------------------------------------------------------+
//| True for a usable number. EMPTY_VALUE marks "not yet defined".    |
//+------------------------------------------------------------------+
bool IsUsable(const double v)
{
   return(v != XAU_RPB_NAN && MathAbs(v) < 1.0e300);
}

//+------------------------------------------------------------------+
//| Copy `count` closed bars of a timeframe into chronological arrays.|
//| Shift 1 is the last CLOSED bar; shift 0 (forming) is never read.  |
//+------------------------------------------------------------------+
bool CopySeriesChronological(const string symbol, const int timeframe, const int count,
                             double &openA[], double &highA[], double &lowA[],
                             double &closeA[], datetime &timeA[])
{
   if(count <= 0)
      return(false);
   if(iBars(symbol, timeframe) < count + 2)
      return(false);

   ArrayResize(openA,  count);
   ArrayResize(highA,  count);
   ArrayResize(lowA,   count);
   ArrayResize(closeA, count);
   ArrayResize(timeA,  count);

   for(int i = 0; i < count; i++)
   {
      // shift 1 = newest CLOSED bar -> chronological index count-1
      int shift = count - i;   // i=count-1 -> shift 1
      openA[i]  = iOpen (symbol, timeframe, shift);
      highA[i]  = iHigh (symbol, timeframe, shift);
      lowA[i]   = iLow  (symbol, timeframe, shift);
      closeA[i] = iClose(symbol, timeframe, shift);
      timeA[i]  = iTime (symbol, timeframe, shift);
      if(openA[i] <= 0.0 || highA[i] < lowA[i])
         return(false);
   }
   return(true);
}

//+------------------------------------------------------------------+
//| EMA, alpha = 2/(n+1), seeded with the SMA of the first n values.  |
//+------------------------------------------------------------------+
void CalcEMA(const double &values[], const int period, double &out[])
{
   int n = ArraySize(values);
   ArrayResize(out, n);
   for(int i = 0; i < n; i++)
      out[i] = XAU_RPB_NAN;
   if(period < 1 || n < period)
      return;

   double sum = 0.0;
   for(int i = 0; i < period; i++)
      sum += values[i];

   double alpha = 2.0 / (period + 1.0);
   double prev  = sum / period;
   out[period - 1] = prev;

   for(int i = period; i < n; i++)
   {
      prev   = values[i] * alpha + prev * (1.0 - alpha);
      out[i] = prev;
   }
}

//+------------------------------------------------------------------+
//| True Range. Index 0 is undefined (needs the previous close).      |
//+------------------------------------------------------------------+
void CalcTrueRange(const double &highA[], const double &lowA[], const double &closeA[],
                   double &out[])
{
   int n = ArraySize(closeA);
   ArrayResize(out, n);
   if(n > 0)
      out[0] = XAU_RPB_NAN;
   for(int i = 1; i < n; i++)
   {
      double prevClose = closeA[i - 1];
      double a = highA[i] - lowA[i];
      double b = MathAbs(highA[i] - prevClose);
      double c = MathAbs(lowA[i]  - prevClose);
      out[i] = MathMax(a, MathMax(b, c));
   }
}

//+------------------------------------------------------------------+
//| Wilder smoothing seeded with the SMA of `period` values from      |
//| `start`, so a leading undefined value is never consumed.          |
//+------------------------------------------------------------------+
void CalcWilderRMA(const double &values[], const int period, const int start, double &out[])
{
   int n = ArraySize(values);
   ArrayResize(out, n);
   for(int i = 0; i < n; i++)
      out[i] = XAU_RPB_NAN;
   if(period < 1 || start < 0)
      return;

   int seedEnd = start + period;      // exclusive
   if(n < seedEnd)
      return;

   double sum = 0.0;
   for(int i = start; i < seedEnd; i++)
      sum += values[i];

   double prev = sum / period;
   out[seedEnd - 1] = prev;

   for(int i = seedEnd; i < n; i++)
   {
      prev   = (prev * (period - 1) + values[i]) / period;
      out[i] = prev;
   }
}

//+------------------------------------------------------------------+
//| ATR (Wilder). First defined value sits at index `period`.         |
//+------------------------------------------------------------------+
void CalcATR(const double &highA[], const double &lowA[], const double &closeA[],
             const int period, double &out[])
{
   double tr[];
   CalcTrueRange(highA, lowA, closeA, tr);
   CalcWilderRMA(tr, period, 1, out);
}

//+------------------------------------------------------------------+
//| ADX (Wilder). First defined value sits at index 2*period - 1.     |
//+------------------------------------------------------------------+
void CalcADX(const double &highA[], const double &lowA[], const double &closeA[],
             const int period, double &out[])
{
   int n = ArraySize(closeA);
   ArrayResize(out, n);
   for(int i = 0; i < n; i++)
      out[i] = XAU_RPB_NAN;
   if(n < 2 || period < 1)
      return;

   double plusDM[], minusDM[], tr[];
   ArrayResize(plusDM, n);
   ArrayResize(minusDM, n);
   plusDM[0]  = XAU_RPB_NAN;
   minusDM[0] = XAU_RPB_NAN;

   for(int i = 1; i < n; i++)
   {
      double up   = highA[i] - highA[i - 1];
      double down = lowA[i - 1] - lowA[i];
      plusDM[i]  = (up > down   && up > 0.0)   ? up   : 0.0;
      minusDM[i] = (down > up   && down > 0.0) ? down : 0.0;
   }

   CalcTrueRange(highA, lowA, closeA, tr);

   double smPlus[], smMinus[], smTR[];
   CalcWilderRMA(plusDM,  period, 1, smPlus);
   CalcWilderRMA(minusDM, period, 1, smMinus);
   CalcWilderRMA(tr,      period, 1, smTR);

   double dx[];
   ArrayResize(dx, n);
   int firstDx = -1;
   for(int i = 0; i < n; i++)
   {
      dx[i] = XAU_RPB_NAN;
      if(!IsUsable(smTR[i]) || smTR[i] <= 0.0)
         continue;
      double plusDi  = 100.0 * smPlus[i]  / smTR[i];
      double minusDi = 100.0 * smMinus[i] / smTR[i];
      double denom   = plusDi + minusDi;
      dx[i] = (denom == 0.0) ? 0.0 : 100.0 * MathAbs(plusDi - minusDi) / denom;
      if(firstDx < 0)
         firstDx = i;
   }
   if(firstDx < 0)
      return;

   CalcWilderRMA(dx, period, firstDx, out);
}

//+------------------------------------------------------------------+
//| Kaufman Efficiency Ratio over `window`.                           |
//+------------------------------------------------------------------+
void CalcEfficiencyRatio(const double &closeA[], const int window, double &out[])
{
   int n = ArraySize(closeA);
   ArrayResize(out, n);
   for(int i = 0; i < n; i++)
      out[i] = XAU_RPB_NAN;
   if(window < 1)
      return;

   for(int i = window; i < n; i++)
   {
      double net  = MathAbs(closeA[i] - closeA[i - window]);
      double path = 0.0;
      for(int j = i - window + 1; j <= i; j++)
         path += MathAbs(closeA[j] - closeA[j - 1]);
      out[i] = (path == 0.0) ? 0.0 : net / path;
   }
}

//+------------------------------------------------------------------+
//| ATR percentile: fraction of the trailing window STRICTLY below    |
//| the current value. Ties count as "not below" (spec §3.1).         |
//+------------------------------------------------------------------+
void CalcATRPercentile(const double &atrA[], const int window, double &out[])
{
   int n = ArraySize(atrA);
   ArrayResize(out, n);
   for(int i = 0; i < n; i++)
      out[i] = XAU_RPB_NAN;
   if(window < 1)
      return;

   for(int i = 0; i < n; i++)
   {
      double current = atrA[i];
      if(!IsUsable(current))
         continue;
      int lo = i - window + 1;
      if(lo < 0)
         continue;

      bool complete = true;
      int  below    = 0;
      for(int j = lo; j <= i; j++)
      {
         if(!IsUsable(atrA[j]))
         {
            complete = false;
            break;
         }
         if(atrA[j] < current)
            below++;
      }
      if(complete)
         out[i] = below / (double)window;
   }
}

#endif // XAU_RPB_INDICATORS_MQH
