//+------------------------------------------------------------------+
//|                                                        XauRpbEA.mq4|
//|         XAUUSD Regime-Filtered Pullback -> Breakout, V1.0.0        |
//|                                                                    |
//| Implements docs/strategy/XAUUSD_RPB_SPEC.md. The CANONICAL         |
//| implementation is research/strategies/xau_rpb/ (Python); this EA   |
//| is its mirror, held to it by tests/parity/. Divergence is a defect.|
//|                                                                    |
//| ARCHITECTURE NOTE (ADR-0027): this is a STANDALONE, autonomous EA. |
//| It is NOT the QuantBridge execution bridge and never speaks the    |
//| ADR-0020 protocol. QuantBridgeEA.mq4 remains execution-only under  |
//| INV-5; this artifact is the bounded, ADR-recorded exception.       |
//|                                                                    |
//| STATUS: RESEARCH / EXPERIMENTAL. No statistical qualification has  |
//| been performed. Defaults to SHADOW mode, which submits no orders.  |
//| Do not connect real capital before the promotion ladder in         |
//| docs/strategy/VALIDATION_METHODOLOGY.md has actually been passed.  |
//+------------------------------------------------------------------+
#property copyright "OpenTrading"
#property link      "https://github.com/opentrading"
#property version   "1.000"
#property strict

#include <xau_rpb/Config.mqh>
#include <xau_rpb/BrokerSpec.mqh>
#include <xau_rpb/Indicators.mqh>
#include <xau_rpb/Regime.mqh>
#include <xau_rpb/SetupMachine.mqh>
#include <xau_rpb/Risk.mqh>
#include <xau_rpb/Sessions.mqh>
#include <xau_rpb/News.mqh>
#include <xau_rpb/Execution.mqh>
#include <xau_rpb/Telemetry.mqh>

//==================== INPUTS: STRUCTURAL (spec §14) ==================
// Changing a STRUCTURAL value is a NEW SPEC VERSION, not a tuning step.
input string  __structural__        = "--- STRUCTURAL (spec version bump if changed) ---";
input bool    InpBreakoutOnClose    = true;    // Confirm breakouts on CLOSED bars only
input int     InpMaxConcurrent      = 1;       // Max concurrent strategy positions

//==================== INPUTS: RESEARCH ===============================
// The ONLY parameters an optimizer may vary. Seeds, not sacred constants.
input string  __research__          = "--- RESEARCH (optimizable) ---";
input int     InpEmaFastPeriod      = 50;
input int     InpEmaSlowPeriod      = 200;
input int     InpAdxPeriod          = 14;
input double  InpAdxTrendMin        = 20.0;
input double  InpAdxRangeMax        = 18.0;
input double  InpSpreadTrendMin     = 0.25;
input double  InpSlopeTrendMin      = 0.03;
input int     InpSlopeLookback      = 3;
input int     InpErWindow           = 20;
input double  InpErTrendMin         = 0.30;
input int     InpAtrPeriodH1        = 14;
input int     InpAtrPeriodM15       = 14;
input int     InpAtrPctWindow       = 500;
input double  InpAtrPctHigh         = 0.95;
input double  InpAtrPctFloor        = 0.10;
input int     InpImpulseLookback    = 6;
input int     InpMinPullbackBars    = 1;
input int     InpMaxPullbackBars    = 4;
input double  InpMinPullbackDepth   = 0.30;
input double  InpMaxPullbackDepth   = 2.00;
input int     InpBreakoutWindowBars = 3;
input double  InpBreakoutBufferAtr  = 0.10;
input int     InpMaxSetupBars       = 12;
input int     InpEntryScoreThresh   = 7;
input double  InpScoreSlopeMin      = 0.03;
input double  InpSlAtrMult          = 2.00;
input double  InpTpRMultiple        = 0.0;     // 0 = no fixed target (variant C)
input double  InpTrailAtrMult       = 2.00;
input double  InpTrailActivateR     = 1.00;
input double  InpBeTriggerR         = 0.0;     // 0 = break-even disabled
input int     InpMaxBarsInTrade     = 48;

//==================== INPUTS: RISK POLICY ============================
// Mandate values. NEVER an optimization target. See spec §7.2.
input string  __risk__              = "--- RISK POLICY (never optimize) ---";
input double  InpRiskPct            = 0.35;    // % equity risked per trade
input double  InpMaxAggregateRisk   = 0.75;
input double  InpDailyLossStopPct   = 1.5;
input double  InpWeeklyLossStopPct  = 3.0;
input double  InpSoftDdPct          = 5.0;
input double  InpHardDdPct          = 9.0;
input double  InpSoftDdRiskMult     = 0.5;

