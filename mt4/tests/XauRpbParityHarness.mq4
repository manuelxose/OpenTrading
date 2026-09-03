//+------------------------------------------------------------------+
//|                                           XauRpbParityHarness.mq4  |
//|                                                                    |
//| SIGNAL-PARITY HARNESS (mandate §46). Not a trading program.        |
//|                                                                    |
//| Reads a fixture CSV produced by research.strategies.xau_rpb.parity,|
//| drives the SAME regime engine and setup state machine the EA uses, |
//| and writes a `<name>.actual` file. tests/parity/ then compares it  |
//| against the Python reference's `<name>.golden.json` field by field.|
//|                                                                    |
//| HOW TO RUN                                                         |
//|   1. Copy mt4/Include/xau_rpb/ -> <terminal>/MQL4/Include/xau_rpb/ |
//|   2. Copy this file            -> <terminal>/MQL4/Scripts/          |
//|   3. Copy data/fixtures/xau_rpb/*.csv -> <terminal>/MQL4/Files/     |
//|   4. Compile and run once per scenario (set InpScenario).          |
//|   5. Copy <terminal>/MQL4/Files/*.actual back to                   |
//|      data/fixtures/xau_rpb/ and run: pytest tests/parity           |
//|                                                                    |
//| The harness never calls OrderSend and never touches an account.    |
//+------------------------------------------------------------------+
#property copyright "OpenTrading"
#property version   "1.000"
#property strict
#property script_show_inputs

#include <xau_rpb/Config.mqh>
#include <xau_rpb/Indicators.mqh>
#include <xau_rpb/Regime.mqh>
#include <xau_rpb/SetupMachine.mqh>

input string InpScenario   = "trend_up";   // fixture base name in MQL4/Files
input int    InpMaxBars    = 8000;

#define MAX_FIXTURE_BARS 20000

double   g_open[MAX_FIXTURE_BARS];
double   g_high[MAX_FIXTURE_BARS];
double   g_low[MAX_FIXTURE_BARS];
double   g_close[MAX_FIXTURE_BARS];
double   g_spread[MAX_FIXTURE_BARS];
datetime g_time[MAX_FIXTURE_BARS];
int      g_count = 0;

