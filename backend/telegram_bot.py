import logging
import httpx
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from backend.database import get_config_val, set_config_val, get_db_connection, log_system_event

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"

class TelegramNotifier:
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = (bot_token or get_config_val("telegram_bot_token", "")).strip()
        self.chat_id = str(chat_id or get_config_val("telegram_chat_id", "")).strip()

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def _mask_token(self, token: str) -> str:
        if len(token) > 8:
            return token[:4] + "..." + token[-4:]
        return "****"

    def test_connection(self, token: Optional[str] = None, chat: Optional[str] = None) -> Dict[str, Any]:
        """
        Validates token via getMe and tests delivery via sendMessage.
        """
        t = (token or self.bot_token).strip()
        c = str(chat or self.chat_id).strip()

        if not t or not c:
            return {
                "success": False,
                "status": "NOT_CONFIGURED",
                "message": "Telegram Bot Token and Chat ID are both required."
            }

        result = {
            "success": False,
            "status": "FAILED",
            "bot_name": None,
            "bot_username": None,
            "message": "",
            "last_tested": datetime.now(timezone.utc).isoformat()
        }

        # Step 1: Validate Bot Token with getMe
        try:
            with httpx.Client(timeout=8.0) as client:
                res = client.get(f"{TELEGRAM_API_BASE}/bot{t}/getMe")
                if res.status_code != 200:
                    result["message"] = f"Invalid Bot Token ({res.status_code}): {res.text}"
                    return result
                
                data = res.json()
                if not data.get("ok"):
                    result["message"] = f"Telegram error: {data.get('description', 'Unknown error')}"
                    return result

                bot_info = data.get("result", {})
                result["bot_name"] = bot_info.get("first_name")
                result["bot_username"] = bot_info.get("username")
        except Exception as e:
            result["message"] = f"Network error testing Bot Token: {str(e)}"
            return result

        # Step 2: Validate Chat ID with a Test Notification
        test_msg = (
            "🔔 *Antigravity Trading Bot — Connectivity Verified*\n\n"
            f"✅ *Bot:* @{result['bot_username']} ({result['bot_name']})\n"
            f"🕒 *Timestamp:* {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"📡 *Status:* Telegram notification channel active and ready for trade alerts."
        )

        try:
            with httpx.Client(timeout=8.0) as client:
                payload = {
                    "chat_id": c,
                    "text": test_msg,
                    "parse_mode": "Markdown"
                }
                res = client.post(f"{TELEGRAM_API_BASE}/bot{t}/sendMessage", json=payload)
                if res.status_code != 200:
                    result["message"] = f"Bot token is valid, but failed to send to Chat ID ({res.status_code}): {res.text}. Did you start a conversation with the bot?"
                    return result

                send_data = res.json()
                if not send_data.get("ok"):
                    result["message"] = f"Failed to deliver message: {send_data.get('description')}"
                    return result
        except Exception as e:
            result["message"] = f"Network error sending test message: {str(e)}"
            return result

        result["success"] = True
        result["status"] = "CONNECTED"
        result["message"] = f"Connected successfully to @{result['bot_username']} and verified test delivery to Chat {c}."

        set_config_val("telegram_connection_status", {
            "status": "CONNECTED",
            "bot_username": result["bot_username"],
            "last_verified": result["last_tested"]
        })
        log_system_event("TELEGRAM", result["message"], severity="INFO")

        return result

    def send_message(self, text: str, notification_type: str = "INFO", trade_id: Optional[str] = None, signal_id: Optional[str] = None) -> bool:
        if not self.is_configured():
            logger.warning("Telegram notifier is not configured. Message skipped.")
            return False

        now = datetime.now(timezone.utc).isoformat()
        try:
            with httpx.Client(timeout=10.0) as client:
                payload = {
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True
                }
                res = client.post(f"{TELEGRAM_API_BASE}/bot{self.bot_token}/sendMessage", json=payload)
                
                success = (res.status_code == 200 and res.json().get("ok", False))
                err_msg = None if success else res.text

                # Log notification to DB
                self._log_notification(trade_id, signal_id, notification_type, text[:200], "SENT" if success else "FAILED", err_msg)
                
                if success:
                    set_config_val("telegram_last_notification_time", now)
                return success
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            self._log_notification(trade_id, signal_id, notification_type, text[:200], "FAILED", str(e))
            return False

    def send_signal_dispatched_notification(self, signal: Dict[str, Any]) -> bool:
        """
        MANDATORY NOTIFICATION 1:
        Dispatched immediately when the signal is sent to TradingView Extension.
        Clearly distinguishes SENT from EXECUTED.
        """
        sym = signal.get("symbol", "UNKNOWN")
        sig_id = signal.get("signal_id", "N/A")
        entry = signal.get("entry_price", 0.0)
        qty = signal.get("quantity", 1.0)
        sl = signal.get("stop_loss", 0.0)
        tp = signal.get("take_profit", 0.0)
        rr = signal.get("risk_reward", 0.0)
        score = signal.get("signal_score", 0.0)
        tf = signal.get("timeframe", "5M")
        ts = signal.get("timestamp", datetime.now(timezone.utc).isoformat())

        msg = (
            f"🚀 *TRADE SIGNAL DISPATCHED (SENT TO TRADINGVIEW)*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 *Symbol:* `{sym}`\n"
            f"🟢 *Action:* `BUY`\n"
            f"🆔 *Signal ID:* `{sig_id}`\n"
            f"🎯 *Expected Entry:* `${entry:.2f}`\n"
            f"📦 *Quantity:* `{qty}` shares\n"
            f"🛑 *Stop Loss:* `${sl:.2f}`\n"
            f"🎯 *Take Profit:* `${tp:.2f}`\n"
            f"⚖️ *Risk/Reward:* `{rr:.2f}:1`\n"
            f"⭐ *Signal Score:* `{score:.1f}/100`\n"
            f"⏱️ *Timeframe:* `{tf}` (1H BOS + 15M Zone + 5M Entry)\n"
            f"🕒 *Dispatched At:* `{ts}`\n"
            f"⚡ *Execution Status:* `SENT_TO_EXTENSION` (Awaiting TradingView Confirmation)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ *Notice:* This order is queued for Paper Trading execution. A confirmation will follow once verified on the chart."
        )

        return self.send_message(msg, notification_type="SIGNAL_DISPATCHED", signal_id=sig_id)

    def send_execution_status_notification(self, trade: Dict[str, Any], success: bool, details: Optional[str] = None) -> bool:
        """
        Sends confirmation or failure alert when TradingView confirms or rejects execution.
        """
        sym = trade.get("symbol", "UNKNOWN")
        trd_id = trade.get("id", "N/A")
        sig_id = trade.get("signal_id", "N/A")
        
        if success:
            entry = trade.get("executed_entry") or trade.get("requested_entry", 0.0)
            qty = trade.get("quantity", 1.0)
            msg = (
                f"✅ *ORDER EXECUTED IN TRADINGVIEW PAPER TRADING*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📈 *Symbol:* `{sym}`\n"
                f"🆔 *Trade ID:* `{trd_id}`\n"
                f"🟢 *Executed Entry Price:* `${entry:.2f}`\n"
                f"📦 *Position Size:* `{qty}` shares\n"
                f"🛑 *Protective SL Active:* `${trade.get('stop_loss', 0.0):.2f}`\n"
                f"🎯 *Protective TP Active:* `${trade.get('take_profit', 0.0):.2f}`\n"
                f"🕒 *Executed At:* `{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🛡️ *Environment:* TradingView Paper Trading (Simulated)"
            )
            return self.send_message(msg, notification_type="TRADE_EXECUTED", trade_id=trd_id, signal_id=sig_id)
        else:
            msg = (
                f"❌ *TRADE EXECUTION FAILED IN TRADINGVIEW*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📈 *Symbol:* `{sym}`\n"
                f"🆔 *Trade ID:* `{trd_id}`\n"
                f"⚠️ *Failure Reason:* {details or 'Could not complete order ticket in TradingView'}\n"
                f"🕒 *Timestamp:* `{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Order was canceled to protect system state."
            )
            return self.send_message(msg, notification_type="EXECUTION_FAILED", trade_id=trd_id, signal_id=sig_id)

    def send_trade_closed_notification(self, trade: Dict[str, Any]) -> bool:
        """
        MANDATORY NOTIFICATION 2:
        Sent when trade closes. Uses actual TradingView confirmed data.
        """
        sym = trade.get("symbol", "UNKNOWN")
        trd_id = trade.get("id", "N/A")
        sig_id = trade.get("signal_id", "N/A")
        direction = trade.get("direction", "BUY")
        entry_price = trade.get("executed_entry") or trade.get("requested_entry", 0.0)
        exit_price = trade.get("actual_exit_price", 0.0)
        qty = trade.get("quantity", 1.0)
        exit_reason = trade.get("exit_reason", "MANUAL")
        gross_pnl = trade.get("gross_pnl", 0.0)
        fees = trade.get("trading_fees", 0.0)
        net_pnl = trade.get("net_pnl", gross_pnl - fees)
        ret_pct = trade.get("return_pct", 0.0)
        duration_sec = trade.get("holding_duration_seconds", 0)
        closed_at = trade.get("closed_at", datetime.now(timezone.utc).isoformat())

        hours, rem = divmod(duration_sec, 3600)
        minutes, seconds = divmod(rem, 60)
        duration_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"

        pnl_emoji = "🟢" if net_pnl >= 0 else "🔴"
        win_label = "PROFIT" if net_pnl >= 0 else "LOSS"

        msg = (
            f"{pnl_emoji} *TRADE CLOSED — {win_label}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 *Symbol:* `{sym}`\n"
            f"🆔 *Trade ID:* `{trd_id}`\n"
            f"🔄 *Direction:* `{direction}`\n"
            f"📥 *Entry Price:* `${entry_price:.2f}`\n"
            f"📤 *Actual Exit Price:* `${exit_price:.2f}`\n"
            f"📦 *Quantity:* `{qty}` shares\n"
            f"🚪 *Exit Reason:* `{exit_reason}`\n"
            f"💵 *Gross P&L:* `${gross_pnl:+.2f}`\n"
            f"🏷️ *Trading Fees:* `${fees:.2f}`\n"
            f"💰 *Net Realized P&L:* `${net_pnl:+.2f}`\n"
            f"📊 *Return:* `{ret_pct:+.2f}%`\n"
            f"⏳ *Holding Duration:* `{duration_str}`\n"
            f"🕒 *Closed At:* `{closed_at}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Realized data verified from TradingView Paper Trading panel."
        )

        return self.send_message(msg, notification_type="TRADE_CLOSED", trade_id=trd_id, signal_id=sig_id)

    def _log_notification(self, trade_id: Optional[str], signal_id: Optional[str], notif_type: str, preview: str, status: str, err: Optional[str]):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()
            cursor.execute("""
                INSERT INTO notifications (trade_id, signal_id, notification_type, message, status, sent_at, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (trade_id, signal_id, notif_type, preview, status, now, err))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error logging notification: {e}")