//==================== INPUTS: EXECUTION ==============================
input string  __execution__         = "--- EXECUTION (venue-tuned) ---";
input double  InpSpreadAtrMax       = 0.12;
input double  InpSpreadAbsMaxPoints = 60.0;
input int     InpMaxSlippagePoints  = 20;
input int     InpMaxRetries         = 3;
input int     InpRetryDelayMs       = 250;
input int     InpQuoteMaxAgeSec     = 5;
input int     InpMagicNumber        = 20260831;
input string  InpSymbolAliases      = "XAUUSD,GOLD,XAUUSD.a,XAUUSDm,XAUUSD.m,XAUUSD_i,XAUUSDpro,GOLD.a";

//==================== INPUTS: OPERATIONAL ============================
input string  __operational__       = "--- OPERATIONAL (no signal effect) ---";
input RpbMode InpMode               = MODE_SHADOW;  // SHADOW submits NO orders
input bool    InpSessionExitEnabled = false;
input bool    InpAllowAsianSession  = false;
input bool    InpBlockRollover      = true;
input bool    InpNewsRequired       = false;
input string  InpNewsCsvFile        = "";      // in MQL4/Files; frozen CSV (spec §12)
input int     InpNewsBlockBeforeMin = 30;
input int     InpNewsBlockAfterMin  = 15;
input bool    InpAutoDetectOffset   = true;
input double  InpBrokerUtcOffsetHrs = 2.0;     // used when auto-detect is off
input bool    InpTelemetryEnabled   = true;
input string  InpTelemetryFile      = "xau_rpb_telemetry.csv";
input bool    InpVerboseTransitions = false;

//==================== FORWARD DECLARATIONS ===========================
// MQL4 resolves same-file calls, but explicit prototypes keep the compile
// order-independent and make the module's surface obvious.
double CurrentAtrM15();
void   OnClosedM15Bar(const datetime barTime);
void   EvaluateSignal(const datetime barTime, const double signalClose, const double atrM15);
void   ManageOpenPosition();
void   CheckBarBasedExits(const datetime barTime);
void   ExitPosition(const string reason, const datetime barTime);
void   HandleVanishedPosition();
void   ClearPositionState(const string reason);
void   LogTradeClose(const datetime barTime, const string exitReason,
                     const double pnl, const double realizedR);

//==================== GLOBAL STATE ===================================
RpbResearch     g_research;
RpbRisk         g_risk;
RpbExecution    g_exec;
RpbOperational  g_op;

BrokerSpec      g_spec;
CSetupMachine   g_machine;
CRiskGovernor   g_governor;
CNewsCalendar   g_news;
CTelemetry      g_telemetry;
ExecutionContext g_ctx;

RegimeFeatures  g_regime;
datetime        g_lastH1BarTime  = 0;
datetime        g_lastM15BarTime = 0;
datetime        g_lastSignalBar  = 0;
double          g_brokerOffset   = 0.0;

int             g_ticket         = -1;
double          g_entryPrice     = 0.0;
double          g_initialStop    = 0.0;
double          g_currentStop    = 0.0;
double          g_targetPrice    = 0.0;
double          g_atrAtSignal    = 0.0;
double          g_positionExtreme= 0.0;
int             g_positionDir    = 0;
int             g_barsInTrade    = 0;
bool            g_beApplied      = false;
bool            g_trailActive    = false;
bool            g_initOk         = false;

