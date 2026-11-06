import sqlite3
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from backend.config import DB_PATH

logger = logging.getLogger(__name__)

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.executescript("""
    -- System Configuration table
    CREATE TABLE IF NOT EXISTS system_config (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    -- Stock Universe / Watchlist table
    CREATE TABLE IF NOT EXISTS watchlists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL UNIQUE,
        name TEXT,
        is_active INTEGER DEFAULT 1,
        added_at TEXT NOT NULL
    );

    -- Signals table
    CREATE TABLE IF NOT EXISTS signals (
        id TEXT PRIMARY KEY,
        symbol TEXT NOT NULL,
        direction TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        entry_price REAL NOT NULL,
        stop_loss REAL NOT NULL,
        take_profit REAL NOT NULL,
        quantity REAL NOT NULL,
        signal_score REAL NOT NULL,
        risk_reward REAL NOT NULL,
        demand_zone_low REAL NOT NULL,
        demand_zone_high REAL NOT NULL,
        timeframe TEXT NOT NULL,
        status TEXT NOT NULL,
        score_breakdown TEXT,
        details TEXT,
        created_at TEXT NOT NULL
    );

    -- Trades table
    CREATE TABLE IF NOT EXISTS trades (
        id TEXT PRIMARY KEY,
        signal_id TEXT,
        symbol TEXT NOT NULL,
        direction TEXT NOT NULL,
        requested_entry REAL NOT NULL,
        executed_entry REAL,
        actual_exit_price REAL,
        quantity REAL NOT NULL,
        stop_loss REAL NOT NULL,
        take_profit REAL NOT NULL,
        status TEXT NOT NULL,
        exit_reason TEXT,
        gross_pnl REAL,
        trading_fees REAL DEFAULT 0.0,
        net_pnl REAL,
        return_pct REAL,
        holding_duration_seconds INTEGER,
        created_at TEXT NOT NULL,
        executed_at TEXT,
        closed_at TEXT,
        tv_order_id TEXT,
        execution_notes TEXT,
        FOREIGN KEY(signal_id) REFERENCES signals(id)
    );

    -- Orders table
    CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY,
        trade_id TEXT NOT NULL,
        order_type TEXT NOT NULL,
        side TEXT NOT NULL,
        price REAL,
        quantity REAL NOT NULL,
        status TEXT NOT NULL,
        tv_order_id TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(trade_id) REFERENCES trades(id)
    );

    -- Active Positions table
    CREATE TABLE IF NOT EXISTS positions (
        symbol TEXT PRIMARY KEY,
        trade_id TEXT NOT NULL,
        quantity REAL NOT NULL,
        entry_price REAL NOT NULL,
        current_price REAL NOT NULL,
        unrealized_pnl REAL NOT NULL,
        stop_loss REAL NOT NULL,
        take_profit REAL NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(trade_id) REFERENCES trades(id)
    );

    -- Telegram and System Notifications
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_id TEXT,
        signal_id TEXT,
        notification_type TEXT NOT NULL,
        message TEXT NOT NULL,
        status TEXT NOT NULL,
        sent_at TEXT NOT NULL,
        error_message TEXT
    );

    -- System Audit and Diagnostic Events
    CREATE TABLE IF NOT EXISTS system_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        message TEXT NOT NULL,
        metadata TEXT,
        created_at TEXT NOT NULL
    );

    -- Test Results Log
    CREATE TABLE IF NOT EXISTS test_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        test_suite TEXT NOT NULL,
        status TEXT NOT NULL,
        details TEXT,
        executed_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
    CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
    CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
    CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
    """)

    conn.commit()
    conn.close()
    logger.info("Database initialized successfully at %s", DB_PATH)

# Config helpers
def get_config_val(key: str, default: Any = None) -> Any:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM system_config WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row["value"])
        except Exception:
            return row["value"]
    return default

def set_config_val(key: str, value: Any):
    conn = get_db_connection()
    cursor = conn.cursor()
    val_str = json.dumps(value) if not isinstance(value, str) else value
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
        INSERT INTO system_config (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
    """, (key, val_str, now))
    conn.commit()
    conn.close()

def log_system_event(event_type: str, message: str, severity: str = "INFO", metadata: Optional[Dict] = None):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        meta_str = json.dumps(metadata) if metadata else None
        cursor.execute("""
            INSERT INTO system_events (event_type, severity, message, metadata, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (event_type, severity, message, meta_str, now))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to log system event: {e}")
