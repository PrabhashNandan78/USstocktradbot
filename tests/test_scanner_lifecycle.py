"""
Tests for Scanner Lifecycle, Universe Discovery, and Batch Quote Resilience.
Verifies:
1. Scanner start/stop async lifecycle and event loop integration.
2. Idempotent start and clean task cancellation on stop.
3. Restart after stop.
4. Automatic universe discovery when watchlist is empty.
5. Absolute prevention of placeholder symbols entering production universe.
6. Deduplication of candidate symbols.
7. Batch quotes resilience when bad symbols are present.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from backend.main import app
from backend.scanner import StockScanner, _is_valid_production_symbol
from backend.tradingview_client import TradingViewClient, is_valid_ticker, DEFAULT_US_UNIVERSE
from backend.database import init_db, get_config_val, set_config_val


@pytest.fixture(autouse=True)
def clean_db():
    init_db()
    # Ensure custom watchlist starts clean
    original_watchlist = get_config_val("scanner_custom_watchlist", [])
    set_config_val("scanner_custom_watchlist", [])
    yield
    set_config_val("scanner_custom_watchlist", original_watchlist)


@pytest.mark.anyio
async def test_scanner_start_stop_lifecycle():
    scanner = StockScanner()
    # Mock scan_once to avoid heavy network operations during rapid lifecycle test
    scanner.scan_once = MagicMock(return_value={"status": "COMPLETED"})

    assert scanner.is_running is False
    assert scanner._task is None

    # 1. Start
    start_res = await scanner.start()
    assert start_res["status"] == "RUNNING"
    assert scanner.is_running is True
    assert scanner._task is not None
    assert not scanner._task.done()

    # 2. Idempotent start
    dup_res = await scanner.start()
    assert dup_res["status"] == "ALREADY_RUNNING"
    assert scanner.is_running is True

    # 3. Stop
    stop_res = await scanner.stop()
    assert stop_res["status"] == "STOPPED"
    assert scanner.is_running is False
    assert scanner._task is None

    # 4. Restart after stop
    restart_res = await scanner.start()
    assert restart_res["status"] == "RUNNING"
    assert scanner.is_running is True
    assert scanner._task is not None

    # Final cleanup
    await scanner.stop()
    assert scanner.is_running is False


def test_scanner_api_start_stop_endpoints():
    from backend.api.routes_scanner import scanner_instance
    with patch.object(scanner_instance, "scan_once", return_value={"status": "COMPLETED"}):
        client = TestClient(app)

        # Status check
        status_res = client.get("/api/scanner/status")
        assert status_res.status_code == 200

        # Start scanner
        start_res = client.post("/api/scanner/start")
        assert start_res.status_code == 200
        assert start_res.json()["status"] in ("RUNNING", "ALREADY_RUNNING")

        # Second start is idempotent
        second_start = client.post("/api/scanner/start")
        assert second_start.status_code == 200
        assert second_start.json()["status"] == "ALREADY_RUNNING"

        # Status reflects running
        status_res2 = client.get("/api/scanner/status")
        assert status_res2.status_code == 200
        assert status_res2.json()["is_running"] is True

        # Stop scanner
        stop_res = client.post("/api/scanner/stop")
        assert stop_res.status_code == 200
        assert stop_res.json()["status"] == "STOPPED"

        # Status reflects stopped
        status_res3 = client.get("/api/scanner/status")
        assert status_res3.status_code == 200
        assert status_res3.json()["is_running"] is False


def test_automatic_universe_discovery_when_watchlist_empty():
    scanner = StockScanner()
    cfg = scanner.get_config()
    assert cfg["custom_watchlist"] == []

    # Mock client to verify automatic discovery triggers
    mock_client = MagicMock()
    mock_client.is_configured.return_value = True
    mock_client.fetch_active_us_equities.return_value = ["AAPL", "MSFT", "NVDA", "AMZN"]
    mock_client.get_snapshots.return_value = {
        "AAPL": {"price": 180.0, "dailyBar": {"c": 180.0, "v": 500000}},
        "MSFT": {"price": 420.0, "dailyBar": {"c": 420.0, "v": 400000}},
        "NVDA": {"price": 120.0, "dailyBar": {"c": 120.0, "v": 600000}},
        "AMZN": {"price": 190.0, "dailyBar": {"c": 190.0, "v": 300000}}
    }
    mock_client.get_bars.return_value = []
    scanner.client = mock_client

    res = scanner.scan_once()
    assert mock_client.fetch_active_us_equities.called
    assert res["status"] in ("IDLE", "RUNNING")
    assert res["accounting"]["universe_candidates_count"] == 4


def test_symbol_validation_prevents_placeholders():
    # Valid tickers
    assert is_valid_ticker("AAPL") is True
    assert is_valid_ticker("BRK.B") is True
    assert is_valid_ticker("BF-B") is True
    assert _is_valid_production_symbol("MSFT") is True

    # Placeholder / dummy symbols must be strictly rejected
    assert is_valid_ticker("EMPTY_SYM") is False
    assert is_valid_ticker("ZERO_PRICE_SYM") is False
    assert is_valid_ticker("TEST") is False
    assert is_valid_ticker("FAKE") is False
    assert is_valid_ticker("DUMMY") is False
    assert _is_valid_production_symbol("EMPTY_SYM") is False
    assert _is_valid_production_symbol("ZERO_PRICE_SYM") is False

    # Malformed strings
    assert is_valid_ticker("") is False
    assert is_valid_ticker("INVALID_LONG_TICKER") is False
    assert is_valid_ticker("12345") is False


def test_candidate_symbols_deduplication():
    scanner = StockScanner()
    cfg = scanner.get_config()
    cfg["custom_watchlist"] = ["AAPL", "MSFT", "AAPL", "NVDA", "MSFT"]
    scanner.get_config = lambda: dict(cfg)

    mock_client = MagicMock()
    mock_client.is_configured.return_value = False
    scanner.client = mock_client

    res = scanner.scan_once()
    # 5 items with duplicates should deduplicate to 3 unique candidates
    assert res["accounting"]["universe_candidates_count"] == 3


def test_resilient_batch_quotes_with_bad_symbol():
    client = TradingViewClient()
    if not client.is_configured():
        pytest.skip("TradingView bridge service is offline")

    # Pass a batch containing both valid symbols and an invalid dummy symbol
    quotes = client.get_snapshots(["AAPL", "EMPTY_SYM", "MSFT"])
    assert isinstance(quotes, dict)
    # Valid symbols must be retrieved successfully
    assert "AAPL" in quotes or "MSFT" in quotes
    # The call did not crash or raise an unhandled 502