//+------------------------------------------------------------------+
//| Assemble the parameter structs from the inputs.                  |
//+------------------------------------------------------------------+
void LoadParameters()
{
   g_research.emaFastPeriod       = InpEmaFastPeriod;
   g_research.emaSlowPeriod       = InpEmaSlowPeriod;
   g_research.adxPeriod           = InpAdxPeriod;
   g_research.adxTrendMin         = InpAdxTrendMin;
   g_research.adxRangeMax         = InpAdxRangeMax;
   g_research.spreadTrendMin      = InpSpreadTrendMin;
   g_research.slopeTrendMin       = InpSlopeTrendMin;
   g_research.slopeLookback       = InpSlopeLookback;
   g_research.erWindow            = InpErWindow;
   g_research.erTrendMin          = InpErTrendMin;
   g_research.atrPeriodH1         = InpAtrPeriodH1;
   g_research.atrPeriodM15        = InpAtrPeriodM15;
   g_research.atrPctWindow        = InpAtrPctWindow;
   g_research.atrPctHigh          = InpAtrPctHigh;
   g_research.atrPctFloor         = InpAtrPctFloor;
   g_research.impulseLookback     = InpImpulseLookback;
   g_research.minPullbackBars     = InpMinPullbackBars;
   g_research.maxPullbackBars     = InpMaxPullbackBars;
   g_research.minPullbackDepthAtr = InpMinPullbackDepth;
   g_research.maxPullbackDepthAtr = InpMaxPullbackDepth;
   g_research.breakoutWindowBars  = InpBreakoutWindowBars;
   g_research.breakoutBufferAtr   = InpBreakoutBufferAtr;
   g_research.maxSetupBars        = InpMaxSetupBars;
   g_research.entryScoreThreshold = InpEntryScoreThresh;
   g_research.scoreSlopeMin       = InpScoreSlopeMin;
   g_research.slAtrMult           = InpSlAtrMult;
   g_research.tpRMultiple         = InpTpRMultiple;
   g_research.trailAtrMult        = InpTrailAtrMult;
   g_research.trailActivateR      = InpTrailActivateR;
   g_research.beTriggerR          = InpBeTriggerR;
   g_research.maxBarsInTrade      = InpMaxBarsInTrade;

   g_risk.riskPct                 = InpRiskPct;
   g_risk.maxAggregateRiskPct     = InpMaxAggregateRisk;
   g_risk.dailyLossStopPct        = InpDailyLossStopPct;
   g_risk.weeklyLossStopPct       = InpWeeklyLossStopPct;
   g_risk.softDdPct               = InpSoftDdPct;
   g_risk.hardDdPct               = InpHardDdPct;
   g_risk.softDdRiskMultiplier    = InpSoftDdRiskMult;
   g_risk.maxConcurrentPositions  = InpMaxConcurrent;

   g_exec.spreadAtrMax            = InpSpreadAtrMax;
   g_exec.spreadAbsMaxPoints      = InpSpreadAbsMaxPoints;
   g_exec.maxSlippagePoints       = InpMaxSlippagePoints;
   g_exec.maxRetries              = InpMaxRetries;
   g_exec.retryDelayMs            = InpRetryDelayMs;
   g_exec.quoteMaxAgeSec          = InpQuoteMaxAgeSec;
   g_exec.magicNumber             = InpMagicNumber;
   g_exec.symbolAliases           = InpSymbolAliases;

   g_op.mode                      = InpMode;
   g_op.sessionExitEnabled        = InpSessionExitEnabled;
   g_op.newsRequired              = InpNewsRequired;
   g_op.newsCsvPath               = InpNewsCsvFile;
   g_op.newsBlockBeforeMin        = InpNewsBlockBeforeMin;
   g_op.newsBlockAfterMin         = InpNewsBlockAfterMin;
   g_op.brokerUtcOffsetHours      = InpBrokerUtcOffsetHrs;
   g_op.autoDetectOffset          = InpAutoDetectOffset;
   g_op.allowAsianSession         = InpAllowAsianSession;
   g_op.blockRollover             = InpBlockRollover;
   g_op.telemetryEnabled          = InpTelemetryEnabled;
   g_op.telemetryFile             = InpTelemetryFile;
}

//+------------------------------------------------------------------+
//| A short, stable id for the active configuration (spec §16, §51).  |
//+------------------------------------------------------------------+
string BuildConfigId()
{
   double acc = 0.0;
   acc += g_research.emaFastPeriod * 1.7   + g_research.emaSlowPeriod * 2.3;
   acc += g_research.adxPeriod * 3.1       + g_research.adxTrendMin * 5.9;
   acc += g_research.adxRangeMax * 7.3     + g_research.spreadTrendMin * 11.7;
   acc += g_research.slopeTrendMin * 13.1  + g_research.slopeLookback * 17.3;
   acc += g_research.erWindow * 19.7       + g_research.erTrendMin * 23.9;
   acc += g_research.atrPeriodH1 * 29.3    + g_research.atrPeriodM15 * 31.1;
   acc += g_research.atrPctWindow * 37.7   + g_research.atrPctHigh * 41.3;
   acc += g_research.atrPctFloor * 43.9    + g_research.impulseLookback * 47.1;
   acc += g_research.minPullbackBars * 53.3+ g_research.maxPullbackBars * 59.7;
   acc += g_research.minPullbackDepthAtr*61.1 + g_research.maxPullbackDepthAtr*67.3;
   acc += g_research.breakoutWindowBars*71.9  + g_research.breakoutBufferAtr*73.1;
   acc += g_research.maxSetupBars * 79.3   + g_research.entryScoreThreshold * 83.7;
   acc += g_research.scoreSlopeMin * 89.1  + g_research.slAtrMult * 97.3;
   acc += g_research.tpRMultiple * 101.9   + g_research.trailAtrMult * 103.1;
   acc += g_research.trailActivateR*107.7  + g_research.beTriggerR * 109.3;
   acc += g_research.maxBarsInTrade*113.1  + g_risk.riskPct * 127.9;
   return(StringFormat("cfg%08X", (int)MathRound(MathAbs(acc) * 1000.0)));
}