//+------------------------------------------------------------------+
//| Load the fixture CSV (chronological, oldest first).               |
//+------------------------------------------------------------------+
bool LoadFixture(const string filename)
{
   int handle = FileOpen(filename, FILE_READ | FILE_CSV | FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
   {
      Print("PARITY: cannot open ", filename, " error=", GetLastError());
      return(false);
   }

   // Skip the header row.
   while(!FileIsLineEnding(handle) && !FileIsEnding(handle))
      FileReadString(handle);

   g_count = 0;
   while(!FileIsEnding(handle) && g_count < MAX_FIXTURE_BARS && g_count < InpMaxBars)
   {
      string rawTime = FileReadString(handle);
      if(StringLen(rawTime) == 0)
         break;
      double o = StringToDouble(FileReadString(handle));
      double h = StringToDouble(FileReadString(handle));
      double l = StringToDouble(FileReadString(handle));
      double c = StringToDouble(FileReadString(handle));
      FileReadString(handle);                       // volume, unused here
      double sp = StringToDouble(FileReadString(handle));
      while(!FileIsLineEnding(handle) && !FileIsEnding(handle))
         FileReadString(handle);

      g_time[g_count]   = StrToTime(rawTime);
      g_open[g_count]   = o;
      g_high[g_count]   = h;
      g_low[g_count]    = l;
      g_close[g_count]  = c;
      g_spread[g_count] = sp;
      g_count++;
   }
   FileClose(handle);
   Print("PARITY: loaded ", g_count, " bars from ", filename);
   return(g_count > 0);
}

//+------------------------------------------------------------------+
//| Aggregate M15 -> H1, keeping only fully-formed hours.             |
//+------------------------------------------------------------------+
int AggregateH1(double &ho[], double &hh[], double &hl[], double &hc[], datetime &ht[])
{
   ArrayResize(ho, g_count); ArrayResize(hh, g_count);
   ArrayResize(hl, g_count); ArrayResize(hc, g_count);
   ArrayResize(ht, g_count);

   int written = 0;
   int i = 0;
   while(i < g_count)
   {
      datetime hourStart = (datetime)(g_time[i] - (g_time[i] % 3600));
      int j = i;
      double hi = g_high[i], lo = g_low[i];
      int members = 0;
      while(j < g_count && (datetime)(g_time[j] - (g_time[j] % 3600)) == hourStart)
      {
         if(g_high[j] > hi) hi = g_high[j];
         if(g_low[j]  < lo) lo = g_low[j];
         members++;
         j++;
      }
      if(members >= 4)      // only complete hours feed a regime decision
      {
         ho[written] = g_open[i];
         hh[written] = hi;
         hl[written] = lo;
         hc[written] = g_close[j - 1];
         ht[written] = hourStart;
         written++;
      }
      i = j;
   }
   ArrayResize(ho, written); ArrayResize(hh, written);
   ArrayResize(hl, written); ArrayResize(hc, written);
   ArrayResize(ht, written);
   return(written);
}

//+------------------------------------------------------------------+
//| Index of the last H1 bar that had CLOSED before `m15Time`.        |
//+------------------------------------------------------------------+
int H1IndexFor(const datetime m15Time, const datetime &ht[], const int n)
{
   int lo = 0, hi = n - 1, result = -1;
   while(lo <= hi)
   {
      int mid = (lo + hi) / 2;
      if((datetime)(ht[mid] + 3600) <= m15Time) { result = mid; lo = mid + 1; }
      else                                      { hi = mid - 1; }
   }
   return(result);
}

//+------------------------------------------------------------------+
void OnStart()
{
   RpbResearch p;
   // Defaults must match research.strategies.xau_rpb.config.ResearchParams.
   p.emaFastPeriod = 50;    p.emaSlowPeriod = 200;   p.adxPeriod = 14;
   p.adxTrendMin = 20.0;    p.adxRangeMax = 18.0;    p.spreadTrendMin = 0.25;
   p.slopeTrendMin = 0.03;  p.slopeLookback = 3;     p.erWindow = 20;
   p.erTrendMin = 0.30;     p.atrPeriodH1 = 14;      p.atrPeriodM15 = 14;
   p.atrPctWindow = 500;    p.atrPctHigh = 0.95;     p.atrPctFloor = 0.10;
   p.impulseLookback = 6;   p.minPullbackBars = 1;   p.maxPullbackBars = 4;
   p.minPullbackDepthAtr = 0.30; p.maxPullbackDepthAtr = 2.00;
   p.breakoutWindowBars = 3;     p.breakoutBufferAtr = 0.10;
   p.maxSetupBars = 12;     p.entryScoreThreshold = 7; p.scoreSlopeMin = 0.03;
   p.slAtrMult = 2.00;      p.tpRMultiple = 0.0;     p.trailAtrMult = 2.00;
   p.trailActivateR = 1.00; p.beTriggerR = 0.0;      p.maxBarsInTrade = 48;

   if(!LoadFixture(InpScenario + ".csv"))
      return;

   double ho[], hh[], hl[], hc[];
   datetime ht[];
   int h1Count = AggregateH1(ho, hh, hl, hc, ht);
   Print("PARITY: aggregated ", h1Count, " H1 bars");

   // Pre-compute the H1 feature series over the whole fixture.
   double emaFast[], emaSlow[], atrH1[], adxH1[], erH1[], atrPctH1[];
   CalcEMA(hc, p.emaFastPeriod, emaFast);
   CalcEMA(hc, p.emaSlowPeriod, emaSlow);
   CalcATR(hh, hl, hc, p.atrPeriodH1, atrH1);
   CalcADX(hh, hl, hc, p.adxPeriod, adxH1);
   CalcEfficiencyRatio(hc, p.erWindow, erH1);
   CalcATRPercentile(atrH1, p.atrPctWindow, atrPctH1);

   // M15 ATR over the whole fixture.
   double m15o[], m15h[], m15l[], m15c[], atrM15[];
   ArrayResize(m15o, g_count); ArrayResize(m15h, g_count);
   ArrayResize(m15l, g_count); ArrayResize(m15c, g_count);
   for(int k = 0; k < g_count; k++)
   {
      m15o[k] = g_open[k]; m15h[k] = g_high[k];
      m15l[k] = g_low[k];  m15c[k] = g_close[k];
   }
   CalcATR(m15h, m15l, m15c, p.atrPeriodM15, atrM15);

   CSetupMachine machine;
   machine.Init(p, false);

   int out = FileOpen(InpScenario + ".actual", FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(out == INVALID_HANDLE)
   {
      Print("PARITY: cannot write output, error=", GetLastError());
      return;
   }
   FileWrite(out, "index", "bar_time", "regime", "state", "direction",
                  "depth_atr", "breakout_reference", "atr_m15", "signal");

   int signals = 0;
   for(int i = 0; i < g_count; i++)
   {
      int h1Idx = H1IndexFor(g_time[i], ht, h1Count);

      MarketRegime regime = REGIME_INVALID;
      if(h1Idx >= 0)
      {
         int slopeIdx = h1Idx - p.slopeLookback;
         if(slopeIdx >= 0)
         {
            double fast = emaFast[h1Idx], slow = emaSlow[h1Idx];
            double fastPrev = emaFast[slopeIdx], atrv = atrH1[h1Idx];
            double adxv = adxH1[h1Idx], erv = erH1[h1Idx], pctv = atrPctH1[h1Idx];
            if(IsUsable(fast) && IsUsable(slow) && IsUsable(fastPrev) && IsUsable(atrv) &&
               IsUsable(adxv) && IsUsable(erv) && IsUsable(pctv) && atrv > 0.0)
            {
               double normSpread = (fast - slow) / atrv;
               double normSlope  = (fast - fastPrev) / (p.slopeLookback * atrv);
               regime = ClassifyRegime(adxv, normSpread, normSlope, erv, pctv, p);
            }
         }
      }

      double atrValue = atrM15[i];
      bool signal = machine.OnClosedBar(m15o, m15h, m15l, m15c, i, regime, atrValue);
      if(signal)
      {
         signals++;
         machine.OnSignalDiscarded("PARITY_HARNESS_CONSUMED");
      }

      int dir = machine.Direction();
      string dirName = (dir > 0) ? "LONG" : ((dir < 0) ? "SHORT" : "");
      double depth = machine.DepthAtr();
      if(!IsUsable(depth)) depth = 0.0;
      double atrOut = IsUsable(atrValue) ? atrValue : 0.0;

      FileWrite(out, i,
                TimeToString(g_time[i], TIME_DATE | TIME_MINUTES),
                RegimeName(regime),
                StateName(machine.State()),
                dirName,
                DoubleToString(depth, 6),
                DoubleToString(machine.BreakoutReference(), 6),
                DoubleToString(atrOut, 6),
                (signal ? 1 : 0));
   }
   FileClose(out);

   Print("PARITY: wrote ", g_count, " rows to ", InpScenario, ".actual (",
         signals, " signals). Copy it back to data/fixtures/xau_rpb/ and run pytest.");
}
//+------------------------------------------------------------------+
