//+------------------------------------------------------------------+
//| Sessions.mqh - time normalization and liquidity windows (spec §11) |
//|                                                                   |
//| The failure this prevents: hardcoding a broker server hour and     |
//| then finding that backtest and live disagree, or that the rule     |
//| silently shifts twice a year at DST transitions.                   |
//|                                                                   |
//| Chain: broker server time -> broker UTC offset -> UTC -> London /  |
//| New York local -> session flags. The offset is an INPUT (or a      |
//| logged auto-detection), never an assumption.                       |
//|                                                                   |
//| MT4 has no timezone database, so DST is computed from the actual   |
//| EU/US rules rather than by table lookup.                           |
//|                                                                   |
//| Part of XAU_RPB_V1.0.0.                                            |
//+------------------------------------------------------------------+
#property strict

#ifndef XAU_RPB_SESSIONS_MQH
#define XAU_RPB_SESSIONS_MQH

#define SEC_PER_HOUR 3600
#define SEC_PER_DAY  86400

//--- Local-exchange windows, in minutes from local midnight (spec §11).
#define LONDON_OPEN_MIN     (8 * 60)
#define LONDON_CLOSE_MIN    (16 * 60 + 30)
#define NEWYORK_OPEN_MIN    (8 * 60)
#define NEWYORK_CLOSE_MIN   (17 * 60)
#define ASIA_OPEN_MIN       (9 * 60)
#define ASIA_CLOSE_MIN      (17 * 60)
#define ROLLOVER_START_UTC  21
#define ROLLOVER_END_UTC    23

struct SessionFlags
{
   datetime utc;
   bool     london;
   bool     newYork;
   bool     overlap;
   bool     asian;
   bool     rollover;
   string   label;
};

//+------------------------------------------------------------------+
//| Day of week for a date, 0 = Sunday (Sakamoto's algorithm).        |
//+------------------------------------------------------------------+
int DayOfWeekFor(const int year, const int month, const int day)
{
   int t[12] = {0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4};
   int y = year;
   if(month < 3)
      y -= 1;
   return((y + y / 4 - y / 100 + y / 400 + t[month - 1] + day) % 7);
}

//+------------------------------------------------------------------+
//| The date of the LAST given weekday in a month (e.g. last Sunday). |
//+------------------------------------------------------------------+
int LastWeekdayOfMonth(const int year, const int month, const int weekday)
{
   int daysInMonth[12] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
   int last = daysInMonth[month - 1];
   if(month == 2 && ((year % 4 == 0 && year % 100 != 0) || year % 400 == 0))
      last = 29;
   while(DayOfWeekFor(year, month, last) != weekday)
      last--;
   return(last);
}

//+------------------------------------------------------------------+
//| EU summer time: last Sunday of March 01:00 UTC to last Sunday of  |
//| October 01:00 UTC.                                                |
//+------------------------------------------------------------------+
bool IsEuropeanSummerTime(const datetime utc)
{
   int year  = TimeYear(utc);
   int month = TimeMonth(utc);
   if(month < 3 || month > 10)
      return(false);
   if(month > 3 && month < 10)
      return(true);

   if(month == 3)
   {
      int start = LastWeekdayOfMonth(year, 3, 0);
      if(TimeDay(utc) > start)  return(true);
      if(TimeDay(utc) < start)  return(false);
      return(TimeHour(utc) >= 1);
   }
   int end = LastWeekdayOfMonth(year, 10, 0);
   if(TimeDay(utc) < end)  return(true);
   if(TimeDay(utc) > end)  return(false);
   return(TimeHour(utc) < 1);
}

//+------------------------------------------------------------------+
//| US daylight time: second Sunday of March 07:00 UTC to first       |
//| Sunday of November 06:00 UTC (approximated at the UTC boundary).  |
//+------------------------------------------------------------------+
bool IsUnitedStatesDaylightTime(const datetime utc)
{
   int year  = TimeYear(utc);
   int month = TimeMonth(utc);
   if(month < 3 || month > 11)
      return(false);
   if(month > 3 && month < 11)
      return(true);

   if(month == 3)
   {
      int firstSunday = 1;
      while(DayOfWeekFor(year, 3, firstSunday) != 0)
         firstSunday++;
      int secondSunday = firstSunday + 7;
      if(TimeDay(utc) > secondSunday)  return(true);
      if(TimeDay(utc) < secondSunday)  return(false);
      return(TimeHour(utc) >= 7);
   }
   int firstSundayNov = 1;
   while(DayOfWeekFor(year, 11, firstSundayNov) != 0)
      firstSundayNov++;
   if(TimeDay(utc) < firstSundayNov)  return(true);
   if(TimeDay(utc) > firstSundayNov)  return(false);
   return(TimeHour(utc) < 6);
}

