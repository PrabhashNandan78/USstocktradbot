import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from backend.database import get_db_connection, log_system_event

logger = logging.getLogger(__name__)

class SignalManager:
    @staticmethod
    def get_signal(signal_id: str) -> Optional[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM signals WHERE id = ?", (signal_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return dict(row)

    @staticmethod
    def is_duplicate_demand_zone(symbol: str, zone_low: float, zone_high: float) -> bool:
        """
        Prevents duplicate signals for the same stock and demand zone.
        Checks if an active or recent signal exists within +/- 0.2% of the same zone.
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, demand_zone_low, demand_zone_high, status 
            FROM signals 
            WHERE symbol = ? AND status NOT IN ('REJECTED', 'CLOSED', 'CANCELLED')
            ORDER BY created_at DESC LIMIT 10
        """, (symbol,))
        rows = cursor.fetchall()
        conn.close()

        for r in rows:
            exist_low = r["demand_zone_low"]
            exist_high = r["demand_zone_high"]
            # Tolerance 0.2%
            tol_low = abs(exist_low - zone_low) / max(1.0, zone_low)
            tol_high = abs(exist_high - zone_high) / max(1.0, zone_high)
            if tol_low < 0.005 and tol_high < 0.005:
                logger.info(f"Duplicate signal prevented for {symbol} at zone [{zone_low}, {zone_high}]. Existing: {r['id']}")
                return True
        return False

    @staticmethod
    def create_signal(signal_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        symbol = signal_data["symbol"]
        z_low = signal_data["demand_zone_low"]
        z_high = signal_data["demand_zone_high"]

        if SignalManager.is_duplicate_demand_zone(symbol, z_low, z_high):
            return None

        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute("""
            INSERT INTO signals (
                id, symbol, direction, timestamp, entry_price, stop_loss,
                take_profit, quantity, signal_score, risk_reward,
                demand_zone_low, demand_zone_high, timeframe, status,
                score_breakdown, details, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            signal_data["signal_id"],
            signal_data["symbol"],
            signal_data["direction"],
            signal_data["timestamp"],
            signal_data["entry_price"],
            signal_data["stop_loss"],
            signal_data["take_profit"],
            signal_data["quantity"],
            signal_data["signal_score"],
            signal_data["risk_reward"],
            signal_data["demand_zone_low"],
            signal_data["demand_zone_high"],
            signal_data["timeframe"],
            signal_data.get("status", "GENERATED"),
            json.dumps(signal_data.get("score_breakdown", {})),
            json.dumps(signal_data.get("details", {})),
            now
        ))

        # Also create initial trade record in PENDING_EXECUTION
        trade_id = f"TRD-{signal_data['symbol']}-{now.replace(':', '').replace('-', '')[:15]}"
        cursor.execute("""
            INSERT INTO trades (
                id, signal_id, symbol, direction, requested_entry, quantity,
                stop_loss, take_profit, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_EXECUTION', ?)
        """, (
            trade_id,
            signal_data["signal_id"],
            signal_data["symbol"],
            signal_data["direction"],
            signal_data["entry_price"],
            signal_data["quantity"],
            signal_data["stop_loss"],
            signal_data["take_profit"],
            now
        ))

        conn.commit()
        conn.close()

        log_system_event("SIGNAL", f"Generated signal {signal_data['signal_id']} for {symbol} at {signal_data['entry_price']}")
        return signal_data

    @staticmethod
    def update_signal_status(signal_id: str, new_status: str, notes: Optional[str] = None):
        valid_statuses = [
            "GENERATED", "SENT_TO_EXTENSION", "PENDING_EXECUTION",
            "EXECUTED", "EXECUTION_FAILED", "REJECTED", "CLOSED", "CANCELLED"
        ]
        if new_status not in valid_statuses:
            logger.warning(f"Invalid status {new_status} for signal {signal_id}")

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE signals SET status = ? WHERE id = ?", (new_status, signal_id))
        conn.commit()
        conn.close()

    @staticmethod
    def list_signals(limit: int = 50) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()

        results = []
        for r in rows:
            d = dict(r)
            if d.get("score_breakdown"):
                try:
                    d["score_breakdown"] = json.loads(d["score_breakdown"])
                except Exception:
                    pass
            if d.get("details"):
                try:
                    d["details"] = json.loads(d["details"])
                except Exception:
                    pass
            results.append(d)
        return results
