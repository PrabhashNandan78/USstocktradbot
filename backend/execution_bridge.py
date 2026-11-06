import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import WebSocket

from backend.database import get_db_connection, set_config_val, get_config_val, log_system_event
from backend.signals import SignalManager
from backend.telegram_bot import TelegramNotifier

logger = logging.getLogger(__name__)

class ExecutionBridge:
    def __init__(self):
        self.active_websockets: List[WebSocket] = []
        self.telegram = TelegramNotifier()
        self.extension_state = {
            "installed": False,
            "connected": False,
            "tv_tab_detected": False,
            "tv_login_detected": False,
            "paper_trading_connected": False,
            "paper_trading_account_verified": False,
            "current_symbol": None,
            "last_heartbeat": None,
            "broker_name": None,
            "error_message": None
        }

    async def connect_websocket(self, websocket: WebSocket):
        await websocket.accept()
        self.active_websockets.append(websocket)
        self.extension_state["installed"] = True
        self.extension_state["connected"] = True
        self.extension_state["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
        logger.info("Chrome Extension WebSocket connected.")
        log_system_event("EXTENSION", "Extension WebSocket connected successfully")

        # Send current pending signals or system state to extension
        await self.broadcast_state()

    def disconnect_websocket(self, websocket: WebSocket):
        if websocket in self.active_websockets:
            self.active_websockets.remove(websocket)
        if len(self.active_websockets) == 0:
            self.extension_state["connected"] = False
        logger.info("Chrome Extension WebSocket disconnected.")
        log_system_event("EXTENSION", "Extension WebSocket disconnected", severity="WARNING")

    def update_status_from_extension(self, data: Dict[str, Any]):
        """
        Receives heartbeat / telemetry from TradingView content script:
        - tab detected, login detected, paper trading connected, broker name, current symbol
        """
        now = datetime.now(timezone.utc).isoformat()
        self.extension_state["last_heartbeat"] = now
        self.extension_state["installed"] = True
        self.extension_state["connected"] = True
        self.extension_state["tv_tab_detected"] = data.get("tv_tab_detected", False)
        self.extension_state["tv_login_detected"] = data.get("tv_login_detected", False)
        
        # Rigorous Broker Safety Check:
        # Must be Paper Trading, NEVER a live broker!
        broker_name = data.get("broker_name", "")
        self.extension_state["broker_name"] = broker_name
        is_paper = ("paper" in broker_name.lower()) or data.get("paper_trading_connected", False)
        is_live_broker = any(live in broker_name.lower() for live in ["interactive brokers", "tradovate", "amp", "oanda", "binance", "cqg"])
        
        if is_live_broker:
            self.extension_state["paper_trading_connected"] = False
            self.extension_state["paper_trading_account_verified"] = False
            self.extension_state["error_message"] = f"CRITICAL SAFETY WARNING: Connected broker is '{broker_name}'. Automation only allowed on Paper Trading!"
            log_system_event("SECURITY", self.extension_state["error_message"], severity="ERROR")
        else:
            self.extension_state["paper_trading_connected"] = is_paper
            self.extension_state["paper_trading_account_verified"] = is_paper and data.get("paper_trading_account_verified", False)
            self.extension_state["error_message"] = data.get("error_message")

        self.extension_state["current_symbol"] = data.get("current_symbol")
        
        set_config_val("extension_status", self.extension_state)

    async def broadcast_state(self):
        msg = {
            "type": "STATE_UPDATE",
            "extension_state": self.extension_state,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.send_to_all(msg)

    async def send_to_all(self, message: Dict[str, Any]):
        dead_sockets = []
        payload = json.dumps(message)
        for ws in self.active_websockets:
            try:
                await ws.send_text(payload)
            except Exception as e:
                logger.warning(f"Error sending to extension websocket: {e}")
                dead_sockets.append(ws)
        for ds in dead_sockets:
            self.disconnect_websocket(ds)

    async def dispatch_signal_to_extension(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatches a BUY signal to the extension for Paper Trading execution.
        Verifies Paper Trading is connected before dispatching!
        Triggers Mandatory Notification 1 to Telegram.
        """
        signal_id = signal["signal_id"]
        symbol = signal["symbol"]

        # Safety Check: Paper Trading verification
        if not self.extension_state["connected"] or not self.extension_state["paper_trading_connected"]:
            err_msg = (
                "Cannot dispatch trade: TradingView Paper Trading is NOT connected. "
                "Please connect Paper Trading in TradingView Trading Panel before executing."
            )
            SignalManager.update_signal_status(signal_id, "EXECUTION_FAILED", notes=err_msg)
            log_system_event("EXECUTION", err_msg, severity="ERROR")
            return {"success": False, "status": "PAPER_TRADING_NOT_CONNECTED", "message": err_msg}

        # Send Mandatory Telegram Notification 1 immediately upon dispatch
        SignalManager.update_signal_status(signal_id, "SENT_TO_EXTENSION")
        self.telegram.send_signal_dispatched_notification(signal)

        # Build execution payload for TradingView extension
        exec_payload = {
            "type": "EXECUTE_ORDER",
            "action": "BUY",
            "signal_id": signal_id,
            "symbol": symbol,
            "quantity": signal.get("quantity", 1.0),
            "order_type": "MARKET",
            "entry_price": signal.get("entry_price"),
            "stop_loss": signal.get("stop_loss"),
            "take_profit": signal.get("take_profit"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Send order command to Chrome extension
        await self.send_to_all(exec_payload)
        log_system_event("EXECUTION", f"Dispatched order command to extension for {symbol} (Signal {signal_id})")

        return {"success": True, "status": "SENT_TO_EXTENSION", "message": f"Order dispatched to TradingView extension for {symbol}."}

    def handle_execution_confirmation(self, data: Dict[str, Any]):
        """
        Called when extension verifies order execution or reports failure on TradingView.
        """
        signal_id = data.get("signal_id")
        symbol = data.get("symbol")
        success = data.get("success", False)
        actual_price = data.get("executed_price")
        tv_order_id = data.get("tv_order_id")
        err_msg = data.get("error_message")

        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute("SELECT * FROM trades WHERE signal_id = ?", (signal_id,))
        trade_row = cursor.fetchone()
        
        if not trade_row:
            # Fallback query by symbol
            cursor.execute("SELECT * FROM trades WHERE symbol = ? AND status = 'PENDING_EXECUTION' ORDER BY created_at DESC LIMIT 1", (symbol,))
            trade_row = cursor.fetchone()

        if trade_row:
            trade_dict = dict(trade_row)
            trade_id = trade_dict["id"]
            if success:
                # Update Trade record
                cursor.execute("""
                    UPDATE trades 
                    SET status = 'OPEN', executed_entry = ?, tv_order_id = ?, executed_at = ?, execution_notes = ?
                    WHERE id = ?
                """, (actual_price or trade_dict["requested_entry"], tv_order_id, now, "Verified in TradingView Paper Trading", trade_id))
                
                # Update Signal status
                cursor.execute("UPDATE signals SET status = 'EXECUTED' WHERE id = ?", (signal_id,))

                # Insert into active positions table
                cursor.execute("""
                    INSERT INTO positions (symbol, trade_id, quantity, entry_price, current_price, unrealized_pnl, stop_loss, take_profit, updated_at)
                    VALUES (?, ?, ?, ?, ?, 0.0, ?, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET
                        quantity = excluded.quantity,
                        entry_price = excluded.entry_price,
                        current_price = excluded.current_price,
                        stop_loss = excluded.stop_loss,
                        take_profit = excluded.take_profit,
                        updated_at = excluded.updated_at
                """, (
                    symbol, 
                    trade_id, 
                    trade_dict["quantity"], 
                    actual_price or trade_dict["requested_entry"], 
                    actual_price or trade_dict["requested_entry"],
                    trade_dict["stop_loss"],
                    trade_dict["take_profit"],
                    now
                ))

                conn.commit()
                trade_dict["executed_entry"] = actual_price or trade_dict["requested_entry"]
                self.telegram.send_execution_status_notification(trade_dict, success=True)
                log_system_event("EXECUTION", f"Order confirmed executed on TradingView: {symbol} at {actual_price}")
            else:
                cursor.execute("""
                    UPDATE trades SET status = 'FAILED', execution_notes = ? WHERE id = ?
                """, (err_msg or "Failed during TradingView interaction", trade_id))
                cursor.execute("UPDATE signals SET status = 'EXECUTION_FAILED' WHERE id = ?", (signal_id,))
                conn.commit()
                self.telegram.send_execution_status_notification(trade_dict, success=False, details=err_msg)
                log_system_event("EXECUTION", f"Execution failed on TradingView for {symbol}: {err_msg}", severity="ERROR")
        else:
            logger.warning(f"No pending trade found for signal {signal_id} on confirmation receipt.")

        conn.close()

# Global execution bridge singleton
bridge = ExecutionBridge()
