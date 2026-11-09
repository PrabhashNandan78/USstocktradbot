import pytest
from starlette.testclient import TestClient
from backend.main import app
from backend.database import init_db, get_db_connection

client = TestClient(app)

def setup_function():
    init_db()
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM positions")
        c.execute("DELETE FROM orders")
        c.execute("DELETE FROM trades")
        c.execute("DELETE FROM signals")
        conn.commit()
    finally:
        if conn:
            conn.close()

def test_trade_history_source_filtering():
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        # Insert 1 test simulation trade
        c.execute("""
            INSERT INTO trades (
                id, symbol, direction, requested_entry, executed_entry, actual_exit_price,
                quantity, stop_loss, take_profit, status, trade_source, net_pnl, created_at, closed_at
            ) VALUES (
                'TRD-SIM-1', 'SIM_AAPL', 'BUY', 100.0, 100.0, 105.0,
                1.0, 95.0, 110.0, 'CLOSED', 'TEST_SIMULATION', 5.0, '2026-11-06T10:00:00Z', '2026-11-06T10:05:00Z'
            )
        """)
        # Insert 1 verified Paper Trading trade
        c.execute("""
            INSERT INTO trades (
                id, symbol, direction, requested_entry, executed_entry, actual_exit_price,
                quantity, stop_loss, take_profit, status, trade_source, net_pnl, created_at, closed_at
            ) VALUES (
                'TRD-TV-1', 'MSFT', 'BUY', 300.0, 300.0, 310.0,
                1.0, 290.0, 320.0, 'CLOSED', 'TRADINGVIEW_PAPER', 10.0, '2026-11-06T11:00:00Z', '2026-11-06T11:30:00Z'
            )
        """)
        conn.commit()
    finally:
        if conn:
            conn.close()

    # Query Paper Trading (default)
    res_paper = client.get("/api/trades/history?source=TRADINGVIEW_PAPER")
    assert res_paper.status_code == 200
    paper_trades = res_paper.json()
    assert len(paper_trades) == 1
    assert paper_trades[0]["id"] == "TRD-TV-1"
    assert paper_trades[0]["trade_source"] == "TRADINGVIEW_PAPER"

    # Query Simulation
    res_sim = client.get("/api/trades/history?source=TEST_SIMULATION")
    assert res_sim.status_code == 200
    sim_trades = res_sim.json()
    assert len(sim_trades) == 1
    assert sim_trades[0]["id"] == "TRD-SIM-1"
    assert sim_trades[0]["trade_source"] == "TEST_SIMULATION"

    # Query All
    res_all = client.get("/api/trades/history?source=ALL")
    assert res_all.status_code == 200
    assert len(res_all.json()) == 2

def test_performance_analytics_source_isolation_and_empty_state():
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        # Insert only simulation trades
        c.execute("""
            INSERT INTO trades (
                id, symbol, direction, requested_entry, executed_entry, actual_exit_price,
                quantity, stop_loss, take_profit, status, trade_source, net_pnl, gross_pnl, created_at, closed_at
            ) VALUES (
                'TRD-SIM-WIN', 'SIM_AAPL', 'BUY', 100.0, 100.0, 105.0,
                1.0, 95.0, 110.0, 'CLOSED', 'TEST_SIMULATION', 5.0, 5.0, '2026-11-06T10:00:00Z', '2026-11-06T10:05:00Z'
            )
        """)
        conn.commit()
    finally:
        if conn:
            conn.close()

    # Verified Paper Trading analytics must be EMPTY (0 trades)
    res_paper = client.get("/api/trades/analytics?source=TRADINGVIEW_PAPER")
    assert res_paper.status_code == 200
    paper_an = res_paper.json()
    assert paper_an["total_trades"] == 0
    assert paper_an["win_rate_pct"] == 0.0
    assert paper_an["profit_factor"] == "N/A"
    assert "No verified TradingView Paper Trading history available" in paper_an["message"]

    # Simulation analytics should report the 1 simulation trade
    res_sim = client.get("/api/trades/analytics?source=TEST_SIMULATION")
    assert res_sim.status_code == 200
    sim_an = res_sim.json()
    assert sim_an["total_trades"] == 1
    assert sim_an["winning_trades"] == 1
    # Since 0 losses, profit factor should be "N/A", not dollar amount!
    assert sim_an["profit_factor"] == "N/A"
    assert sim_an["net_pnl"] == 5.0