//+------------------------------------------------------------------+
int OnInit()
{
   LoadParameters();

   string problem = "";
   if(!ValidateResearch(g_research, problem) || !ValidateRisk(g_risk, problem))
   {
      Print("XAU_RPB FAIL-CLOSED: invalid configuration - ", problem);
      return(INIT_PARAMETERS_INCORRECT);
   }
   if(!InpBreakoutOnClose)
   {
      Print("XAU_RPB FAIL-CLOSED: intrabar breakout confirmation is not a production "
            "definition in V1 (spec §5.4). Refusing to start.");
      return(INIT_PARAMETERS_INCORRECT);
   }

   if(!ResolveSymbol(g_exec.symbolAliases, g_spec))
      return(INIT_FAILED);

   g_brokerOffset = g_op.autoDetectOffset ? DetectBrokerUtcOffsetHours()
                                          : g_op.brokerUtcOffsetHours;
   if(IsTesting() && g_op.autoDetectOffset)
   {
      // In the Strategy Tester TimeGMT() tracks the simulated server clock, so a
      // detected offset there is meaningless. Fall back to the explicit value and
      // say so, rather than silently backtesting a different session rule.
      g_brokerOffset = g_op.brokerUtcOffsetHours;
      Print("XAU_RPB: Strategy Tester detected - using the EXPLICIT broker UTC offset ",
            DoubleToString(g_brokerOffset, 2),
            "h (TimeGMT tracks simulated server time in the tester)");
   }
   Print("XAU_RPB: broker UTC offset = ", DoubleToString(g_brokerOffset, 2), "h");

   g_news.Init(g_op.newsBlockBeforeMin, g_op.newsBlockAfterMin, g_op.newsRequired);
   if(StringLen(g_op.newsCsvPath) > 0)
      g_news.LoadFromCsv(g_op.newsCsvPath, "USD");
   else if(g_op.newsRequired)
      g_news.MarkFailed("news filter required but no file configured");

   g_machine.Init(g_research, InpVerboseTransitions);
   g_governor.Init(g_risk, AccountEquity(), TimeCurrent());
   g_telemetry.Init(g_op.telemetryFile, g_op.telemetryEnabled, BuildConfigId());

   g_ctx.spec = g_spec;
   g_ctx.ex   = g_exec;
   g_ctx.mode = g_op.mode;

   // Spec §13 restart recovery: never duplicate an existing entry.
   int firstTicket = -1, firstDir = 0;
   int open = ReconcileOpenPositions(g_ctx, firstTicket, firstDir);
   if(open > g_risk.maxConcurrentPositions)
   {
      g_governor.EnterSafeMode(StringFormat(
         "%d strategy positions found on restart, limit is %d",
         open, g_risk.maxConcurrentPositions));
   }
   if(open >= 1 && OrderSelect(firstTicket, SELECT_BY_TICKET))
   {
      g_ticket          = firstTicket;
      g_positionDir     = firstDir;
      g_entryPrice      = OrderOpenPrice();
      g_initialStop     = OrderStopLoss();
      g_currentStop     = OrderStopLoss();
      g_targetPrice     = OrderTakeProfit();
      g_positionExtreme = OrderOpenPrice();
      g_barsInTrade     = 0;
      // The signal-time ATR is not recoverable from the broker, so re-derive it
      // from current volatility and say so: trailing resumes on a fresh reading
      // rather than on a fabricated one.
      g_atrAtSignal     = CurrentAtrM15();
      g_machine.AdoptRecoveredPosition(firstDir);
      Print("XAU_RPB: recovered position ticket=", g_ticket,
            " dir=", (firstDir > 0 ? "LONG" : "SHORT"),
            " entry=", DoubleToString(g_entryPrice, g_spec.digits),
            " stop=", DoubleToString(g_currentStop, g_spec.digits),
            " - resuming management, no new entry");
   }

   Print("XAU_RPB ", XAU_RPB_SPEC_VERSION, " initialized. mode=",
         (g_op.mode == MODE_SHADOW ? "SHADOW (no orders will be sent)" : "LIVE"),
         " symbol=", g_spec.symbol, " magic=", g_exec.magicNumber,
         " config=", g_telemetry.ConfigId(),
         " | STATUS: RESEARCH/EXPERIMENTAL - not statistically qualified");

   g_initOk = true;
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   Print("XAU_RPB deinit, reason=", reason,
         " state=", StateName(g_machine.State()), " ticket=", g_ticket);
}

