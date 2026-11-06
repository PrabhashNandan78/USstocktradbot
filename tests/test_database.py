import pytest
import os
from backend.database import (
    init_db, get_db_connection, set_config_val, get_config_val, log_system_event
)
from backend.signals import SignalManager

def test_database_init_and_config():
    init_db()
    set_config_val("test_key", "test_value")
    assert get_config_val("test_key") == "test_value"

    set_config_val("test_dict", {"foo": "bar", "num": 42})
    val = get_config_val("test_dict")
    assert isinstance(val, dict)
    assert val["num"] == 42

def test_signal_manager_crud_and_deduplication():
    init_db()
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM positions")
        conn.execute("DELETE FROM orders")
        conn.execute("DELETE FROM trades WHERE signal_id LIKE 'SIG-TEST%' OR symbol LIKE 'AAPL_TEST%'")
        conn.execute("DELETE FROM signals WHERE id LIKE 'SIG-TEST%' OR symbol LIKE 'AAPL_TEST%'")
        conn.commit()
    finally:
        conn.close()

    sig_payload = {
        "signal_id": "SIG-TEST-001",
        "symbol": "AAPL_TEST",
        "direction": "BUY",
        "timestamp": "2026-11-06T20:00:00Z",
        "entry_price": 150.00,
        "stop_loss": 145.00,
        "take_profit": 165.00,
        "quantity": 1.0,
        "signal_score": 75.0,
        "risk_reward": 3.0,
        "demand_zone_low": 146.00,
        "demand_zone_high": 148.00,
        "timeframe": "5M",
        "score_breakdown": {"candlestick": 25.0, "momentum": 20.0, "trend": 20.0, "volume": 10.0, "price_action": 0.0},
        "details": {"note": "test"}
    }

    created = SignalManager.create_signal(sig_payload)
    assert created is not None
    assert created["signal_id"] == "SIG-TEST-001"

    # Attempt to create duplicate signal with same symbol and demand zone
    duplicate_payload = sig_payload.copy()
    duplicate_payload["signal_id"] = "SIG-TEST-002"
    duplicate_res = SignalManager.create_signal(duplicate_payload)
    assert duplicate_res is None  # Correctly blocked as duplicate!

    # Verify retrieval
    retrieved = SignalManager.get_signal("SIG-TEST-001")
    assert retrieved is not None
    assert retrieved["symbol"] == "AAPL_TEST"
    assert retrieved["entry_price"] == 150.00

    # Verify status update
    SignalManager.update_signal_status("SIG-TEST-001", "SENT_TO_EXTENSION")
    updated = SignalManager.get_signal("SIG-TEST-001")
    assert updated["status"] == "SENT_TO_EXTENSION"
