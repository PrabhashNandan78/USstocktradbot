"""
Automated unit tests for Central Quote Validation Layer (DataValidator.validate_quote).
Validates:
- Fresh quote in open market
- Stale quote in open market
- Missing quote handling
- Zero and negative price rejection
- Non-finite (NaN / Inf) price rejection
- Invalid / future timestamp handling
- Delayed quote handling
- Last available quote during closed market
- Distinction between missing quotes, stale quotes, provider errors, and symbol resolution failures
"""

from datetime import datetime, timezone, timedelta
import math
import pytest

from backend.data_validator import DataValidator


def test_fresh_quote_open_market():
    now_utc = datetime(2026, 6, 10, 15, 0, tzinfo=timezone.utc)
    quote_data = {
        "latestTrade": {"p": 182.50, "t": (now_utc - timedelta(seconds=25)).isoformat()},
        "dailyBar": {"o": 180.0, "h": 183.0, "l": 179.5, "c": 182.50, "v": 1500000}
    }

    res = DataValidator.validate_quote(
        quote_data,
        "AAPL",
        market_status="OPEN",
        max_age_seconds=120,
        now=now_utc
    )

    assert res["is_valid"] is True
    assert res["freshness"] == "LIVE"
    assert res["category"] == "VALID"
    assert res["is_live_executable"] is True
    assert res["price"] == 182.50
    assert res["volume"] == 1500000
    assert res["data_source"] == "TradingView Real-Time"
    assert res["error_reason"] is None


def test_stale_quote_open_market():
    now_utc = datetime(2026, 6, 10, 15, 0, tzinfo=timezone.utc)
    # Quote timestamp is 350 seconds old (exceeds 120s threshold)
    quote_data = {
        "latestTrade": {"p": 182.50, "t": (now_utc - timedelta(seconds=350)).isoformat()},
        "dailyBar": {"c": 182.50, "v": 1500000}
    }

    res = DataValidator.validate_quote(
        quote_data,
        "AAPL",
        market_status="OPEN",
        max_age_seconds=120,
        now=now_utc
    )

    assert res["is_valid"] is False
    assert res["freshness"] == "STALE"
    assert res["category"] == "STALE"
    assert res["is_live_executable"] is False
    assert "exceeds threshold" in res["error_reason"]


def test_missing_quote():
    # None quote
    res_none = DataValidator.validate_quote(None, "MSFT", market_status="OPEN")
    assert res_none["is_valid"] is False
    assert res_none["freshness"] == "INVALID"
    assert res_none["category"] == "MISSING"
    assert res_none["is_live_executable"] is False
    assert "No snapshot quote" in res_none["error_reason"]

    # Empty dictionary
    res_empty = DataValidator.validate_quote({}, "MSFT", market_status="OPEN")
    assert res_empty["is_valid"] is False
    assert res_empty["category"] == "MISSING"


def test_zero_and_negative_prices():
    # Zero price
    res_zero = DataValidator.validate_quote({"price": 0.0}, "NVDA", market_status="OPEN")
    assert res_zero["is_valid"] is False
    assert res_zero["category"] == "INVALID"
    assert "Non-positive price" in res_zero["error_reason"]

    # Negative price
    res_neg = DataValidator.validate_quote({"price": -45.20}, "NVDA", market_status="OPEN")
    assert res_neg["is_valid"] is False
    assert res_neg["category"] == "INVALID"
    assert "Non-positive price" in res_neg["error_reason"]


def test_non_finite_prices():
    res_nan = DataValidator.validate_quote({"price": float("nan")}, "NVDA")
    assert res_nan["is_valid"] is False
    assert res_nan["category"] == "INVALID"

    res_inf = DataValidator.validate_quote({"price": float("inf")}, "NVDA")
    assert res_inf["is_valid"] is False
    assert res_inf["category"] == "INVALID"


def test_invalid_and_future_timestamp():
    now_utc = datetime(2026, 6, 10, 15, 0, tzinfo=timezone.utc)
    # Timestamp 10 minutes into the future
    future_data = {
        "latestTrade": {"p": 150.0, "t": (now_utc + timedelta(minutes=10)).isoformat()}
    }

    res = DataValidator.validate_quote(future_data, "AMD", market_status="OPEN", now=now_utc)
    assert res["is_valid"] is False
    assert res["category"] == "INVALID"
    assert "Future quote timestamp" in res["error_reason"]


def test_delayed_quote_handling():
    now_utc = datetime(2026, 6, 10, 15, 0, tzinfo=timezone.utc)
    quote_data = {
        "latestTrade": {"p": 120.0, "t": (now_utc - timedelta(minutes=15)).isoformat()}
    }

    res = DataValidator.validate_quote(
        quote_data,
        "INTC",
        market_status="OPEN",
        is_delayed_feed=True,
        now=now_utc
    )

    assert res["is_valid"] is True
    assert res["freshness"] == "DELAYED"
    assert res["is_live_executable"] is False
    assert "delayed" in res["execution_blocked_reason"].lower()


def test_last_available_quote_market_closed():
    now_utc = datetime(2026, 6, 10, 23, 0, tzinfo=timezone.utc)  # Market CLOSED
    quote_data = {
        "latestTrade": {"p": 250.0, "t": "2026-06-10T20:00:00Z"},
        "dailyBar": {"o": 245.0, "h": 252.0, "l": 244.0, "c": 250.0, "v": 2500000}
    }

    res = DataValidator.validate_quote(
        quote_data,
        "TSLA",
        market_status="CLOSED",
        now=now_utc
    )

    # Valid for historical scanning & candidate analysis!
    assert res["is_valid"] is True
    assert res["freshness"] == "LAST_AVAILABLE"
    assert res["category"] == "VALID"
    # But strictly prohibited from live order execution!
    assert res["is_live_executable"] is False
    assert "CLOSED" in res["execution_blocked_reason"]


def test_provider_errors_vs_symbol_resolution_failures():
    # 1. Symbol Resolution Failure (no_such_symbol)
    res_sym = DataValidator.validate_quote(
        {"error": "Quote error (NASDAQ:EMPTY_SYM): no_such_symbol"},
        "EMPTY_SYM"
    )
    assert res_sym["is_valid"] is False
    assert res_sym["category"] == "SYMBOL_RESOLUTION_FAILURE"
    assert "resolution failed" in res_sym["error_reason"]

    # 2. Provider Error (Bridge 502 / timeout)
    res_prov = DataValidator.validate_quote(
        {"error": "502 Bad Gateway: upstream timeout"},
        "AAPL"
    )
    assert res_prov["is_valid"] is False
    assert res_prov["category"] == "PROVIDER_ERROR"
    assert "Provider quote error" in res_prov["error_reason"]