//+------------------------------------------------------------------+
//| Current M15 ATR from CLOSED bars, per the spec's definition.     |
//+------------------------------------------------------------------+
double CurrentAtrM15()
{
   int count = g_research.atrPeriodM15 * 4 + 8;
   double o[], h[], l[], c[];
   datetime t[];
   if(!CopySeriesChronological(g_spec.symbol, PERIOD_M15, count, o, h, l, c, t))
      return(XAU_RPB_NAN);
   double atrA[];
   CalcATR(h, l, c, g_research.atrPeriodM15, atrA);
   return(atrA[ArraySize(atrA) - 1]);
}

//+------------------------------------------------------------------+
//| Signal score, spec §6. Maximum 9.                                 |
//+------------------------------------------------------------------+
int ComputeScore(const int direction, const double depthAtr, const bool sessionOk,
                 const double spreadPoints, const double atrM15, int &parts[])
{
   ArrayResize(parts, 7);
   MarketRegime expected = (direction > 0) ? REGIME_TREND_UP : REGIME_TREND_DOWN;

   parts[0] = (g_regime.regime == expected) ? 2 : 0;
   parts[1] = (MathAbs(g_regime.normalizedSlope) >= g_research.scoreSlopeMin) ? 1 : 0;
   parts[2] = (depthAtr >= g_research.minPullbackDepthAtr &&
               depthAtr <= g_research.maxPullbackDepthAtr) ? 1 : 0;
   parts[3] = 2;   // reaching SIGNAL_READY means the breakout was close-confirmed
   parts[4] = (g_regime.atrPct >= g_research.atrPctFloor &&
               g_regime.atrPct <  g_research.atrPctHigh) ? 1 : 0;
   parts[5] = sessionOk ? 1 : 0;

   // Relative AND absolute: a fixed number alone is insufficient, and a purely
   // relative test lets a volatility spike justify an arbitrarily wide spread.
   double spreadPrice = spreadPoints * g_spec.point;
   parts[6] = (spreadPrice <= g_exec.spreadAtrMax * atrM15 &&
               spreadPoints <= g_exec.spreadAbsMaxPoints) ? 1 : 0;

   int total = 0;
   for(int i = 0; i < 7; i++)
      total += parts[i];
   return(total);
}

string PartsToCsv(const int &parts[])
{
   string out = "";
   for(int i = 0; i < ArraySize(parts); i++)
      out += (i == 0 ? "" : ",") + IntegerToString(parts[i]);
   return(out);
}

//+------------------------------------------------------------------+
//| OnTick - event classes are separated (spec §27).                 |
//+------------------------------------------------------------------+
void OnTick()
{
   if(!g_initOk)
      return;

   g_governor.Observe(TimeCurrent(), AccountEquity());

   // 1) Per-tick: manage an open position (stops are broker-side; this handles
   //    trailing, break-even and the non-price exits).
   if(g_ticket >= 0)
      ManageOpenPosition();

   // 2) New CLOSED H1 bar -> refresh the regime.
   datetime h1Time = iTime(g_spec.symbol, PERIOD_H1, 1);
   if(h1Time != g_lastH1BarTime)
   {
      g_lastH1BarTime = h1Time;
      if(!ComputeRegime(g_spec.symbol, g_research, g_regime))
         ResetRegimeFeatures(g_regime);   // fail closed to INVALID
   }

   // 3) New CLOSED M15 bar -> advance the setup machine.
   //    Ordering is normative: the H1 regime is applied BEFORE the M15 logic.
   datetime m15Time = iTime(g_spec.symbol, PERIOD_M15, 1);
   if(m15Time != g_lastM15BarTime)
   {
      g_lastM15BarTime = m15Time;
      OnClosedM15Bar(m15Time);
   }
}

//+------------------------------------------------------------------+
void OnClosedM15Bar(const datetime barTime)
{
   if(g_ticket >= 0)
   {
      g_barsInTrade++;
      CheckBarBasedExits(barTime);
      return;                       // one position at a time (spec §7.2)
   }

   int count = MathMax(WarmupBarsM15(g_research), g_research.atrPeriodM15 * 4) + 16;
   double o[], h[], l[], c[];
   datetime t[];
   if(!CopySeriesChronological(g_spec.symbol, PERIOD_M15, count, o, h, l, c, t))
      return;

   double atrA[];
   CalcATR(h, l, c, g_research.atrPeriodM15, atrA);
   int idx = ArraySize(c) - 1;
   double atrM15 = atrA[idx];

   bool ready = g_machine.OnClosedBar(o, h, l, c, idx, g_regime.regime, atrM15);
   if(!ready)
      return;

   if(barTime == g_lastSignalBar)
   {
      g_machine.OnSignalDiscarded(RPB_REJ_DUPLICATE);
      return;
   }

   EvaluateSignal(barTime, c[idx], atrM15);
}

