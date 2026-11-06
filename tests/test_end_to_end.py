import asyncio
import pytest
from datetime import datetime, timezone
from backend.database import init_db, get_db_connection
from backend.strategy.engine import StrategyEngine
from backend.signals import SignalManager
from backend.execution_bridge import bridge
from backend.monitor import monitor
from tests.test_strategy import make_candle

def test_full_pipeline_simulation():
    async def run_pipeline():
        init_db()
        conn = get_db_connection()
        try:
            conn.execute("DELETE FROM positions WHERE symbol = 'NVDA'")
            conn.execute("DELETE FROM orders WHERE trade_id IN (SELECT id FROM trades WHERE symbol = 'NVDA')")
            conn.execute("DELETE FROM trades WHERE symbol = 'NVDA'")
            conn.execute("DELETE FROM signals WHERE symbol = 'NVDA'")
            conn.commit()
        finally:
            conn.close()

        # 1. Generate Synthetic Multi-Timeframe Candles
        # 1H BOS
        candles_1h = [
            make_candle(105, 110, 100, 105, idx=0),
            make_candle(105, 115, 103, 112, idx=1),
            make_candle(112, 120, 110, 118, idx=2),
            make_candle(118, 130, 115, 125, idx=3),
            make_candle(125, 150, 120, 145, idx=4), # 1H Swing High = 150
            make_candle(145, 140, 135, 138, idx=5),
            make_candle(138, 135, 125, 128, idx=6),
            make_candle(128, 128, 100, 102, idx=7), # 1H Swing Low = 100
            make_candle(102, 115, 105, 112, idx=8),
            make_candle(112, 125, 110, 122, idx=9),
            make_candle(122, 140, 120, 138, idx=10),
            make_candle(138, 160, 135, 155, idx=11) # BOS Breakout
        ]

        # 15M Demand Zone
        candles_15m = [make_candle(100, 103, 99, 102, idx=i) for i in range(10)]
        candles_15m.append(make_candle(115, 116, 112, 113, idx=10)) # Bearish
        candles_15m.append(make_candle(113, 126, 113, 125, idx=11)) # Displacement
        candles_15m.append(make_candle(124, 124, 114, 118, idx=12)) # Return to zone

        # 5M Bullish Entry Confirmation
        candles_5m = [make_candle(110 + (i*0.1), 111 + (i*0.1), 109 + (i*0.1), 110.5 + (i*0.1), idx=i) for i in range(35)]
        candles_5m[-2] = make_candle(116, 117, 112, 113, idx=33)
        candles_5m[-1] = make_candle(113, 120, 112.5, 118, v=6000, idx=34)

        # 2. Strategy Engine Evaluation
        engine = StrategyEngine(min_score=60.0, min_rr=2.0)
        analysis = engine.analyze_symbol("NVDA", candles_1h, candles_15m, candles_5m, configured_qty=2.0)
        
        assert analysis["status"] == "QUALIFIED"
        assert analysis["signal"] is not None
        sig = analysis["signal"]
        assert sig["symbol"] == "NVDA"
        assert sig["entry_price"] == 118.00
        assert sig["quantity"] == 2.0
        assert sig["risk_reward"] >= 2.0

        # 3. Create Signal in Database
        created_sig = SignalManager.create_signal(sig)
        assert created_sig is not None

        # Verify duplicate prevention on same zone
        dup_sig = SignalManager.create_signal(sig)
        assert dup_sig is None

        # 4. Simulate Bridge Order Dispatch
        # Mock extension state as connected to Paper Trading
        bridge.update_status_from_extension({
            "tv_tab_detected": True,
            "tv_login_detected": True,
            "paper_trading_connected": True,
            "paper_trading_account_verified": True,
            "current_symbol": "NVDA",
            "broker_name": "Paper Trading by TradingView"
        })

        dispatch_res = await bridge.dispatch_signal_to_extension(created_sig)
        assert dispatch_res["success"] is True
        assert dispatch_res["status"] == "SENT_TO_EXTENSION"

        # 5. Simulate Extension Order Execution Confirmation from TradingView
        fill_price = 118.10
        bridge.handle_execution_confirmation({
            "signal_id": created_sig["signal_id"],
            "symbol": "NVDA",
            "success": True,
            "executed_price": fill_price,
            "tv_order_id": "TV-NVDA-12345"
        })

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM positions WHERE symbol = 'NVDA'")
        pos_row = cursor.fetchone()
        assert pos_row is not None
        assert pos_row["entry_price"] == fill_price
        assert pos_row["quantity"] == 2.0

        # 6. Simulate Real-time Position Tracking Sync
        monitor.process_tv_positions_sync([{
            "symbol": "NVDA",
            "quantity": 2.0,
            "avg_price": fill_price,
            "current_price": 130.00,
            "unrealized_pnl": 23.80,
            "stop_loss": created_sig["stop_loss"],
            "take_profit": created_sig["take_profit"]
        }])

        cursor.execute("SELECT unrealized_pnl FROM positions WHERE symbol = 'NVDA'")
        assert cursor.fetchone()["unrealized_pnl"] == 23.80

        # 7. Simulate Trade Exit via Take Profit Hit
        exit_price = 150.00
        monitor.process_trade_closure_report({
            "symbol": "NVDA",
            "exit_price": exit_price,
            "exit_reason": "TAKE_PROFIT",
            "gross_pnl": (exit_price - fill_price) * 2.0,
            "trading_fees": 0.0,
            "quantity": 2.0,
            "closed_at": datetime.now(timezone.utc).isoformat()
        })

        # Verify positions table cleared for NVDA
        cursor.execute("SELECT * FROM positions WHERE symbol = 'NVDA'")
        assert cursor.fetchone() is None

        # Verify trade marked CLOSED with realized P&L
        cursor.execute("SELECT * FROM trades WHERE symbol = 'NVDA' ORDER BY created_at DESC LIMIT 1")
        closed_trade = cursor.fetchone()
        assert closed_trade["status"] == "CLOSED"
        assert closed_trade["exit_reason"] == "TAKE_PROFIT"
        assert closed_trade["net_pnl"] == (exit_price - fill_price) * 2.0
        conn.close()

    asyncio.run(run_pipeline())

