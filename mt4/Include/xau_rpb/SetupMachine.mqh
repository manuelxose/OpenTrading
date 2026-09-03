//+------------------------------------------------------------------+
//| SetupMachine.mqh - M15 pullback -> breakout state machine (spec §5)|
//|                                                                   |
//| A line-for-line mirror of research/strategies/xau_rpb/            |
//| state_machine.py. Transition order is normative: for each state    |
//| the conditions are evaluated in the listed order and the first     |
//| match fires. Divergence from the Python reference is a DEFECT and  |
//| is caught by tests/parity/.                                        |
//|                                                                   |
//| Part of XAU_RPB_V1.0.0.                                            |
//+------------------------------------------------------------------+
#property strict

#ifndef XAU_RPB_SETUPMACHINE_MQH
#define XAU_RPB_SETUPMACHINE_MQH

#include "Config.mqh"
#include "Indicators.mqh"

class CSetupMachine
{
private:
   RpbResearch m_p;

   SetupState  m_state;
   int         m_direction;        // +1 long, -1 short, 0 none

   int         m_pullbackBars;
   double      m_pullbackExtreme;
   double      m_breakoutReference;
   double      m_swingExtreme;
   double      m_swingOrigin;
   int         m_windowBarsLeft;
   int         m_setupAgeBars;
   double      m_depthAtr;

   string      m_lastReason;
   bool        m_verboseTransitions;

   void Goto(const SetupState target, const string reason)
   {
      if(target != m_state)
      {
         m_lastReason = reason;
         if(m_verboseTransitions)
            Print("XAU_RPB STATE ", StateName(m_state), " -> ", StateName(target),
                  " reason=", reason);
      }
      m_state = target;
   }

   void ResetSetup(const string reason)
   {
      Goto(STATE_SCANNING, reason);
      m_direction         = 0;
      m_pullbackBars      = 0;
      m_pullbackExtreme   = 0.0;
      m_breakoutReference = 0.0;
      m_swingExtreme      = 0.0;
      m_swingOrigin       = 0.0;
      m_windowBarsLeft    = 0;
      m_setupAgeBars      = 0;
      m_depthAtr          = 0.0;
   }

   //--- A bar closing AGAINST the armed direction (spec §5).
   bool CounterTrend(const double openV, const double closeV) const
   {
      return(m_direction * (closeV - openV) < 0.0);
   }

   int DirectionFor(const MarketRegime regime) const
   {
      if(regime == REGIME_TREND_UP)   return(1);
      if(regime == REGIME_TREND_DOWN) return(-1);
      return(0);
   }

   //--- Impulse leg over the lookback window ENDING at endIdx.
   //--- endIdx is the bar BEFORE the pullback began: including the pullback
   //--- bar would fold its own low into swingOrigin and make the structural
   //--- invalidation test unfalsifiable.
   bool UpdateSwing(const double &highA[], const double &lowA[], const int endIdx)
   {
      int lo = endIdx - m_p.impulseLookback + 1;
      if(endIdx < 0 || lo < 0)
         return(false);

      double hi = highA[lo];
      double lw = lowA[lo];
      for(int i = lo + 1; i <= endIdx; i++)
      {
         if(highA[i] > hi) hi = highA[i];
         if(lowA[i]  < lw) lw = lowA[i];
      }
      if(m_direction > 0) { m_swingExtreme = hi; m_swingOrigin = lw; }
      else                { m_swingExtreme = lw; m_swingOrigin = hi; }
      return(true);
   }

   double ComputeDepth(const double atrM15) const
   {
      if(atrM15 <= 0.0 || !IsUsable(atrM15))
         return(XAU_RPB_NAN);
      return(MathAbs(m_swingExtreme - m_pullbackExtreme) / atrM15);
   }

public:
   void Init(const RpbResearch &p, const bool verboseTransitions = false)
   {
      m_p                  = p;
      m_verboseTransitions = verboseTransitions;
      m_state              = STATE_SCANNING;
      ResetSetup("INIT");
      m_lastReason         = "INIT";
   }

   SetupState State()            const { return(m_state); }
   int        Direction()        const { return(m_direction); }
   double     BreakoutReference()const { return(m_breakoutReference); }
   double     DepthAtr()         const { return(m_depthAtr); }
   int        PullbackBars()     const { return(m_pullbackBars); }
   string     LastReason()       const { return(m_lastReason); }