//+------------------------------------------------------------------+
//| SIGNAL_READY -> score, guards, sizing, submission (spec §5.5, §9).|
//+------------------------------------------------------------------+
void EvaluateSignal(const datetime barTime, const double signalClose, const double atrM15)
{
   int    direction    = g_machine.Direction();
   double spreadPoints = MarketInfo(g_spec.symbol, MODE_SPREAD);
   bool   sessionOk    = IsSessionPermitted(barTime, g_brokerOffset,
                                            g_op.allowAsianSession, g_op.blockRollover);
   datetime utcNow     = BrokerToUtc(barTime, g_brokerOffset);

   int parts[];
   int score = ComputeScore(direction, g_machine.DepthAtr(), sessionOk,
                            spreadPoints, atrM15, parts);

   //--- Guards, severity-ordered so telemetry names the most serious block.
   string reject = RPB_REJ_NONE;
   if(!IsUsable(atrM15) || atrM15 <= 0.0)          reject = RPB_REJ_ATR;
   else if(StringLen(g_governor.EntryBlockReason()) > 0)
                                                   reject = g_governor.EntryBlockReason();
   else if(g_news.IsBlackout(utcNow))              reject = RPB_REJ_NEWS;
   else if(!sessionOk)                             reject = RPB_REJ_SESSION;
   else if(parts[6] == 0)                          reject = RPB_REJ_SPREAD;
   else if(score < g_research.entryScoreThreshold) reject = RPB_REJ_SCORE;

   double stopPrice = (direction > 0)
                      ? signalClose - g_research.slAtrMult * atrM15
                      : signalClose + g_research.slAtrMult * atrM15;

   SizingResult sizing;
   sizing.lots = 0.0; sizing.riskMoney = 0.0; sizing.riskPerLot = 0.0;
   sizing.stopDistance = 0.0; sizing.actualRisk = 0.0; sizing.rejectReason = RPB_REJ_NONE;

   if(StringLen(reject) == 0)
   {
      sizing = CalculateLots(AccountEquity(), g_governor.EffectiveRiskPct(),
                             signalClose, stopPrice, g_spec);
      if(sizing.lots <= 0.0)
         reject = sizing.rejectReason;
   }

   if(StringLen(reject) > 0)
   {
      LogDecision(barTime, utcNow, "SIGNAL_REJECTED", direction, atrM15, score, parts,
                  spreadPoints, signalClose, stopPrice, 0.0, sizing, -1, reject, "", "");
      g_machine.OnSignalDiscarded(reject);
      return;
   }

   double target = 0.0;
   if(g_research.tpRMultiple > 0.0)
   {
      double r = MathAbs(signalClose - stopPrice);
      target = (direction > 0) ? signalClose + g_research.tpRMultiple * r
                               : signalClose - g_research.tpRMultiple * r;
   }

   g_machine.OnOrderSubmitted();
   g_lastSignalBar = barTime;

   string brokerError = "";
   int orderType = (direction > 0) ? OP_BUY : OP_SELL;
   int ticket = SendMarketOrder(g_ctx, orderType, sizing.lots, stopPrice, target, brokerError);

   if(ticket < 0)
   {
      // SHADOW mode reaches here by design: the decision is logged, nothing is sent.
      string event = (g_op.mode == MODE_SHADOW) ? "SHADOW_SIGNAL" : "ORDER_FAILED";
      LogDecision(barTime, utcNow, event, direction, atrM15, score, parts, spreadPoints,
                  signalClose, stopPrice, target, sizing, -1,
                  (g_op.mode == MODE_SHADOW ? "" : brokerError), "", brokerError);
      g_machine.OnRejected(g_op.mode == MODE_SHADOW ? "SHADOW" : brokerError);
      return;
   }

   if(OrderSelect(ticket, SELECT_BY_TICKET))
   {
      g_ticket          = ticket;
      g_positionDir     = direction;
      g_entryPrice      = OrderOpenPrice();
      g_initialStop     = stopPrice;
      g_currentStop     = stopPrice;
      g_targetPrice     = target;
      g_atrAtSignal     = atrM15;      // FROZEN for the life of the trade (spec §8)
      g_positionExtreme = OrderOpenPrice();
      g_barsInTrade     = 0;
      g_beApplied       = false;
      g_trailActive     = false;
      g_machine.OnFilled();

      LogDecision(barTime, utcNow, "POSITION_OPENED", direction, atrM15, score, parts,
                  spreadPoints, g_entryPrice, stopPrice, target, sizing, ticket, "", "", "");
   }
}

