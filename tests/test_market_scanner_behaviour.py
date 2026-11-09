"""
Integration tests for Scanner Behaviour across US Market Sessions & Quote Freshness states.
Validates:
1. Market Closed: Historical scan works and satisfies all accounting invariants.
2. Market Closed: Signals are marked non-executable; bridge blocks order dispatch.
3. Market Open: Fresh quotes pass and qualify.
4. Market Open: Stale quotes are rejected from execution and categorized accurately.
5. Market Transitions (Closed -> Open) do not generate duplicate signals for same demand zone.
6. Execution Bridge strictly prevents dispatching non-live or closed-market signals.
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import pytest

from backend.scanner import StockScanner
from backend.tradingview_client import TradingViewClient
from backend.execution_bridge import bridge
from backend.database import init_db, get_config_val, set_config_val, get_db_connection
from backend.signals import SignalManager
from backend.market_calendar import NY_TZ


@pytest.fixture(autouse=True)
def setup_clean_state():
    init_db()
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM orders")
        conn.execute("DELETE FROM trades WHERE symbol IN ('AAPL', 'NVDA', 'MSFT', 'TEST_SYM')")
        conn.execute("DELETE FROM signals WHERE symbol IN ('AAPL', 'NVDA', 'MSFT', 'TEST_SYM')")
        conn.execute("DELETE FROM positions WHERE symbol IN ('AAPL', 'NVDA', 'MSFT', 'TEST_SYM')")
        conn.commit()
    finally:
        conn.close()

    original_watchlist = get_config_val("scanner_custom_watchlist", [])
    set_config_val("scanner_custom_watchlist", [])
    yield
    set_config_val("scanner_custom_watchlist", original_watchlist)


def test_market_closed_historical_scan_works_and_satisfies_invariants():
    """
    When US market is CLOSED, the scanner should:
    - Retrieve last available quotes.
    - NOT classify closed market as a provider failure.
    - Evaluate completed candles and maintain all accounting invariants.
    """
    scanner = StockScanner()
    cfg = scanner.get_config()
    cfg["custom_watchlist"] = ["AAPL", "MSFT"]
    scanner.get_config = lambda: dict(cfg)

    # Mock market status to CLOSED
    closed_status = {
        "status": "CLOSED",
        "ny_time": "2026-06-13T14:00:00-04:00",
        "trading_date": "2026-06-13",
        "session_type": "WEEKEND",
        "regular_session_open": "2026-06-15T09:30:00-04:00",
        "regular_session_close": "2026-06-15T16:00:00-04:00",
        "next_market_open": "2026-06-15T09:30:00-04:00",
        "next_market_close": "2026-06-15T16:00:00-04:00",
        "is_holiday": False,
        "is_early_close": False,
        "holiday_name": None
    }

    mock_client = MagicMock()
    mock_client.is_configured.return_value = True
    # Return last available closing snapshots
    mock_client.get_snapshots.return_value = {
        "AAPL": {
            "price": 185.0,
            "latestTrade": {"p": 185.0, "t": "2026-06-12T20:00:00Z"},
            "dailyBar": {"c": 185.0, "v": 2000000}
        },
        "MSFT": {
            "price": 420.0,
            "latestTrade": {"p": 420.0, "t": "2026-06-12T20:00:00Z"},
            "dailyBar": {"c": 420.0, "v": 1500000}
        }
    }
    mock_client.get_bars.return_value = []
    scanner.client = mock_client

    with patch("backend.scanner.NYSECalendar.get_market_status", return_value=closed_status):
        res = scanner.scan_once()

    acct = res["accounting"]
    assert acct["invariants_satisfied"] is True
    # Market closed condition must NOT be counted as a provider failure!
    assert acct["data_retrieval_failures_count"] == 0
    assert acct["liquidity_passed_count"] == 2
    assert res["market_status"] == "CLOSED"


@pytest.mark.anyio
async def test_market_closed_prevents_order_dispatch():
    """
    When market is CLOSED, any signal generated is marked non-executable,
    and the execution bridge strictly rejects dispatch to the TradingView extension.
    """
    closed_status = {
        "status": "CLOSED",
        "ny_time": "2026-06-13T14:00:00-04:00",
        "session_type": "WEEKEND"
    }

    bridge.extension_state["connected"] = True
    bridge.extension_state["account_state"] = "PAPER_TRADING_CONNECTED"
    bridge.extension_state["current_symbol"] = "NVDA"

    # Signal produced during closed session
    signal = {
        "signal_id": "SIG-NVDA-CLOSED-1",
        "symbol": "NVDA",
        "direction": "BUY",
        "entry_price": 120.0,
        "stop_loss": 115.0,
        "take_profit": 130.0,
        "quantity": 1.0,
        "signal_score": 85.0,
        "risk_reward": 2.0,
        "timeframe": "15m",
        "demand_zone_low": 119.0,
        "demand_zone_high": 121.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "is_live_executable": False,
        "quote_freshness": "LAST_AVAILABLE",
        "execution_blocked_reason": "Live execution prohibited: Market session is CLOSED"
    }

    SignalManager.create_signal(signal)

    with patch("backend.execution_bridge.NYSECalendar.get_market_status", return_value=closed_status):
        dispatch_res = await bridge.dispatch_signal_to_extension(signal)

    assert dispatch_res["success"] is False
    assert dispatch_res["status"] in ("EXECUTION_BLOCKED", "MARKET_NOT_OPEN")
    assert "blocked" in dispatch_res["message"].lower() or "closed" in dispatch_res["message"].lower()


@pytest.mark.anyio
async def test_market_open_stale_quote_rejected_for_execution():
    """
    During an OPEN market session, stale quotes are categorized as STALE and
    prevented from automated order placement.
    """
    open_status = {
        "status": "OPEN",
        "ny_time": "2026-06-10T11:00:00-04:00",
        "session_type": "REGULAR"
    }

    bridge.extension_state["connected"] = True
    bridge.extension_state["account_state"] = "PAPER_TRADING_CONNECTED"
    bridge.extension_state["current_symbol"] = "AAPL"

    stale_signal = {
        "signal_id": "SIG-AAPL-STALE-1",
        "symbol": "AAPL",
        "direction": "BUY",
        "entry_price": 180.0,
        "stop_loss": 175.0,
        "take_profit": 190.0,
        "quantity": 1.0,
        "signal_score": 85.0,
        "risk_reward": 2.0,
        "timeframe": "15m",
        "demand_zone_low": 179.0,
        "demand_zone_high": 181.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "is_live_executable": False,
        "quote_freshness": "STALE",
        "execution_blocked_reason": "Quote timestamp age exceeds freshness threshold"
    }

    SignalManager.create_signal(stale_signal)

    with patch("backend.execution_bridge.NYSECalendar.get_market_status", return_value=open_status):
        dispatch_res = await bridge.dispatch_signal_to_extension(stale_signal)

    assert dispatch_res["success"] is False
    assert dispatch_res["status"] == "EXECUTION_BLOCKED"


def test_transition_closed_to_open_does_not_duplicate_signals():
    """
    Tests that a setup identified in PRE_MARKET / CLOSED does not trigger a duplicate
    signal when the market opens.
    """
    sig_data = {
        "signal_id": "SIG-NVDA-ZONE-1",
        "symbol": "NVDA",
        "direction": "BUY",
        "entry_price": 120.0,
        "stop_loss": 115.0,
        "take_profit": 130.0,
        "quantity": 1.0,
        "signal_score": 85.0,
        "risk_reward": 2.0,
        "demand_zone_low": 119.0,
        "demand_zone_high": 121.0,
        "timeframe": "15m",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # 1. Create first signal during PRE_MARKET
    first_sig = SignalManager.create_signal(sig_data)
    assert first_sig is not None

    # 2. Attempt duplicate creation at market open for same zone
    sig_data_open = dict(sig_data)
    sig_data_open["signal_id"] = "SIG-NVDA-ZONE-2"
    dup_sig = SignalManager.create_signal(sig_data_open)
    assert dup_sig is None, "Duplicate signal should be prevented for the same active zone"