   //--- Spec §5.4 trigger: strict CLOSE-based break. Wicks never confirm.
   bool BreakoutConfirmed(const double closeV, const double atrM15) const
   {
      double buffer = m_p.breakoutBufferAtr * atrM15;
      if(m_direction > 0)
         return(closeV > m_breakoutReference + buffer);
      return(closeV < m_breakoutReference - buffer);
   }

   //--- Execution-side callbacks (spec §5.5).
   void OnOrderSubmitted()               { Goto(STATE_ORDER_SUBMITTED, "ORDER_SUBMITTED"); }
   void OnFilled()                       { Goto(STATE_IN_POSITION, "FILLED"); }
   void OnRejected(const string reason)  { ResetSetup("REJECTED_" + reason); }
   void OnSignalDiscarded(const string r){ ResetSetup(r); }
   void OnPositionClosed(const string r) { ResetSetup("CLOSED_" + r); }

   //--- Restart recovery (spec §13): resume IN_POSITION without re-entering.
   void AdoptRecoveredPosition(const int direction)
   {
      m_state     = STATE_IN_POSITION;
      m_direction = direction;
      m_lastReason = "RECOVERED";
   }

   //+---------------------------------------------------------------+
   //| Advance by one CLOSED M15 bar. Arrays are CHRONOLOGICAL.       |
   //| Returns true when SIGNAL_READY was reached on this bar.        |
   //+---------------------------------------------------------------+
   bool OnClosedBar(const double &openA[], const double &highA[], const double &lowA[],
                    const double &closeA[], const int idx,
                    const MarketRegime regime, const double atrM15)
   {
      if(m_state == STATE_ORDER_SUBMITTED || m_state == STATE_IN_POSITION)
         return(false);
      int n = ArraySize(closeA);
      if(idx < 0 || idx >= n)
         return(false);

      // Fail closed on an unusable volatility reading (spec §15).
      if(!IsUsable(atrM15) || atrM15 <= 0.0)
      {
         if(m_state != STATE_SCANNING)
            ResetSetup("ATR_INVALID");
         return(false);
      }

      if(m_state != STATE_SCANNING)
         m_setupAgeBars++;

      switch(m_state)
      {
         case STATE_SCANNING:
            return(StepScanning(regime));
         case STATE_ARMED:
            return(StepArmed(openA, highA, lowA, closeA, idx, regime, atrM15));
         case STATE_PULLBACK_ACTIVE:
            return(StepPullback(openA, highA, lowA, closeA, idx, regime, atrM15));
         case STATE_BREAKOUT_WINDOW:
            return(StepWindow(closeA, idx, regime, atrM15));
      }
      return(false);
   }

private:
   bool StepScanning(const MarketRegime regime)
   {
      int dir = DirectionFor(regime);
      if(dir == 0)
         return(false);
      m_direction    = dir;
      m_setupAgeBars = 0;
      Goto(STATE_ARMED, RegimeName(regime));
      return(false);
   }

   //--- The regime must still authorize the direction we armed on.
   bool RegimeStillValid(const MarketRegime regime)
   {
      int dir = DirectionFor(regime);
      if(dir == 0 || dir != m_direction)
      {
         ResetSetup("REGIME_INVALIDATED");
         return(false);
      }
      return(true);
   }

   bool StepArmed(const double &openA[], const double &highA[], const double &lowA[],
                  const double &closeA[], const int idx,
                  const MarketRegime regime, const double atrM15)
   {
      if(!RegimeStillValid(regime))
         return(false);
      if(!CounterTrend(openA[idx], closeA[idx]))
         return(false);
      // The impulse leg is what preceded this bar.
      if(!UpdateSwing(highA, lowA, idx - 1))
         return(false);

      m_pullbackBars = 1;
      if(m_direction > 0)
      {
         m_pullbackExtreme   = lowA[idx];
         m_breakoutReference = MathMax(highA[idx], highA[idx - 1]);
      }
      else
      {
         m_pullbackExtreme   = highA[idx];
         m_breakoutReference = MathMin(lowA[idx], lowA[idx - 1]);
      }
      m_depthAtr = ComputeDepth(atrM15);

      // A "pullback" that immediately breaks the structure is not a pullback.
      if(!IsUsable(m_depthAtr) || m_depthAtr > m_p.maxPullbackDepthAtr)
      {
         ResetSetup("PULLBACK_TOO_DEEP");
         return(false);
      }
      bool structureLost = (m_direction > 0)
                           ? (m_pullbackExtreme < m_swingOrigin)
                           : (m_pullbackExtreme > m_swingOrigin);
      if(structureLost)
      {
         ResetSetup("STRUCTURE_LOST");
         return(false);
      }

      Goto(STATE_PULLBACK_ACTIVE, "PULLBACK_STARTED");
      return(false);
   }