//+------------------------------------------------------------------+
//| Per-tick management: break-even and ATR trailing (spec §8).       |
//+------------------------------------------------------------------+
void ManageOpenPosition()
{
   if(!OrderSelect(g_ticket, SELECT_BY_TICKET))
   {
      HandleVanishedPosition();
      return;
   }
   if(OrderCloseTime() != 0)
   {
      HandleVanishedPosition();
      return;
   }

   bool   isLong = (g_positionDir > 0);
   double price  = isLong ? MarketInfo(g_spec.symbol, MODE_BID)
                          : MarketInfo(g_spec.symbol, MODE_ASK);
   if(price <= 0.0)
      return;

   if(isLong) g_positionExtreme = MathMax(g_positionExtreme, price);
   else       g_positionExtreme = MathMin(g_positionExtreme, price);

   double rDistance = MathAbs(g_entryPrice - g_initialStop);
   if(rDistance <= 0.0)
      return;
   double rNow = (isLong ? (price - g_entryPrice) : (g_entryPrice - price)) / rDistance;

   // Break-even, once, and only when it improves the stop.
   if(g_research.beTriggerR > 0.0 && !g_beApplied && rNow >= g_research.beTriggerR)
   {
      if(ModifyStop(g_ctx, g_ticket, g_entryPrice))
      {
         g_currentStop = g_entryPrice;
         g_beApplied   = true;
         Print("XAU_RPB BREAK_EVEN ticket=", g_ticket,
               " stop=", DoubleToString(g_entryPrice, g_spec.digits));
      }
   }

   // ATR trailing from the extreme reached since entry.
   if(rNow >= g_research.trailActivateR && g_atrAtSignal > 0.0)
   {
      double offset    = g_research.trailAtrMult * g_atrAtSignal;
      double candidate = isLong ? (g_positionExtreme - offset)
                                : (g_positionExtreme + offset);
      bool improves = isLong ? (candidate > g_currentStop) : (candidate < g_currentStop);
      if(improves && ModifyStop(g_ctx, g_ticket, candidate))
      {
         g_currentStop = candidate;
         g_trailActive = true;
      }
   }
}

//+------------------------------------------------------------------+
//| Bar-close exits: regime invalidation, time, session (spec §8).   |
//+------------------------------------------------------------------+
void CheckBarBasedExits(const datetime barTime)
{
   if(g_ticket < 0)
      return;

   // Only the OPPOSITE trend forces an exit. RANGE / HIGH_VOL / INVALID merely
   // block new entries (spec §8).
   MarketRegime opposite = (g_positionDir > 0) ? REGIME_TREND_DOWN : REGIME_TREND_UP;
   if(g_regime.regime == opposite)
   {
      ExitPosition("REGIME_INVALIDATION", barTime);
      return;
   }
   if(g_barsInTrade >= g_research.maxBarsInTrade)
   {
      ExitPosition("TIME_EXIT", barTime);
      return;
   }
   if(g_op.sessionExitEnabled &&
      !IsSessionPermitted(barTime, g_brokerOffset, g_op.allowAsianSession, g_op.blockRollover))
   {
      ExitPosition("SESSION_EXIT", barTime);
   }
}

//+------------------------------------------------------------------+
void ExitPosition(const string reason, const datetime barTime)
{
   if(ClosePosition(g_ctx, g_ticket, reason))
   {
      double pnl = 0.0, realizedR = 0.0;
      if(OrderSelect(g_ticket, SELECT_BY_TICKET))
      {
         pnl = OrderProfit() + OrderSwap() + OrderCommission();
         double rDistance = MathAbs(g_entryPrice - g_initialStop);
         if(rDistance > 0.0)
         {
            double move = (g_positionDir > 0)
                          ? (OrderClosePrice() - g_entryPrice)
                          : (g_entryPrice - OrderClosePrice());
            realizedR = move / rDistance;
         }
      }
      LogTradeClose(barTime, reason, pnl, realizedR);
      ClearPositionState(reason);
   }
}

