//+------------------------------------------------------------------+
//| Telemetry.mqh - structured decision logging (spec §28, §29)        |
//|                                                                   |
//| Machine-readable CSV, one row per decision, written to MQL4/Files. |
//| The point is reconstruction: given these rows a reviewer can       |
//| replay why the EA did - or refused to do - anything, without       |
//| guessing from price action afterwards.                             |
//|                                                                   |
//| Telemetry never influences a trading decision, and a telemetry     |
//| failure never blocks or alters one.                                |
//|                                                                   |
//| Part of XAU_RPB_V1.0.0.                                            |
//+------------------------------------------------------------------+
#property strict

#ifndef XAU_RPB_TELEMETRY_MQH
#define XAU_RPB_TELEMETRY_MQH

#include "Config.mqh"

#define RPB_TELEMETRY_HEADER \
   "broker_time,utc_time,spec_version,config_id,symbol,event,state,regime," \
   "ema_fast,ema_slow,adx,er,atr_h1,atr_m15,norm_spread,norm_slope,atr_pct," \
   "direction,depth_atr,breakout_ref,score,score_regime,score_slope,score_depth," \
   "score_breakout,score_atr,score_session,score_spread,session,spread_points," \
   "entry,stop,target,lots,risk_pct,risk_money,expected_r,ticket,reject_reason," \
   "exit_reason,realized_pnl,realized_r,mae,mfe,bars_held,equity,broker_error"

class CTelemetry
{
private:
   string m_file;
   bool   m_enabled;
   bool   m_headerWritten;
   string m_configId;

   string Esc(const string v) const
   {
      string out = v;
      StringReplace(out, ",", ";");   // keep the CSV single-line and parseable
      StringReplace(out, "\n", " ");
      return(out);
   }

public:
   void Init(const string filename, const bool enabled, const string configId)
   {
      m_file          = filename;
      m_enabled       = enabled;
      m_headerWritten = false;
      m_configId      = configId;

      if(!m_enabled)
         return;

      // Append-only: a restart must never erase the prior decision history.
      int handle = FileOpen(m_file, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
      if(handle == INVALID_HANDLE)
      {
         Print("XAU_RPB: telemetry disabled, cannot open '", m_file,
               "' error=", GetLastError());
         m_enabled = false;
         return;
      }
      if(FileSize(handle) == 0)
      {
         FileWrite(handle, RPB_TELEMETRY_HEADER);
         m_headerWritten = true;
      }
      FileClose(handle);
      Print("XAU_RPB: telemetry -> MQL4/Files/", m_file);
   }

   //+---------------------------------------------------------------+
   //| Append one pre-formatted decision row.                         |
   //+---------------------------------------------------------------+
   void Write(const string row)
   {
      if(!m_enabled)
         return;
      int handle = FileOpen(m_file, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
      if(handle == INVALID_HANDLE)
         return;                       // never block trading on a logging failure
      FileSeek(handle, 0, SEEK_END);
      FileWrite(handle, row);
      FileClose(handle);
   }

   string ConfigId() const { return(m_configId); }

   //--- Convenience builder for the common "decision" row shape.
   string BuildRow(const datetime brokerTime, const datetime utcTime, const string symbol,
                   const string eventName, const string state, const string regime,
                   const double emaFast, const double emaSlow, const double adx,
                   const double er, const double atrH1, const double atrM15,
                   const double normSpread, const double normSlope, const double atrPct,
                   const string direction, const double depthAtr, const double breakoutRef,
                   const int score, const string scoreParts, const string session,
                   const double spreadPoints, const double entry, const double stop,
                   const double target, const double lots, const double riskPct,
                   const double riskMoney, const double expectedR, const int ticket,
                   const string rejectReason, const string exitReason,
                   const double realizedPnl, const double realizedR,
                   const double mae, const double mfe, const int barsHeld,
                   const double equity, const string brokerError)
   {
      string row = TimeToString(brokerTime, TIME_DATE | TIME_SECONDS) + "," +
                   TimeToString(utcTime,    TIME_DATE | TIME_SECONDS) + "," +
                   XAU_RPB_SPEC_VERSION + "," + m_configId + "," + Esc(symbol) + "," +
                   Esc(eventName) + "," + Esc(state) + "," + Esc(regime) + "," +
                   DoubleToString(emaFast, 5) + "," + DoubleToString(emaSlow, 5) + "," +
                   DoubleToString(adx, 4) + "," + DoubleToString(er, 4) + "," +
                   DoubleToString(atrH1, 5) + "," + DoubleToString(atrM15, 5) + "," +
                   DoubleToString(normSpread, 5) + "," + DoubleToString(normSlope, 5) + "," +
                   DoubleToString(atrPct, 4) + "," + Esc(direction) + "," +
                   DoubleToString(depthAtr, 4) + "," + DoubleToString(breakoutRef, 5) + "," +
                   IntegerToString(score) + "," + scoreParts + "," + Esc(session) + "," +
                   DoubleToString(spreadPoints, 1) + "," +
                   DoubleToString(entry, 5) + "," + DoubleToString(stop, 5) + "," +
                   DoubleToString(target, 5) + "," + DoubleToString(lots, 2) + "," +
                   DoubleToString(riskPct, 4) + "," + DoubleToString(riskMoney, 2) + "," +
                   DoubleToString(expectedR, 3) + "," + IntegerToString(ticket) + "," +
                   Esc(rejectReason) + "," + Esc(exitReason) + "," +
                   DoubleToString(realizedPnl, 2) + "," + DoubleToString(realizedR, 3) + "," +
                   DoubleToString(mae, 5) + "," + DoubleToString(mfe, 5) + "," +
                   IntegerToString(barsHeld) + "," + DoubleToString(equity, 2) + "," +
                   Esc(brokerError);
      return(row);
   }
};

#endif // XAU_RPB_TELEMETRY_MQH