   bool StepPullback(const double &openA[], const double &highA[], const double &lowA[],
                     const double &closeA[], const int idx,
                     const MarketRegime regime, const double atrM15)
   {
      if(!RegimeStillValid(regime))
         return(false);

      bool longSide = (m_direction > 0);

      if(CounterTrend(openA[idx], closeA[idx]))
      {
         m_pullbackBars++;
         if(longSide)
         {
            m_pullbackExtreme   = MathMin(m_pullbackExtreme, lowA[idx]);
            m_breakoutReference = MathMax(m_breakoutReference, highA[idx]);
         }
         else
         {
            m_pullbackExtreme   = MathMax(m_pullbackExtreme, highA[idx]);
            m_breakoutReference = MathMin(m_breakoutReference, lowA[idx]);
         }
         m_depthAtr = ComputeDepth(atrM15);

         if(m_pullbackBars > m_p.maxPullbackBars)
         { ResetSetup("PULLBACK_TOO_LONG"); return(false); }
         if(!IsUsable(m_depthAtr) || m_depthAtr > m_p.maxPullbackDepthAtr)
         { ResetSetup("PULLBACK_TOO_DEEP"); return(false); }
         bool structureLost = longSide ? (m_pullbackExtreme < m_swingOrigin)
                                       : (m_pullbackExtreme > m_swingOrigin);
         if(structureLost)
         { ResetSetup("STRUCTURE_LOST"); return(false); }
         return(false);
      }

      // First non-counter-trend bar: the pullback is over, validate it.
      if(m_pullbackBars < m_p.minPullbackBars)
      { ResetSetup("PULLBACK_TOO_SHORT"); return(false); }

      m_depthAtr = ComputeDepth(atrM15);
      if(!IsUsable(m_depthAtr))
      { ResetSetup("ATR_INVALID"); return(false); }
      if(m_depthAtr < m_p.minPullbackDepthAtr)
      { ResetSetup("PULLBACK_TOO_SHALLOW"); return(false); }
      if(m_depthAtr > m_p.maxPullbackDepthAtr)
      { ResetSetup("PULLBACK_TOO_DEEP"); return(false); }

      // The reference stays frozen at the PULLBACK structure. Extending it with
      // this bar's own high would make the recovery bar - the classic pullback
      // entry - structurally unable to trigger, biasing every entry one bar late.
      m_windowBarsLeft = m_p.breakoutWindowBars;
      Goto(STATE_BREAKOUT_WINDOW, "PULLBACK_COMPLETE");

      if(BreakoutConfirmed(closeA[idx], atrM15))
      {
         Goto(STATE_SIGNAL_READY, "BREAKOUT_CONFIRMED");
         return(true);
      }
      return(false);
   }

   bool StepWindow(const double &closeA[], const int idx,
                   const MarketRegime regime, const double atrM15)
   {
      if(!RegimeStillValid(regime))
         return(false);

      if(BreakoutConfirmed(closeA[idx], atrM15))
      {
         Goto(STATE_SIGNAL_READY, "BREAKOUT_CONFIRMED");
         return(true);
      }

      m_windowBarsLeft--;
      if(m_windowBarsLeft <= 0)
      { ResetSetup("BREAKOUT_WINDOW_EXPIRED"); return(false); }
      if(m_setupAgeBars >= m_p.maxSetupBars)
      { ResetSetup("SETUP_LIFETIME_EXCEEDED"); return(false); }
      return(false);
   }
};

#endif // XAU_RPB_SETUPMACHINE_MQH
