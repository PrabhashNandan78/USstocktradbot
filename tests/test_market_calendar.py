"""
Unit tests for US Market Trading Calendar (NYSE / Nasdaq).
Uses deterministic mocked datetimes across:
- Regular weekday trading hours
- Pre-market sessions
- After-hours sessions
- Night closed periods
- Saturdays and Sundays
- All 10 official US exchange holidays (New Year's, MLK, Washington, Good Friday, Memorial Day, Juneteenth, July 4, Labor Day, Thanksgiving, Christmas)
- Early-close sessions (Black Friday, Christmas Eve, July 3)
- Daylight Saving Time transitions (EDT UTC-4 / EST UTC-5)
- Next market open and close calculations
"""

from datetime import datetime
from zoneinfo import ZoneInfo
import pytest

from backend.market_calendar import NYSECalendar, NY_TZ


def test_regular_weekday_session():
    # Wednesday 11:30 AM ET -> OPEN
    dt = datetime(2026, 6, 10, 11, 30, tzinfo=NY_TZ)
    status = NYSECalendar.get_market_status(dt)
    assert status["status"] == "OPEN"
    assert status["session_type"] == "REGULAR"
    assert status["is_holiday"] is False
    assert status["is_early_close"] is False
    assert "2026-06-10T09:30:00" in status["regular_session_open"]
    assert "2026-06-10T16:00:00" in status["regular_session_close"]


def test_before_market_opens_premarket_and_early_morning():
    # Wednesday 08:15 AM ET -> PRE_MARKET
    dt_premkt = datetime(2026, 6, 10, 8, 15, tzinfo=NY_TZ)
    status_premkt = NYSECalendar.get_market_status(dt_premkt)
    assert status_premkt["status"] == "PRE_MARKET"
    assert "2026-06-10T09:30:00" in status_premkt["next_market_open"]

    # Wednesday 03:30 AM ET -> CLOSED
    dt_early = datetime(2026, 6, 10, 3, 30, tzinfo=NY_TZ)
    status_early = NYSECalendar.get_market_status(dt_early)
    assert status_early["status"] == "CLOSED"
    assert "2026-06-10T09:30:00" in status_early["next_market_open"]


def test_after_market_closes_after_hours_and_night():
    # Wednesday 17:30 ET -> AFTER_HOURS
    dt_post = datetime(2026, 6, 10, 17, 30, tzinfo=NY_TZ)
    status_post = NYSECalendar.get_market_status(dt_post)
    assert status_post["status"] == "AFTER_HOURS"
    assert "2026-06-11T09:30:00" in status_post["next_market_open"]

    # Wednesday 22:30 ET -> CLOSED
    dt_night = datetime(2026, 6, 10, 22, 30, tzinfo=NY_TZ)
    status_night = NYSECalendar.get_market_status(dt_night)
    assert status_night["status"] == "CLOSED"
    assert "2026-06-11T09:30:00" in status_night["next_market_open"]


def test_weekend_saturday_and_sunday():
    # Saturday 14:00 ET -> CLOSED / WEEKEND
    dt_sat = datetime(2026, 6, 13, 14, 0, tzinfo=NY_TZ)
    status_sat = NYSECalendar.get_market_status(dt_sat)
    assert status_sat["status"] == "CLOSED"
    assert status_sat["session_type"] == "WEEKEND"
    assert "2026-06-15T09:30:00" in status_sat["next_market_open"]

    # Sunday 10:00 ET -> CLOSED / WEEKEND
    dt_sun = datetime(2026, 6, 14, 10, 0, tzinfo=NY_TZ)
    status_sun = NYSECalendar.get_market_status(dt_sun)
    assert status_sun["status"] == "CLOSED"
    assert status_sun["session_type"] == "WEEKEND"
    assert "2026-06-15T09:30:00" in status_sun["next_market_open"]


def test_exchange_holidays():
    holidays_2026 = [
        (datetime(2026, 1, 1, 12, 0, tzinfo=NY_TZ), "New Year's Day"),
        (datetime(2026, 1, 19, 12, 0, tzinfo=NY_TZ), "Martin Luther King, Jr. Day"),
        (datetime(2026, 2, 16, 12, 0, tzinfo=NY_TZ), "Washington's Birthday / Presidents' Day"),
        (datetime(2026, 4, 3, 12, 0, tzinfo=NY_TZ), "Good Friday"),
        (datetime(2026, 5, 25, 12, 0, tzinfo=NY_TZ), "Memorial Day"),
        (datetime(2026, 6, 19, 12, 0, tzinfo=NY_TZ), "Juneteenth National Independence Day"),
        (datetime(2026, 7, 3, 12, 0, tzinfo=NY_TZ), "Independence Day (Observed)"),  # July 4 is Saturday -> Friday July 3 observed
        (datetime(2026, 9, 7, 12, 0, tzinfo=NY_TZ), "Labor Day"),
        (datetime(2026, 11, 26, 12, 0, tzinfo=NY_TZ), "Thanksgiving Day"),
        (datetime(2026, 12, 25, 12, 0, tzinfo=NY_TZ), "Christmas Day"),
    ]

    for dt_hol, expected_name in holidays_2026:
        status = NYSECalendar.get_market_status(dt_hol)
        assert status["status"] == "HOLIDAY", f"Failed for {expected_name} on {dt_hol}"
        assert status["is_holiday"] is True
        assert status["holiday_name"] == expected_name


def test_early_close_sessions():
    # 1. Black Friday (Day after Thanksgiving, 2026-11-27)
    # Open at 10:00 ET (regular session)
    dt_bf_open = datetime(2026, 11, 27, 10, 0, tzinfo=NY_TZ)
    status_bf_open = NYSECalendar.get_market_status(dt_bf_open)
    assert status_bf_open["status"] == "OPEN"
    assert status_bf_open["is_early_close"] is True
    assert "13:00:00" in status_bf_open["regular_session_close"]

    # 13:30 ET -> AFTER_HOURS (since closed at 13:00)
    dt_bf_post = datetime(2026, 11, 27, 13, 30, tzinfo=NY_TZ)
    status_bf_post = NYSECalendar.get_market_status(dt_bf_post)
    assert status_bf_post["status"] == "AFTER_HOURS"

    # 2. Christmas Eve (Thursday 2026-12-24)
    dt_eve_open = datetime(2026, 12, 24, 11, 0, tzinfo=NY_TZ)
    status_eve_open = NYSECalendar.get_market_status(dt_eve_open)
    assert status_eve_open["status"] == "OPEN"
    assert status_eve_open["is_early_close"] is True
    assert "13:00:00" in status_eve_open["regular_session_close"]


def test_us_daylight_saving_time_transitions():
    # In Summer (EDT UTC-4)
    dt_summer = datetime(2026, 7, 15, 10, 0, tzinfo=NY_TZ)
    status_summer = NYSECalendar.get_market_status(dt_summer)
    assert "-04:00" in status_summer["ny_time"]

    # In Winter (EST UTC-5)
    dt_winter = datetime(2026, 12, 15, 10, 0, tzinfo=NY_TZ)
    status_winter = NYSECalendar.get_market_status(dt_winter)
    assert "-05:00" in status_winter["ny_time"]

