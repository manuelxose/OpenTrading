//+------------------------------------------------------------------+
//| News.mqh - high-impact news risk filter (spec §12)                 |
//|                                                                   |
//| News NEVER predicts direction. It only blocks new entries inside a |
//| blackout window.                                                   |
//|                                                                   |
//| The calendar is a FROZEN, VERSIONED CSV, never a live API:         |
//| WebRequest() does not execute inside the MT4 Strategy Tester, and  |
//| a backtest whose inputs can change between runs is not             |
//| reproducible. A missing or malformed file FAILS CLOSED when the    |
//| filter is marked required (spec §15).                              |
//|                                                                   |
//| CSV schema (UTC, header mandatory):                                |
//|   event_time_utc,currency,impact,event_name                        |
//|   2024-01-11T13:30:00Z,USD,HIGH,CPI m/m                            |
//|                                                                   |
//| Part of XAU_RPB_V1.0.0.                                            |
//+------------------------------------------------------------------+
#property strict

#ifndef XAU_RPB_NEWS_MQH
#define XAU_RPB_NEWS_MQH

#define RPB_MAX_NEWS_EVENTS 4096

class CNewsCalendar
{
private:
   datetime m_times[RPB_MAX_NEWS_EVENTS];
   int      m_count;
   int      m_beforeSec;
   int      m_afterSec;
   bool     m_required;
   bool     m_loaded;
   string   m_source;

   //--- Parse "2024-01-11T13:30:00Z" or "2024-01-11 13:30:00" to a datetime.
   bool ParseUtcTimestamp(string raw, datetime &out) const
   {
      StringTrimLeft(raw);
      StringTrimRight(raw);
      if(StringLen(raw) < 16)
         return(false);
      StringReplace(raw, "T", " ");
      StringReplace(raw, "Z", "");
      StringReplace(raw, "-", ".");
      // MQL4's StrToTime accepts "YYYY.MM.DD HH:MM[:SS]".
      datetime parsed = StrToTime(raw);
      if(parsed <= 0)
         return(false);
      out = parsed;
      return(true);
   }

   void SortTimes()
   {
      // Insertion sort: calendars are small and usually already ordered.
      for(int i = 1; i < m_count; i++)
      {
         datetime key = m_times[i];
         int j = i - 1;
         while(j >= 0 && m_times[j] > key)
         {
            m_times[j + 1] = m_times[j];
            j--;
         }
         m_times[j + 1] = key;
      }
   }

public:
   void Init(const int beforeMin, const int afterMin, const bool required)
   {
      m_count     = 0;
      m_beforeSec = beforeMin * 60;
      m_afterSec  = afterMin * 60;
      m_required  = required;
      m_loaded    = !required;   // an optional, unloaded calendar simply never blocks
      m_source    = "<none>";
   }

   int  Count()    const { return(m_count); }
   bool IsUsable() const { return(m_loaded || !m_required); }
   string Source() const { return(m_source); }

   //--- Mark the calendar unusable so every query fails closed.
   void MarkFailed(const string source)
   {
      m_count  = 0;
      m_loaded = false;
      m_source = source;
      Print("XAU_RPB FAIL-CLOSED: news calendar unusable (", source,
            ") - new entries will be blocked while the filter is required");
   }

   //+---------------------------------------------------------------+
   //| Load the frozen CSV from MQL4/Files. Returns false and fails   |
   //| closed when the file is absent or the header is wrong.         |
   //+---------------------------------------------------------------+
   bool LoadFromCsv(const string filename, const string currencyFilter = "USD")
   {
      m_count = 0;
      if(StringLen(filename) == 0)
      {
         if(m_required)
         { MarkFailed("no news file configured"); return(false); }
         m_loaded = true;
         m_source = "<none>";
         return(true);
      }

      int handle = FileOpen(filename, FILE_READ | FILE_CSV | FILE_ANSI, ',');
      if(handle == INVALID_HANDLE)
      {
         MarkFailed(filename + " (open failed, error " + IntegerToString(GetLastError()) + ")");
         return(false);
      }

      // Header row must name the timestamp column.
      string h0 = FileReadString(handle);
      if(StringFind(h0, "event_time_utc") < 0)
      {
         FileClose(handle);
         MarkFailed(filename + " (missing 'event_time_utc' header)");
         return(false);
      }
      while(!FileIsLineEnding(handle) && !FileIsEnding(handle))
         FileReadString(handle);

      int skipped = 0;
      while(!FileIsEnding(handle) && m_count < RPB_MAX_NEWS_EVENTS)
      {
         string rawTime = FileReadString(handle);
         if(FileIsEnding(handle) && StringLen(rawTime) == 0)
            break;
         string currency = FileIsLineEnding(handle) ? "" : FileReadString(handle);
         string impact   = FileIsLineEnding(handle) ? "" : FileReadString(handle);
         while(!FileIsLineEnding(handle) && !FileIsEnding(handle))
            FileReadString(handle);   // discard the event name and any extra columns

         StringTrimLeft(currency);  StringTrimRight(currency);
         StringTrimLeft(impact);    StringTrimRight(impact);
         StringToUpper(currency);
         StringToUpper(impact);

         if(impact != "HIGH" && impact != "H" && impact != "3")
            continue;
         if(StringLen(currencyFilter) > 0 && currency != currencyFilter)
            continue;

         datetime parsed = 0;
         if(!ParseUtcTimestamp(rawTime, parsed))
         { skipped++; continue; }

         m_times[m_count] = parsed;
         m_count++;
      }
      FileClose(handle);

      SortTimes();
      m_loaded = true;
      m_source = filename;
      Print("XAU_RPB: news calendar '", filename, "' loaded, ", m_count,
            " high-impact ", currencyFilter, " events (", skipped, " unparseable rows skipped)");
      return(true);
   }

   //+---------------------------------------------------------------+
   //| True when new entries must be blocked at `momentUtc`.          |
   //+---------------------------------------------------------------+
   bool IsBlackout(const datetime momentUtc) const
   {
      if(!IsUsable())
         return(true);           // fail closed
      if(m_count == 0)
         return(false);

      // Binary search for the first event that could still be blocking.
      int lo = 0, hi = m_count - 1, first = m_count;
      datetime threshold = (datetime)(momentUtc - m_afterSec);
      while(lo <= hi)
      {
         int mid = (lo + hi) / 2;
         if(m_times[mid] >= threshold) { first = mid; hi = mid - 1; }
         else                          { lo = mid + 1; }
      }
      for(int i = first; i < m_count; i++)
      {
         datetime start = (datetime)(m_times[i] - m_beforeSec);
         datetime end   = (datetime)(m_times[i] + m_afterSec);
         if(start > momentUtc)
            return(false);       // events are sorted, so nothing later can match
         if(momentUtc >= start && momentUtc <= end)
            return(true);
      }
      return(false);
   }
};

#endif // XAU_RPB_NEWS_MQH