//+------------------------------------------------------------------+
//| The position is gone (stop, target, or a manual/broker close).    |
//+------------------------------------------------------------------+
void HandleVanishedPosition()
{
   string reason = "STOP_LOSS";
   double pnl = 0.0, realizedR = 0.0;

   if(OrderSelect(g_ticket, SELECT_BY_TICKET, MODE_HISTORY))
   {
      pnl = OrderProfit() + OrderSwap() + OrderCommission();
      double closePrice = OrderClosePrice();
      double rDistance  = MathAbs(g_entryPrice - g_initialStop);
      if(rDistance > 0.0)
      {
         double move = (g_positionDir > 0) ? (closePrice - g_entryPrice)
                                           : (g_entryPrice - closePrice);
         realizedR = move / rDistance;
      }
      // Distinguish the stop family from a target fill using the recorded levels,
      // not by guessing from the price path afterwards (spec §8.1).
      if(g_targetPrice > 0.0 && MathAbs(closePrice - g_targetPrice) <= g_spec.point * 5)
         reason = "TARGET";
      else if(g_trailActive)
         reason = "ATR_TRAIL";
      else if(MathAbs(closePrice - g_initialStop) <= g_spec.point * 5)
         reason = "STOP_LOSS";
      else
         reason = "MANUAL";
   }
   else
   {
      reason = "BROKER_ERROR_RECOVERY";
   }

   LogTradeClose(TimeCurrent(), reason, pnl, realizedR);
   ClearPositionState(reason);
}

//+------------------------------------------------------------------+
void ClearPositionState(const string reason)
{
   g_machine.OnPositionClosed(reason);
   g_ticket          = -1;
   g_positionDir     = 0;
   g_entryPrice      = 0.0;
   g_initialStop     = 0.0;
   g_currentStop     = 0.0;
   g_targetPrice     = 0.0;
   g_atrAtSignal     = 0.0;
   g_positionExtreme = 0.0;
   g_barsInTrade     = 0;
   g_beApplied       = false;
   g_trailActive     = false;
}

//+------------------------------------------------------------------+
//| Telemetry helpers.                                                |
//+------------------------------------------------------------------+
void LogDecision(const datetime barTime, const datetime utcTime, const string event,
                 const int direction, const double atrM15, const int score,
                 const int &parts[], const double spreadPoints, const double entry,
                 const double stop, const double target, const SizingResult &sizing,
                 const int ticket, const string rejectReason, const string exitReason,
                 const string brokerError)
{
   if(!g_op.telemetryEnabled)
      return;
   SessionFlags f = ResolveSession(barTime, g_brokerOffset);
   double expectedR = (g_research.tpRMultiple > 0.0) ? g_research.tpRMultiple : 0.0;

   string row = g_telemetry.BuildRow(
      barTime, utcTime, g_spec.symbol, event, StateName(g_machine.State()),
      RegimeName(g_regime.regime),
      g_regime.emaFast, g_regime.emaSlow, g_regime.adx, g_regime.er,
      g_regime.atrH1, atrM15, g_regime.normalizedSpread, g_regime.normalizedSlope,
      g_regime.atrPct,
      (direction > 0 ? "LONG" : (direction < 0 ? "SHORT" : "")),
      g_machine.DepthAtr(), g_machine.BreakoutReference(),
      score, PartsToCsv(parts), f.label, spreadPoints,
      entry, stop, target, sizing.lots, g_governor.EffectiveRiskPct(), sizing.riskMoney,
      expectedR, ticket, rejectReason, exitReason, 0.0, 0.0, 0.0, 0.0, 0,
      AccountEquity(), brokerError);
   g_telemetry.Write(row);
}

void LogTradeClose(const datetime barTime, const string exitReason,
                   const double pnl, const double realizedR)
{
   if(!g_op.telemetryEnabled)
      return;
   int parts[];
   ArrayResize(parts, 7);
   for(int i = 0; i < 7; i++)
      parts[i] = 0;

   SizingResult empty;
   empty.lots = 0.0; empty.riskMoney = 0.0; empty.riskPerLot = 0.0;
   empty.stopDistance = 0.0; empty.actualRisk = 0.0; empty.rejectReason = "";

   SessionFlags f = ResolveSession(barTime, g_brokerOffset);
   string row = g_telemetry.BuildRow(
      barTime, BrokerToUtc(barTime, g_brokerOffset), g_spec.symbol, "POSITION_CLOSED",
      StateName(g_machine.State()), RegimeName(g_regime.regime),
      g_regime.emaFast, g_regime.emaSlow, g_regime.adx, g_regime.er,
      g_regime.atrH1, g_atrAtSignal, g_regime.normalizedSpread, g_regime.normalizedSlope,
      g_regime.atrPct, (g_positionDir > 0 ? "LONG" : "SHORT"),
      0.0, 0.0, 0, PartsToCsv(parts), f.label,
      MarketInfo(g_spec.symbol, MODE_SPREAD),
      g_entryPrice, g_currentStop, g_targetPrice, 0.0,
      g_governor.EffectiveRiskPct(), 0.0, 0.0, g_ticket, "", exitReason,
      pnl, realizedR, 0.0, 0.0, g_barsInTrade, AccountEquity(), "");
   g_telemetry.Write(row);
}
//+------------------------------------------------------------------+