//+------------------------------------------------------------------+
//| Broker server timestamp -> UTC, using the configured offset.      |
//+------------------------------------------------------------------+
datetime BrokerToUtc(const datetime brokerTime, const double brokerUtcOffsetHours)
{
   return((datetime)(brokerTime - (int)MathRound(brokerUtcOffsetHours * SEC_PER_HOUR)));
}

int MinutesOfDay(const datetime t)
{
   return(TimeHour(t) * 60 + TimeMinute(t));
}

//+------------------------------------------------------------------+
//| Full DST-aware session classification for a broker-time instant.  |
//+------------------------------------------------------------------+
SessionFlags ResolveSession(const datetime brokerTime, const double brokerUtcOffsetHours)
{
   SessionFlags f;
   f.utc = BrokerToUtc(brokerTime, brokerUtcOffsetHours);

   int londonOffset = IsEuropeanSummerTime(f.utc)      ?  1 :  0;   // UTC+1 / UTC+0
   int newYorkOffset= IsUnitedStatesDaylightTime(f.utc)? -4 : -5;   // UTC-4 / UTC-5
   int tokyoOffset  = 9;                                            // Japan has no DST

   datetime londonLocal = (datetime)(f.utc + londonOffset  * SEC_PER_HOUR);
   datetime nyLocal     = (datetime)(f.utc + newYorkOffset * SEC_PER_HOUR);
   datetime tokyoLocal  = (datetime)(f.utc + tokyoOffset   * SEC_PER_HOUR);

   int londonMin = MinutesOfDay(londonLocal);
   int nyMin     = MinutesOfDay(nyLocal);
   int tokyoMin  = MinutesOfDay(tokyoLocal);

   f.london   = (londonMin >= LONDON_OPEN_MIN  && londonMin < LONDON_CLOSE_MIN);
   f.newYork  = (nyMin     >= NEWYORK_OPEN_MIN && nyMin     < NEWYORK_CLOSE_MIN);
   f.asian    = (tokyoMin  >= ASIA_OPEN_MIN    && tokyoMin  < ASIA_CLOSE_MIN);
   f.overlap  = (f.london && f.newYork);
   f.rollover = (TimeHour(f.utc) >= ROLLOVER_START_UTC && TimeHour(f.utc) < ROLLOVER_END_UTC);

   if(f.rollover)      f.label = "ROLLOVER";
   else if(f.overlap)  f.label = "OVERLAP";
   else if(f.london)   f.label = "LONDON";
   else if(f.newYork)  f.label = "NEW_YORK";
   else if(f.asian)    f.label = "ASIAN";
   else                f.label = "OFF_SESSION";
   return(f);
}

//+------------------------------------------------------------------+
//| V1 default permitted window: London or New York, minus rollover.  |
//+------------------------------------------------------------------+
bool IsSessionPermitted(const datetime brokerTime, const double brokerUtcOffsetHours,
                        const bool allowAsian, const bool blockRollover)
{
   SessionFlags f = ResolveSession(brokerTime, brokerUtcOffsetHours);
   if(blockRollover && f.rollover)
      return(false);
   if(f.london || f.newYork)
      return(true);
   return(allowAsian && f.asian);
}

//+------------------------------------------------------------------+
//| Auto-detect the server offset by comparing TimeCurrent to TimeGMT.|
//|                                                                   |
//| In the MT4 Strategy Tester TimeGMT() is documented to equal the    |
//| simulated server time, which would yield an offset of 0. The       |
//| caller must therefore pass an explicit offset for reproducible     |
//| backtests; the detected value is returned for LOGGING and live use.|
//+------------------------------------------------------------------+
double DetectBrokerUtcOffsetHours()
{
   double raw = (double)(TimeCurrent() - TimeGMT()) / (double)SEC_PER_HOUR;
   return(MathRound(raw * 4.0) / 4.0);   // quarter-hour resolution
}

#endif // XAU_RPB_SESSIONS_MQH
