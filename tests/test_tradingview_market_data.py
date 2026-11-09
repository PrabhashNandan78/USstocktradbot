"""
Unit and Integration Tests for TradingView Market Data Integration & DataValidator.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from backend.data_validator import DataValidator
from backend.tradingview_client import TradingViewClient, DEFAULT_US_UNIVERSE
from backend.database import init_db


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def create_sample_bars(base_price=150.0, count=20, interval_seconds=300):
    """Helper to generate structurally valid OHLCV bars."""
    now_epoch = int(datetime.now(timezone.utc).timestamp()) - (count * interval_seconds)
    bars = []
    p = base_price
    for i in range(count):
        t_epoch = now_epoch + (i * interval_seconds)
        iso_ts = datetime.fromtimestamp(t_epoch, tz=timezone.utc).isoformat()
        o = round(p, 2)
        h = round(o + 0.50, 2)
        l = round(o - 0.50, 2)
        c = round(o + 0.10, 2)
        v = 15000 + (i * 100)
        bars.append({
            "timestamp": iso_ts,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v,
            "vwap": (h + l + c) / 3.0
        })
        p = c
    return bars


def test_validator_candle_structural_integrity():
    validator = DataValidator()

    # Valid bar
    valid_bar = {"open": 100.0, "high": 105.0, "low": 98.0, "close": 102.0, "volume": 5000}
    ok, errs = validator.validate_candle_structure(valid_bar)
    assert ok is True
    assert len(errs) == 0

    # Invariant violation: High < Open
    bad_h_o = {"open": 100.0, "high": 95.0, "low": 90.0, "close": 92.0, "volume": 5000}
    ok, errs = validator.validate_candle_structure(bad_h_o)
    assert ok is False
    assert any("High" in e and "Open" in e for e in errs)

    # Invariant violation: Low > Close
    bad_l_c = {"open": 100.0, "high": 105.0, "low": 103.0, "close": 101.0, "volume": 5000}
    ok, errs = validator.validate_candle_structure(bad_l_c)
    assert ok is False
    assert any("Low" in e and "Close" in e for e in errs)

    # Invariant violation: High < Low
    bad_h_l = {"open": 100.0, "high": 90.0, "low": 95.0, "close": 92.0, "volume": 5000}
    ok, errs = validator.validate_candle_structure(bad_h_l)
    assert ok is False

    # Negative volume
    bad_vol = {"open": 100.0, "high": 105.0, "low": 98.0, "close": 102.0, "volume": -100}
    ok, errs = validator.validate_candle_structure(bad_vol)
    assert ok is False
    assert any("Negative volume" in e for e in errs)

    # Negative price
    bad_price = {"open": -10.0, "high": 10.0, "low": -12.0, "close": 5.0, "volume": 100}
    ok, errs = validator.validate_candle_structure(bad_price)
    assert ok is False
    assert any("Non-positive price" in e for e in errs)


def test_validator_chronological_ordering_and_duplicates():
    validator = DataValidator()
    base_bars = create_sample_bars(count=5, interval_seconds=300)

    # Valid series passes
    ok, errs, stats = validator.validate_bars_series(base_bars, "AAPL", "5m")
    assert ok is True
    assert stats["valid_bars"] == 5
    assert stats["duplicate_bars"] == 0
    assert stats["out_of_order_bars"] == 0

    # Duplicate timestamp injection
    dup_bars = list(base_bars)
    dup_bars[2] = dict(dup_bars[1])  # exact duplicate timestamp
    ok, errs, stats = validator.validate_bars_series(dup_bars, "AAPL", "5m")
    assert ok is False
    assert stats["duplicate_bars"] >= 1
    assert any("Duplicate timestamp" in e for e in errs)

    # Out-of-order timestamp injection
    rev_bars = list(base_bars)
    rev_bars[2], rev_bars[3] = rev_bars[3], rev_bars[2]
    ok, errs, stats = validator.validate_bars_series(rev_bars, "AAPL", "5m")
    assert ok is False
    assert stats["out_of_order_bars"] >= 1
    assert any("Out-of-order timestamp" in e for e in errs)


def test_validator_future_timestamp_detection():
    validator = DataValidator()
    far_future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    future_bars = [{
        "timestamp": far_future,
        "open": 100.0,
        "high": 105.0,
        "low": 98.0,
        "close": 102.0,
        "volume": 5000
    }]
    ok, errs, stats = validator.validate_bars_series(future_bars, "TSLA", "5m")
    assert ok is False
    assert stats["future_bars"] == 1
    assert any("Future timestamp" in e for e in errs)


def test_validator_quote_divergence_cross_check():
    validator = DataValidator()
    bars = create_sample_bars(base_price=100.0, count=5)

    # Quote matches within 1% -> Pass
    quote_close = {"price": 100.50}
    ok, errs = validator.validate_quote_consistency("NVDA", bars, quote_close, max_divergence_pct=0.05)
    assert ok is True
    assert len(errs) == 0

    # Quote diverges by 15% -> Reject
    quote_divergent = {"price": 120.0}
    ok, errs = validator.validate_quote_consistency("NVDA", bars, quote_divergent, max_divergence_pct=0.05)
    assert ok is False
    assert any("diverges from latest candle close" in e for e in errs)


def test_validator_indicator_mathematical_consistency():
    validator = DataValidator()
    bars = create_sample_bars(base_price=200.0, count=30)

    # Verify local indicator calculation
    res = validator.verify_indicators(bars)
    assert res["verified"] is True
    calc = res["calculated"]
    assert "ema_9" in calc
    assert "ema_20" in calc
    assert "atr_14" in calc
    assert calc["ema_9"] > 0
    assert calc["atr_14"] > 0

    # Test discrepancy detection against bad external indicator
    mismatch_res = validator.verify_indicators(bars, external_ema9=999.99)
    assert mismatch_res["verified"] is False
    assert any("EMA9 mismatch" in d for d in mismatch_res["discrepancies"])


def test_validation_report_generation():
    validator = DataValidator()
    bars_dict = {
        "AAPL": create_sample_bars(base_price=180.0, count=15),
        "MSFT": create_sample_bars(base_price=420.0, count=15),
        "NVDA": create_sample_bars(base_price=120.0, count=15),
        "TSLA": create_sample_bars(base_price=250.0, count=15)
    }
    quotes_dict = {
        "AAPL": {"price": bars_dict["AAPL"][-1]["close"]},
        "MSFT": {"price": bars_dict["MSFT"][-1]["close"]},
        "NVDA": {"price": bars_dict["NVDA"][-1]["close"]},
        "TSLA": {"price": bars_dict["TSLA"][-1]["close"]}
    }

    report = validator.generate_validation_report(
        requested_symbols=["AAPL", "MSFT", "NVDA", "TSLA"],
        received_bars=bars_dict,
        received_quotes=quotes_dict,
        latency_ms=45.2,
        timeframe="5m"
    )

    assert report["validation_passed"] is True
    assert report["total_symbols_requested"] == 4
    assert report["successful_subscriptions"] == 4
    assert report["candle_completeness_pct"] == 100.0
    assert report["invalid_record_count"] == 0
    assert report["feed_source"] == "TradingView Real-Time Consolidated Tape"
    assert "NYSE, NASDAQ, AMEX" in report["feed_coverage"]
    assert len(report["symbol_details"]) == 4


def test_tradingview_client_multi_timeframe_and_snapshots():
    client = TradingViewClient()
    # Test symbols
    symbols = ["AAPL", "MSFT", "NVDA", "TSLA"]

    # 1. Snapshots
    snapshots = client.get_snapshots(symbols)
    assert isinstance(snapshots, dict)
    assert len(snapshots) > 0
    for s in symbols:
        if s in snapshots:
            snap = snapshots[s]
            assert "price" in snap or "latestTrade" in snap
            assert "dailyBar" in snap

    # 2. Multi-Timeframe Bars (5M, 15M, 1H)
    for tf in ["5m", "15m", "1h"]:
        bars = client.get_bars("AAPL", timeframe=tf, limit=5)
        assert len(bars) > 0, f"Failed to retrieve bars for AAPL on timeframe {tf}"
        assert "close" in bars[0]
        assert "timestamp" in bars[0]
        assert "volume" in bars[0]

    # 3. Connection Test
    conn_res = client.test_connection()
    assert conn_res["success"] is True
    assert conn_res["status"] == "CONNECTED"
    assert conn_res["historical_candle_access"] is True
    assert conn_res["real_time_access"] is True
    assert conn_res["validation_report"]["validation_passed"] is True

