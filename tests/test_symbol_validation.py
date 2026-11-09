import pytest
import asyncio
from backend.execution_bridge import bridge
from backend.database import init_db, get_db_connection
from backend.signals import SignalManager

def setup_function():
    init_db()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM positions")
    c.execute("DELETE FROM orders")
    c.execute("DELETE FROM trades")
    c.execute("DELETE FROM signals")
    conn.commit()
    conn.close()

@pytest.mark.anyio
async def test_symbol_validation_matching():
    # Configure bridge in PAPER_TRADING_CONNECTED state
    bridge.extension_state["connected"] = True
    bridge.extension_state["account_state"] = "PAPER_TRADING_CONNECTED"
    bridge.extension_state["paper_trading_connected"] = True
    bridge.extension_state["current_symbol"] = "NASDAQ:AAPL"

    signal_data = {
        "signal_id": "SIG-VALID-AAPL",
        "symbol": "AAPL",
        "direction": "BUY",
        "timestamp": "2026-11-06T12:00:00Z",
        "entry_price": 150.0,
        "stop_loss": 145.0,
        "take_profit": 160.0,
        "quantity": 1.0,
        "signal_score": 85.0,
        "risk_reward": 2.0,
        "demand_zone_low": 144.0,
        "demand_zone_high": 146.0,
        "timeframe": "5M"
    }
    SignalManager.create_signal(signal_data)

    res = await bridge.dispatch_signal_to_extension(signal_data)
    assert res["success"] is True
    assert res["status"] == "SENT_TO_EXTENSION"

@pytest.mark.anyio
async def test_symbol_validation_mismatch_rejected():
    bridge.extension_state["connected"] = True
    bridge.extension_state["account_state"] = "PAPER_TRADING_CONNECTED"
    bridge.extension_state["paper_trading_connected"] = True
    # Chart is on NVDA, but signal is for AAPL
    bridge.extension_state["current_symbol"] = "NASDAQ:NVDA"

    signal_data = {
        "signal_id": "SIG-MISMATCH-AAPL",
        "symbol": "AAPL",
        "direction": "BUY",
        "timestamp": "2026-11-06T12:00:00Z",
        "entry_price": 150.0,
        "stop_loss": 145.0,
        "take_profit": 160.0,
        "quantity": 1.0,
        "signal_score": 85.0,
        "risk_reward": 2.0,
        "demand_zone_low": 144.0,
        "demand_zone_high": 146.0,
        "timeframe": "5M"
    }
    SignalManager.create_signal(signal_data)

    res = await bridge.dispatch_signal_to_extension(signal_data)
    assert res["success"] is False
    assert res["status"] == "SYMBOL_MISMATCH"
    assert "Execution blocked: TradingView symbol 'NVDA' does not match signal symbol 'AAPL'" in res["message"]

    # Verify signal status in database is EXECUTION_FAILED
    sig = SignalManager.get_signal("SIG-MISMATCH-AAPL")
    assert sig["status"] == "EXECUTION_FAILED"

@pytest.mark.anyio
async def test_symbol_validation_foreign_exchange_rejected():
    bridge.extension_state["connected"] = True
    bridge.extension_state["account_state"] = "PAPER_TRADING_CONNECTED"
    bridge.extension_state["paper_trading_connected"] = True
    # Non-US equity exchange on chart
    bridge.extension_state["current_symbol"] = "NSE:NIFTY1!"

    signal_data = {
        "signal_id": "SIG-FOREIGN-AAPL",
        "symbol": "AAPL",
        "direction": "BUY",
        "timestamp": "2026-11-06T12:00:00Z",
        "entry_price": 150.0,
        "stop_loss": 145.0,
        "take_profit": 160.0,
        "quantity": 1.0,
        "signal_score": 85.0,
        "risk_reward": 2.0,
        "demand_zone_low": 144.0,
        "demand_zone_high": 146.0,
        "timeframe": "5M"
    }
    SignalManager.create_signal(signal_data)

    res = await bridge.dispatch_signal_to_extension(signal_data)
    assert res["success"] is False
    assert res["status"] == "SYMBOL_MISMATCH"
    assert "Execution blocked: TradingView chart exchange 'NSE' is not a US equity exchange" in res["message"]
