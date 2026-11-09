import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from backend.database import get_db_connection, log_system_event
from backend.telegram_bot import TelegramNotifier

logger = logging.getLogger(__name__)

class PositionMonitor:
    def __init__(self):
        self.telegram = TelegramNotifier()
        self._already_notified_closed_trades = set()

    def process_tv_positions_sync(self, tv_positions: List[Dict[str, Any]]):
        """
        Synchronizes positions table with active positions scraped from TradingView's Paper Trading panel.
        tv_positions format:
        [{
            'symbol': 'AAPL',
            'quantity': 1.0,
            'avg_price': 150.25,
            'current_price': 151.10,
            'unrealized_pnl': 0.85,
            'stop_loss': 148.00,
            'take_profit': 155.00
        }]
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()

            active_symbols = set()
            for p in tv_positions:
                sym = p.get("symbol")
                if not sym:
                    continue
                active_symbols.add(sym)
                
                # Find associated open trade
                cursor.execute("SELECT id FROM trades WHERE symbol = ? AND status = 'OPEN' ORDER BY created_at DESC LIMIT 1", (sym,))
                t_row = cursor.fetchone()
                if t_row:
                    trade_id = t_row["id"]
                else:
                    trade_id = f"TRD-{sym}-SYNC"
                    cursor.execute("""
                        INSERT OR IGNORE INTO trades (id, symbol, direction, requested_entry, executed_entry, quantity, stop_loss, take_profit, status, created_at, executed_at, trade_source)
                        VALUES (?, ?, 'BUY', ?, ?, ?, ?, ?, 'OPEN', ?, ?, 'TRADINGVIEW_PAPER')
                    """, (
                        trade_id,
                        sym,
                        float(p.get("avg_price", 0.0)),
                        float(p.get("avg_price", 0.0)),
                        float(p.get("quantity", 1.0)),
                        float(p.get("stop_loss", 0.0)),
                        float(p.get("take_profit", 0.0)),
                        now,
                        now
                    ))

                cursor.execute("""
                    INSERT INTO positions (symbol, trade_id, quantity, entry_price, current_price, unrealized_pnl, stop_loss, take_profit, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET
                        quantity = excluded.quantity,
                        entry_price = excluded.entry_price,
                        current_price = excluded.current_price,
                        unrealized_pnl = excluded.unrealized_pnl,
                        stop_loss = excluded.stop_loss,
                        take_profit = excluded.take_profit,
                        updated_at = excluded.updated_at
                """, (
                    sym,
                    trade_id,
                    float(p.get("quantity", 1.0)),
                    float(p.get("avg_price", 0.0)),
                    float(p.get("current_price", 0.0)),
                    float(p.get("unrealized_pnl", 0.0)),
                    float(p.get("stop_loss", 0.0)),
                    float(p.get("take_profit", 0.0)),
                    now
                ))

            # Check for open DB positions that no longer exist on TradingView -> Closed!
            cursor.execute("SELECT symbol, trade_id FROM positions")
            existing_db_positions = cursor.fetchall()
            for row in existing_db_positions:
                s = row["symbol"]
                trd_id = row["trade_id"]
                if s not in active_symbols:
                    # Position disappeared from TradingView positions table!
                    logger.info(f"Position {s} no longer in TV open positions list. Resolving closure...")
                    self._handle_position_closure_by_disappearance(cursor, s, trd_id, now)

            conn.commit()
        finally:
            conn.close()

    def process_trade_closure_report(self, closure_report: Dict[str, Any]):
        """
        Called when extension explicitly scrapes a closed trade from TradingView's Account History or Orders History.
        closure_report:
        {
            'symbol': 'AAPL',
            'trade_id': 'TRD-AAPL-...',
            'exit_price': 155.00,
            'exit_reason': 'TAKE_PROFIT' | 'STOP_LOSS' | 'MANUAL' | 'OTHER',
            'gross_pnl': 4.75,
            'trading_fees': 0.0,
            'closed_at': '2026-11-06T...',
            'quantity': 1.0
        }
        """
        sym = closure_report.get("symbol")
        trade_id = closure_report.get("trade_id")
        
        conn = get_db_connection()
        cursor = conn.cursor()

        trade_row = None
        if trade_id:
            cursor.execute("SELECT * FROM trades WHERE id = ?", (trade_id,))
            trade_row = cursor.fetchone()
        
        if not trade_row and sym:
            cursor.execute("SELECT * FROM trades WHERE symbol = ? AND status = 'OPEN' ORDER BY created_at DESC LIMIT 1", (sym,))
            trade_row = cursor.fetchone()

        if not trade_row:
            logger.warning(f"Closure report received for {sym} but no matching open trade found in DB.")
            conn.close()
            return

        trade_dict = dict(trade_row)
        trd_id = trade_dict["id"]

        # Prevent duplicate closure notifications
        if trd_id in self._already_notified_closed_trades or trade_dict["status"] == "CLOSED":
            logger.info(f"Trade {trd_id} was already closed and notified. Skipping duplicate.")
            conn.close()
            return

        # Calculate metrics
        entry_price = trade_dict.get("executed_entry") or trade_dict.get("requested_entry", 1.0)
        exit_price = float(closure_report.get("exit_price") or entry_price)
        qty = float(closure_report.get("quantity") or trade_dict.get("quantity", 1.0))
        gross_pnl = float(closure_report.get("gross_pnl", (exit_price - entry_price) * qty))
        fees = float(closure_report.get("trading_fees", 0.0))
        net_pnl = gross_pnl - fees
        ret_pct = ((exit_price - entry_price) / max(0.01, entry_price)) * 100.0

        # Holding duration
        created_at_dt = None
        try:
            created_at_dt = datetime.fromisoformat(trade_dict["created_at"])
        except Exception:
            created_at_dt = datetime.now(timezone.utc)
        
        closed_at = closure_report.get("closed_at") or datetime.now(timezone.utc).isoformat()
        try:
            closed_dt = datetime.fromisoformat(closed_at)
        except Exception:
            closed_dt = datetime.now(timezone.utc)

        duration_sec = int((closed_dt - created_at_dt).total_seconds())

        exit_reason = closure_report.get("exit_reason", "MANUAL")
        if not exit_reason or exit_reason == "UNKNOWN":
            tp = trade_dict.get("take_profit")
            sl = trade_dict.get("stop_loss")
            if tp and abs(exit_price - tp) <= (entry_price * 0.002):
                exit_reason = "TAKE_PROFIT"
            elif sl and abs(exit_price - sl) <= (entry_price * 0.002):
                exit_reason = "STOP_LOSS"
            else:
                exit_reason = "MANUAL"

        # Update Trade record
        cursor.execute("""
            UPDATE trades SET
                status = 'CLOSED',
                actual_exit_price = ?,
                exit_reason = ?,
                gross_pnl = ?,
                trading_fees = ?,
                net_pnl = ?,
                return_pct = ?,
                holding_duration_seconds = ?,
                closed_at = ?
            WHERE id = ?
        """, (exit_price, exit_reason, gross_pnl, fees, net_pnl, ret_pct, duration_sec, closed_at, trd_id))

        # Update Signal status
        if trade_dict.get("signal_id"):
            cursor.execute("UPDATE signals SET status = 'CLOSED' WHERE id = ?", (trade_dict["signal_id"],))

        # Delete from active positions table
        cursor.execute("DELETE FROM positions WHERE symbol = ?", (sym,))

        conn.commit()
        conn.close()

        # Update trade dict for Telegram
        trade_dict.update({
            "actual_exit_price": exit_price,
            "exit_reason": exit_reason,
            "gross_pnl": gross_pnl,
            "trading_fees": fees,
            "net_pnl": net_pnl,
            "return_pct": ret_pct,
            "holding_duration_seconds": duration_sec,
            "closed_at": closed_at
        })

        self._already_notified_closed_trades.add(trd_id)
        # Send Mandatory Telegram Notification 2
        self.telegram.send_trade_closed_notification(trade_dict)
        log_system_event("TRADE", f"Trade {trd_id} ({sym}) closed: Reason={exit_reason}, Net PnL=${net_pnl:.2f}")

    def _handle_position_closure_by_disappearance(self, cursor, symbol: str, trade_id: str, timestamp: str):
        cursor.execute("SELECT * FROM trades WHERE id = ?", (trade_id,))
        trade_row = cursor.fetchone()
        cursor.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
        
        if trade_row and trade_row["status"] == "OPEN":
            trade_dict = dict(trade_row)
            # Default closure as manual if closed without history record yet
            cursor.execute("""
                UPDATE trades SET status = 'CLOSED', exit_reason = 'MANUAL', closed_at = ? WHERE id = ?
            """, (timestamp, trade_id))
            if trade_dict.get("signal_id"):
                cursor.execute("UPDATE signals SET status = 'CLOSED' WHERE id = ?", (trade_dict["signal_id"],))

# Global monitor instance
monitor = PositionMonitor()

