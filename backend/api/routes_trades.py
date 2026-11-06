import logging
from fastapi import APIRouter, HTTPException
from typing import Optional, List, Dict, Any
from backend.database import get_db_connection, log_system_event
from backend.execution_bridge import bridge

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/trades", tags=["Trades"])

@router.get("/active")
def get_active_trades():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.symbol, p.trade_id, p.quantity, p.entry_price, p.current_price, 
               p.unrealized_pnl, p.stop_loss, p.take_profit, p.updated_at,
               t.direction, t.created_at, t.status
        FROM positions p
        LEFT JOIN trades t ON p.trade_id = t.id
        ORDER BY p.updated_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/history")
def get_trade_history(limit: int = 100, symbol: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM trades WHERE status = 'CLOSED'"
    params = []
    if symbol:
        query += " AND symbol = ?"
        params.append(symbol.upper())
    query += " ORDER BY closed_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@router.get("/analytics")
def get_performance_analytics():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.*, s.signal_score 
        FROM trades t
        LEFT JOIN signals s ON t.signal_id = s.id
        WHERE t.status = 'CLOSED'
    """)
    trades = [dict(r) for r in cursor.fetchall()]
    conn.close()

    total_trades = len(trades)
    if total_trades == 0:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "total_gross_pnl": 0.0,
            "total_fees": 0.0,
            "net_pnl": 0.0,
            "average_profit": 0.0,
            "average_loss": 0.0,
            "max_drawdown": 0.0,
            "by_stock": {},
            "by_score_tier": {}
        }

    wins = [t for t in trades if (t.get("net_pnl") or 0.0) > 0]
    losses = [t for t in trades if (t.get("net_pnl") or 0.0) <= 0]
    
    total_win_dollars = sum(t.get("net_pnl", 0.0) for t in wins)
    total_loss_dollars = abs(sum(t.get("net_pnl", 0.0) for t in losses))
    net_pnl = sum(t.get("net_pnl", 0.0) for t in trades)
    gross_pnl = sum(t.get("gross_pnl", 0.0) for t in trades)
    fees = sum(t.get("trading_fees", 0.0) for t in trades)

    win_rate = (len(wins) / total_trades) * 100.0
    profit_factor = round(total_win_dollars / total_loss_dollars, 2) if total_loss_dollars > 0 else (round(total_win_dollars, 2) if total_win_dollars > 0 else 0.0)
    avg_profit = (total_win_dollars / len(wins)) if wins else 0.0
    avg_loss = (total_loss_dollars / len(losses)) if losses else 0.0

    # Max Drawdown calculation
    cumulative_pnl = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in sorted(trades, key=lambda x: x.get("closed_at") or ""):
        cumulative_pnl += t.get("net_pnl", 0.0)
        if cumulative_pnl > peak:
            peak = cumulative_pnl
        dd = peak - cumulative_pnl
        if dd > max_dd:
            max_dd = dd

    # Performance by Stock
    by_stock = {}
    for t in trades:
        sym = t["symbol"]
        if sym not in by_stock:
            by_stock[sym] = {"trades": 0, "wins": 0, "net_pnl": 0.0}
        by_stock[sym]["trades"] += 1
        pnl = t.get("net_pnl", 0.0)
        by_stock[sym]["net_pnl"] += pnl
        if pnl > 0:
            by_stock[sym]["wins"] += 1

    for sym, stats in by_stock.items():
        stats["win_rate"] = round((stats["wins"] / stats["trades"]) * 100.0, 1)
        stats["net_pnl"] = round(stats["net_pnl"], 2)

    # Performance by Score Tier
    # 60-69, 70-79, 80-89, 90-100
    by_score = {"60-69": {"count": 0, "net_pnl": 0.0, "wins": 0},
                "70-79": {"count": 0, "net_pnl": 0.0, "wins": 0},
                "80-89": {"count": 0, "net_pnl": 0.0, "wins": 0},
                "90-100": {"count": 0, "net_pnl": 0.0, "wins": 0}}

    for t in trades:
        score = t.get("signal_score") or 60.0
        pnl = t.get("net_pnl", 0.0)
        tier = "90-100" if score >= 90 else ("80-89" if score >= 80 else ("70-79" if score >= 70 else "60-69"))
        by_score[tier]["count"] += 1
        by_score[tier]["net_pnl"] = round(by_score[tier]["net_pnl"] + pnl, 2)
        if pnl > 0:
            by_score[tier]["wins"] += 1

    return {
        "total_trades": total_trades,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate_pct": round(win_rate, 1),
        "profit_factor": profit_factor,
        "total_gross_pnl": round(gross_pnl, 2),
        "total_fees": round(fees, 2),
        "net_pnl": round(net_pnl, 2),
        "average_profit": round(avg_profit, 2),
        "average_loss": round(avg_loss, 2),
        "max_drawdown": round(max_dd, 2),
        "by_stock": by_stock,
        "by_score_tier": by_score
    }

@router.post("/kill-switch")
async def trigger_kill_switch():
    """
    Emergency Kill Switch:
    - Broadcasts emergency stop command to Extension to cancel pending orders
    - Logs emergency event
    """
    log_system_event("SECURITY", "KILL SWITCH TRIGGERED: Emergency stop commanded by operator", severity="ERROR")
    await bridge.send_to_all({"type": "KILL_SWITCH", "action": "STOP_ALL_TRADING"})
    return {"status": "TRIGGERED", "message": "Emergency kill switch engaged. Orders halted."}
