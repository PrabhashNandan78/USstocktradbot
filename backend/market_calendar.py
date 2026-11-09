"""
Official US Exchange Trading Calendar & Market Status Service (NYSE / Nasdaq).

Accurately computes US Equities market sessions using the America/New_York timezone.
Accounts for:
- Regular Trading Sessions (09:30 to 16:00 ET)
- Early-Close Sessions (09:30 to 13:00 ET, e.g. Black Friday, Christmas Eve, July 3)
- Pre-Market Sessions (04:00 to 09:30 ET)
- After-Hours Sessions (16:00 to 20:00 ET)
- Full-Day Exchange Holidays (NYSE Rule 7.2)
- Weekends (Saturday & Sunday)
- Daylight Saving Time (EDT UTC-4 / EST UTC-5)
- Deterministic calculation of next market open and close
"""

from datetime import date, datetime, time, timedelta
from typing import Dict, Any, Optional, Tuple
from zoneinfo import ZoneInfo

NY_TZ = ZoneInfo("America/New_York")


def get_easter_sunday(year: int) -> date:
    """Computes Western Easter Sunday using Meeus/Jones/Butcher algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _get_nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """Returns the n-th occurrence of a weekday in a given month (1-indexed). Weekday: 0=Mon, 6=Sun."""
    first_day = date(year, month, 1)
    day_offset = (weekday - first_day.weekday()) % 7
    first_occurrence = first_day + timedelta(days=day_offset)
    return first_occurrence + timedelta(weeks=n - 1)


def _get_last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """Returns the last occurrence of a weekday in a given month."""
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = next_month - timedelta(days=1)
    day_offset = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=day_offset)


class NYSECalendar:
    """
    Authoritative NYSE / Nasdaq Trading Calendar.
    Enforces official exchange holiday schedules and session boundaries.
    """

    @staticmethod
    def get_ny_time(now: Optional[datetime] = None) -> datetime:
        """Returns the current timestamp in America/New_York timezone."""
        if now is None:
            return datetime.now(NY_TZ)
        if now.tzinfo is None:
            return now.replace(tzinfo=NY_TZ)
        return now.astimezone(NY_TZ)

    @classmethod
    def get_holidays(cls, year: int) -> Dict[date, str]:
        """
        Returns all official NYSE full-day holidays for a given year,
        including standard weekend observance shifts.
        """
        holidays: Dict[date, str] = {}

        # 1. New Year's Day (Jan 1)
        # If Jan 1 is Sunday, observed Monday Jan 2.
        # Note: If Jan 1 is Saturday, NYSE does not observe on Friday Dec 31 (Rule 7.2).
        nyd = date(year, 1, 1)
        if nyd.weekday() == 6:  # Sunday
            holidays[date(year, 1, 2)] = "New Year's Day (Observed)"
        elif nyd.weekday() != 5:  # Not Saturday
            holidays[nyd] = "New Year's Day"

        # 2. Martin Luther King, Jr. Day (Third Monday in January)
        holidays[_get_nth_weekday_of_month(year, 1, 0, 3)] = "Martin Luther King, Jr. Day"

        # 3. Washington's Birthday / Presidents' Day (Third Monday in February)
        holidays[_get_nth_weekday_of_month(year, 2, 0, 3)] = "Washington's Birthday / Presidents' Day"

        # 4. Good Friday (Friday before Easter Sunday)
        easter = get_easter_sunday(year)
        good_friday = easter - timedelta(days=2)
        holidays[good_friday] = "Good Friday"

        # 5. Memorial Day (Last Monday in May)
        holidays[_get_last_weekday_of_month(year, 5, 0)] = "Memorial Day"

        # 6. Juneteenth National Independence Day (June 19, established 2021)
        if year >= 2021:
            june19 = date(year, 6, 19)
            if june19.weekday() == 5:  # Saturday -> Friday June 18
                holidays[date(year, 6, 18)] = "Juneteenth National Independence Day (Observed)"
            elif june19.weekday() == 6:  # Sunday -> Monday June 20
                holidays[date(year, 6, 20)] = "Juneteenth National Independence Day (Observed)"
            else:
                holidays[june19] = "Juneteenth National Independence Day"

        # 7. Independence Day (July 4)
        july4 = date(year, 7, 4)
        if july4.weekday() == 5:  # Saturday -> Friday July 3
            holidays[date(year, 7, 3)] = "Independence Day (Observed)"
        elif july4.weekday() == 6:  # Sunday -> Monday July 5
            holidays[date(year, 7, 5)] = "Independence Day (Observed)"
        else:
            holidays[july4] = "Independence Day"

        # 8. Labor Day (First Monday in September)
        holidays[_get_nth_weekday_of_month(year, 9, 0, 1)] = "Labor Day"

        # 9. Thanksgiving Day (Fourth Thursday in November)
        thanksgiving = _get_nth_weekday_of_month(year, 11, 3, 4)
        holidays[thanksgiving] = "Thanksgiving Day"

        # 10. Christmas Day (December 25)
        xmas = date(year, 12, 25)
        if xmas.weekday() == 5:  # Saturday -> Friday Dec 24
            holidays[date(year, 12, 24)] = "Christmas Day (Observed)"
        elif xmas.weekday() == 6:  # Sunday -> Monday Dec 26
            holidays[date(year, 12, 26)] = "Christmas Day (Observed)"
        else:
            holidays[xmas] = "Christmas Day"

        return holidays

    @classmethod
    def get_early_close_days(cls, year: int) -> Dict[date, Tuple[time, str]]:
        """
        Returns official NYSE early-close days for a given year (1:00 PM Eastern close = 13:00).
        """
        early_closes: Dict[date, Tuple[time, str]] = {}
        close_1pm = time(13, 0)

        # 1. Day before Independence Day (July 3), if a weekday and July 4 is not Saturday
        july3 = date(year, 7, 3)
        july4 = date(year, 7, 4)
        # If July 4 is Tue, Wed, Thu, Fri, July 3 is an early close (if it's a weekday)
        if july3.weekday() < 5 and july4.weekday() in (1, 2, 3, 4):
            early_closes[july3] = (close_1pm, "Day Before Independence Day")

        # 2. Black Friday (Day after Thanksgiving, 4th Friday in November)
        thanksgiving = _get_nth_weekday_of_month(year, 11, 3, 4)
        black_friday = thanksgiving + timedelta(days=1)
        early_closes[black_friday] = (close_1pm, "Day After Thanksgiving (Black Friday)")

        # 3. Christmas Eve (Dec 24), if a weekday and not an observed holiday
        xmas_eve = date(year, 12, 24)
        xmas = date(year, 12, 25)
        # If Dec 25 is Saturday, Dec 24 is a full holiday (Observed), not an early close
        if xmas_eve.weekday() < 5 and xmas.weekday() != 5:
            early_closes[xmas_eve] = (close_1pm, "Christmas Eve")

        return early_closes

    @classmethod
    def is_holiday(cls, check_date: date) -> Tuple[bool, Optional[str]]:
        """Checks if a given date is an official US exchange holiday."""
        holidays = cls.get_holidays(check_date.year)
        if check_date in holidays:
            return True, holidays[check_date]
        return False, None

    @classmethod
    def is_early_close(cls, check_date: date) -> Tuple[bool, Optional[time], Optional[str]]:
        """Checks if a given date has an official 1:00 PM early close."""
        early_closes = cls.get_early_close_days(check_date.year)
        if check_date in early_closes:
            close_time, reason = early_closes[check_date]
            return True, close_time, reason
        return False, None, None

    @classmethod
    def is_trading_day(cls, check_date: date) -> bool:
        """Returns True if the exchange is open for trading on check_date (Mon-Fri and not a holiday)."""
        if check_date.weekday() >= 5:  # Saturday or Sunday
            return False
        is_hol, _ = cls.is_holiday(check_date)
        return not is_hol

    @classmethod
    def get_market_status(cls, now: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Calculates the complete, authoritative market status for a specific or current timestamp.
        Returns:
            - status: "PRE_MARKET" | "OPEN" | "AFTER_HOURS" | "CLOSED" | "HOLIDAY"
            - ny_time: Current Eastern timestamp
            - trading_date: Current Eastern date string
            - regular_session_open: Today's 09:30 Eastern timestamp
            - regular_session_close: Today's 16:00 (or 13:00) Eastern timestamp
            - next_market_open: Timestamp of the next 09:30 regular market opening
            - next_market_close: Timestamp of the next regular market closing
            - is_holiday: bool
            - is_early_close: bool
            - holiday_name: Optional[str]
            - session_type: "REGULAR" | "EARLY_CLOSE" | "HOLIDAY" | "WEEKEND"
        """
        ny_now = cls.get_ny_time(now)
        today = ny_now.date()
        current_time = ny_now.time()

        is_hol, hol_name = cls.is_holiday(today)
        is_early, early_time, early_reason = cls.is_early_close(today)
        regular_close_time = early_time if (is_early and early_time) else time(16, 0)

        # Datetimes for today's session boundaries in Eastern Time
        pre_market_start = datetime.combine(today, time(4, 0), tzinfo=NY_TZ)
        regular_open = datetime.combine(today, time(9, 30), tzinfo=NY_TZ)
        regular_close = datetime.combine(today, regular_close_time, tzinfo=NY_TZ)
        after_hours_end = datetime.combine(today, time(20, 0), tzinfo=NY_TZ)

        session_type = "REGULAR"
        if today.weekday() >= 5:
            session_type = "WEEKEND"
        elif is_hol:
            session_type = "HOLIDAY"
        elif is_early:
            session_type = "EARLY_CLOSE"

        # Determine status
        if today.weekday() >= 5:
            status = "CLOSED"
        elif is_hol:
            status = "HOLIDAY"
        else:
            if current_time < time(4, 0):
                status = "CLOSED"
            elif time(4, 0) <= current_time < time(9, 30):
                status = "PRE_MARKET"
            elif time(9, 30) <= current_time < regular_close_time:
                status = "OPEN"
            elif regular_close_time <= current_time < time(20, 0):
                status = "AFTER_HOURS"
            else:
                status = "CLOSED"

        # Calculate next market open and next market close
        next_open = cls._calculate_next_open(ny_now, status)
        next_close = cls._calculate_next_close(ny_now, status, regular_close)

        return {
            "status": status,
            "ny_time": ny_now.isoformat(),
            "trading_date": today.isoformat(),
            "regular_session_open": regular_open.isoformat(),
            "regular_session_close": regular_close.isoformat(),
            "next_market_open": next_open.isoformat(),
            "next_market_close": next_close.isoformat(),
            "is_holiday": is_hol,
            "is_early_close": is_early,
            "holiday_name": hol_name,
            "session_type": session_type,
            "early_close_reason": early_reason if is_early else None
        }

    @classmethod
    def _calculate_next_open(cls, ny_now: datetime, status: str) -> datetime:
        """Finds the next 09:30 AM regular session opening datetime."""
        today = ny_now.date()
        # If currently in PRE_MARKET or CLOSED before 09:30 on a trading day:
        if status in ("PRE_MARKET", "CLOSED") and cls.is_trading_day(today) and ny_now.time() < time(9, 30):
            return datetime.combine(today, time(9, 30), tzinfo=NY_TZ)

        # Otherwise, look at future days
        cand_date = today + timedelta(days=1)
        while not cls.is_trading_day(cand_date):
            cand_date += timedelta(days=1)
        return datetime.combine(cand_date, time(9, 30), tzinfo=NY_TZ)

    @classmethod
    def _calculate_next_close(cls, ny_now: datetime, status: str, today_close: datetime) -> datetime:
        """Finds the next regular session closing datetime."""
        today = ny_now.date()
        # If currently before today's close on a trading day:
        if cls.is_trading_day(today) and ny_now < today_close:
            return today_close

        # Otherwise, find the close time of the next trading day
        cand_date = today + timedelta(days=1)
        while not cls.is_trading_day(cand_date):
            cand_date += timedelta(days=1)

        is_early, early_time, _ = cls.is_early_close(cand_date)
        close_t = early_time if (is_early and early_time) else time(16, 0)
        return datetime.combine(cand_date, close_t, tzinfo=NY_TZ)

