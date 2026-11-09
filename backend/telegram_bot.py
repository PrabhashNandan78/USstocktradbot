
import logging
import httpx

from datetime import datetime, timezone
from typing import Dict, Any, Optional

from backend.database import (
    get_config_val,
    set_config_val,
    get_db_connection,
    log_system_event
)

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramNotifier:

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None
    ):
        raw_token = bot_token if bot_token is not None else get_config_val("telegram_bot_token", "")
        self.bot_token = (raw_token or "").strip()

        raw_chat = chat_id if chat_id is not None else get_config_val("telegram_chat_id", "")
        self.chat_id = str(raw_chat or "").strip()

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def _mask_token(self, token: str) -> str:
        if len(token) > 8:
            return token[:4] + "..." + token[-4:]
        return "****"

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

    def test_connection(
        self,
        token: Optional[str] = None,
        chat: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validates the Telegram bot token using getMe
        and verifies actual message delivery using sendMessage.

        Messages are sent as plain text to avoid Telegram
        Markdown/HTML entity parsing errors.
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

        # Step 1: Validate bot token using getMe.

        try:
            with httpx.Client(timeout=8.0) as client:

                response = client.get(
                    f"{TELEGRAM_API_BASE}/bot{t}/getMe"
                )

                data = response.json()

                if response.status_code != 200 or not data.get("ok"):
                    result["message"] = (
                        f"Invalid Bot Token or Telegram API error "
                        f"({response.status_code}): "
                        f"{data.get('description', response.text)}"
                    )
                    return result

                bot_info = data.get("result", {})

                result["bot_name"] = bot_info.get("first_name")
                result["bot_username"] = bot_info.get("username")

        except httpx.TimeoutException:
            result["message"] = "Connection timed out while validating Telegram bot token."
            return result

        except Exception:
            logger.exception("Telegram getMe validation failed.")
            result["message"] = "Network error while validating Telegram bot token."
            return result

        # Step 2: Send a plain-text test notification.

        timestamp = datetime.now(timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )

        test_msg = (
            "🔔 ANTIGRAVITY TRADING BOT - CONNECTIVITY VERIFIED\n\n"
            f"✅ Bot: @{result['bot_username']} ({result['bot_name']})\n"
            f"🕒 Timestamp: {timestamp}\n"
            "📡 Status: Telegram notification channel is active "
            "and ready for trade alerts."
        )

        try:
            with httpx.Client(timeout=8.0) as client:

                payload = {
                    "chat_id": c,
                    "text": test_msg,
                    "disable_web_page_preview": True
                }

                response = client.post(
                    f"{TELEGRAM_API_BASE}/bot{t}/sendMessage",
                    json=payload
                )

                send_data = response.json()

                if response.status_code != 200 or not send_data.get("ok"):

                    description = send_data.get(
                        "description",
                        response.text
                    )

                    result["message"] = (
                        f"Bot token is valid, but Telegram could not "
                        f"deliver the message ({response.status_code}): "
                        f"{description}. Verify the Chat ID and ensure "
                        f"you have started a conversation with the bot."
                    )

                    return result

        except httpx.TimeoutException:
            result["message"] = (
                "Telegram message delivery timed out. "
                "Check your connection and try again."
            )
            return result

        except Exception:
            logger.exception("Telegram test message delivery failed.")
            result["message"] = (
                "Network error while sending the Telegram test message."
            )
            return result

        # Step 3: Persist successful connection status.

        result["success"] = True
        result["status"] = "CONNECTED"

        result["message"] = (
            f"Connected successfully to @{result['bot_username']} "
            f"and verified test delivery to Chat {c}."
        )

        set_config_val(
            "telegram_connection_status",
            {
                "status": "CONNECTED",
                "bot_username": result["bot_username"],
                "last_verified": result["last_tested"]
            }
        )

        # Ensure admin chat_id is registered as active subscriber
        self.register_subscriber(c, username=result.get("bot_username"), is_admin=True)

        log_system_event(
            "TELEGRAM",
            result["message"],
            severity="INFO"
        )

        return result

    # ---------------------------------------------------------
    # SUBSCRIBER MANAGEMENT & MULTI-USER BROADCAST
    # ---------------------------------------------------------

    def register_subscriber(
        self,
        chat_id: str,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        is_admin: bool = False
    ) -> bool:
        """
        Registers or reactivates a subscriber in the telegram_subscribers table.
        """
        if not chat_id:
            return False

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()
            cursor.execute("""
                INSERT INTO telegram_subscribers (
                    chat_id, username, first_name, last_name, is_active, is_admin, subscribed_at
                )
                VALUES (?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    username = COALESCE(excluded.username, telegram_subscribers.username),
                    first_name = COALESCE(excluded.first_name, telegram_subscribers.first_name),
                    last_name = COALESCE(excluded.last_name, telegram_subscribers.last_name),
                    is_active = 1,
                    is_admin = CASE WHEN excluded.is_admin = 1 THEN 1 ELSE telegram_subscribers.is_admin END
            """, (str(chat_id).strip(), username, first_name, last_name, 1 if is_admin else 0, now))
            conn.commit()
            return True
        except Exception:
            logger.exception("Failed to register subscriber %s", chat_id)
            return False
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def unsubscribe(self, chat_id: str) -> bool:
        """
        Deactivates a subscriber.
        """
        if not chat_id:
            return False

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE telegram_subscribers SET is_active = 0 WHERE chat_id = ?", (str(chat_id).strip(),))
            conn.commit()
            return True
        except Exception:
            logger.exception("Failed to unsubscribe %s", chat_id)
            return False
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def get_subscribers(self, active_only: bool = True) -> list:
        """
        Returns list of subscribers.
        """
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            if active_only:
                cursor.execute("SELECT * FROM telegram_subscribers WHERE is_active = 1 ORDER BY subscribed_at ASC")
            else:
                cursor.execute("SELECT * FROM telegram_subscribers ORDER BY subscribed_at ASC")
            rows = [dict(r) for r in cursor.fetchall()]
            return rows
        except Exception:
            logger.exception("Failed to fetch subscribers")
            return []
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _update_subscriber_delivery(self, chat_id: str, success: bool, error: Optional[str] = None):
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()
            if success:
                cursor.execute("""
                    UPDATE telegram_subscribers
                    SET last_delivery_at = ?, last_error = NULL
                    WHERE chat_id = ?
                """, (now, str(chat_id).strip()))
            else:
                cursor.execute("""
                    UPDATE telegram_subscribers
                    SET last_error = ?
                    WHERE chat_id = ?
                """, (error, str(chat_id).strip()))
            conn.commit()
        except Exception:
            logger.exception("Failed to update subscriber delivery state")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _send_direct_message(self, client: httpx.Client, chat_id: str, text: str) -> bool:
        try:
            payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
            res = client.post(f"{TELEGRAM_API_BASE}/bot{self.bot_token}/sendMessage", json=payload)
            data = res.json() if res.status_code == 200 else {}
            return res.status_code == 200 and data.get("ok", False)
        except Exception:
            logger.exception("Failed to send direct reply to %s", chat_id)
            return False

    def broadcast_message(
        self,
        text: str,
        notification_type: str = "BROADCAST",
        trade_id: Optional[str] = None,
        signal_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Broadcasts message to all active subscribers, including configured chat_id.
        """
        if not self.bot_token:
            return {"total": 0, "sent": 0, "failed": 0, "error": "Bot token not configured"}

        if self.chat_id:
            self.register_subscriber(self.chat_id, is_admin=True)

        subscribers = self.get_subscribers(active_only=True)
        target_chat_ids = set()
        for s in subscribers:
            if s.get("chat_id"):
                target_chat_ids.add(str(s["chat_id"]).strip())
        if self.chat_id:
            target_chat_ids.add(self.chat_id)

        if not target_chat_ids:
            return {"total": 0, "sent": 0, "failed": 0, "error": "No active recipients"}

        sent_count = 0
        failed_count = 0
        errors = []
        now = datetime.now(timezone.utc).isoformat()

        with httpx.Client(timeout=10.0) as client:
            for cid in target_chat_ids:
                try:
                    payload = {
                        "chat_id": cid,
                        "text": str(text),
                        "disable_web_page_preview": True
                    }
                    res = client.post(f"{TELEGRAM_API_BASE}/bot{self.bot_token}/sendMessage", json=payload)
                    data = res.json() if res.status_code == 200 else {}
                    if res.status_code == 200 and data.get("ok"):
                        sent_count += 1
                        self._update_subscriber_delivery(cid, success=True)
                    else:
                        failed_count += 1
                        err_desc = data.get("description", res.text)
                        errors.append(f"{cid}: {err_desc}")
                        self._update_subscriber_delivery(cid, success=False, error=err_desc)
                except Exception as e:
                    failed_count += 1
                    errors.append(f"{cid}: {str(e)}")
                    self._update_subscriber_delivery(cid, success=False, error=str(e))

        status = "SENT" if sent_count > 0 else "FAILED"
        err_str = "; ".join(errors) if errors else None
        self._log_notification(trade_id, signal_id, notification_type, str(text)[:200], status, err_str)
        if sent_count > 0:
            set_config_val("telegram_last_notification_time", now)

        return {
            "total": len(target_chat_ids),
            "sent": sent_count,
            "failed": failed_count,
            "errors": errors
        }

    def poll_telegram_updates(self) -> Dict[str, Any]:
        """
        Polls Telegram getUpdates API for incoming messages and commands.
        Handles:
          /start - Registers user as active subscriber and replies with greeting
          /stop - Unsubscribes user
          /status - Reports current bot status
          /help - Shows help
        """
        if not self.bot_token:
            return {"processed": 0, "status": "NOT_CONFIGURED"}

        last_offset = get_config_val("telegram_poll_offset", 0)
        url = f"{TELEGRAM_API_BASE}/bot{self.bot_token}/getUpdates"
        params = {"offset": last_offset + 1, "timeout": 2, "limit": 20}

        try:
            with httpx.Client(timeout=8.0) as client:
                res = client.get(url, params=params)
                if res.status_code != 200:
                    return {"processed": 0, "error": res.text}
                data = res.json()
                if not data.get("ok"):
                    return {"processed": 0, "error": data.get("description")}

                updates = data.get("result", [])
                max_update_id = last_offset
                processed_count = 0

                for update in updates:
                    update_id = update.get("update_id", 0)
                    if update_id > max_update_id:
                        max_update_id = update_id

                    msg = update.get("message", {})
                    chat = msg.get("chat", {})
                    chat_id = str(chat.get("id", "")).strip()
                    text = (msg.get("text") or "").strip()
                    username = chat.get("username")
                    first_name = chat.get("first_name")
                    last_name = chat.get("last_name")

                    if not chat_id:
                        continue

                    processed_count += 1
                    cmd = text.split()[0].lower() if text else ""

                    if cmd in ("/start", "start"):
                        self.register_subscriber(chat_id, username, first_name, last_name)
                        reply = (
                            f"👋 Hello {first_name or 'there'}!\n\n"
                            "✅ You are now subscribed to US Equities Trading Bot alerts.\n"
                            "You will receive:\n"
                            "• 🚀 Trade Signal Dispatches\n"
                            "• ⚡ Paper Trading Execution Confirmations\n"
                            "• 📊 Realized P&L Trade Close Updates\n\n"
                            "Commands:\n"
                            "/status - Check bot & Paper Trading status\n"
                            "/stop - Unsubscribe from alerts\n"
                            "/help - Command list"
                        )
                        self._send_direct_message(client, chat_id, reply)

                    elif cmd in ("/stop", "stop", "/unsubscribe"):
                        self.unsubscribe(chat_id)
                        reply = "🛑 You have unsubscribed from trading alerts. Send /start anytime to resubscribe."
                        self._send_direct_message(client, chat_id, reply)

                    elif cmd in ("/status", "status"):
                        from backend.database import get_db_connection
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("SELECT COUNT(*) as cnt FROM trades WHERE status = 'OPEN'")
                        open_trades = cursor.fetchone()["cnt"]
                        cursor.execute("SELECT SUM(net_pnl) as total_pnl FROM trades WHERE trade_source = 'TRADINGVIEW_PAPER'")
                        pnl_row = cursor.fetchone()
                        paper_pnl = pnl_row["total_pnl"] if pnl_row and pnl_row["total_pnl"] is not None else 0.0
                        conn.close()

                        ext_status = get_config_val("extension_status", {})
                        acct_state = ext_status.get("account_state", "UNKNOWN")

                        reply = (
                            "📊 TRADING BOT STATUS\n"
                            "━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"🛡️ Paper Trading State: {acct_state}\n"
                            f"📂 Open Positions: {open_trades}\n"
                            f"💰 Realized Paper P&L: ${paper_pnl:+.2f}\n"
                            f"🕒 UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                        self._send_direct_message(client, chat_id, reply)

                    elif cmd in ("/help", "help"):
                        reply = (
                            "ℹ️ BOT COMMANDS\n"
                            "━━━━━━━━━━━━━━━━━━━━━━\n"
                            "/start - Subscribe to trade alerts\n"
                            "/status - View system and P&L status\n"
                            "/stop - Unsubscribe\n"
                            "/help - Show this message"
                        )
                        self._send_direct_message(client, chat_id, reply)

                if max_update_id > last_offset:
                    set_config_val("telegram_poll_offset", max_update_id)

                return {"processed": processed_count, "last_offset": max_update_id}
        except Exception as e:
            logger.exception("Error polling Telegram updates")
            return {"processed": 0, "error": str(e)}

    def send_message(
        self,
        text: str,
        notification_type: str = "INFO",
        trade_id: Optional[str] = None,
        signal_id: Optional[str] = None
    ) -> bool:
        """
        Sends a Telegram notification to configured chat and all active subscribers.
        Plain text mode ensures safety from entity parse errors.
        """
        if not self.is_configured() and not self.get_subscribers(active_only=True):
            logger.warning("Telegram notifier is not configured. Message skipped.")
            return False

        res = self.broadcast_message(
            text=text,
            notification_type=notification_type,
            trade_id=trade_id,
            signal_id=signal_id
        )
        return res.get("sent", 0) > 0

    # ---------------------------------------------------------
    # NOTIFICATION 1: SIGNAL DISPATCHED
    # ---------------------------------------------------------

    def send_signal_dispatched_notification(
        self,
        signal: Dict[str, Any]
    ) -> bool:
        """
        Mandatory notification 1.

        Dispatched immediately when the signal is sent
        to the TradingView extension.

        Clearly distinguishes SENT from EXECUTED.
        """

        sym = signal.get("symbol", "UNKNOWN")
        sig_id = signal.get("signal_id", "N/A")

        entry = self._safe_float(signal.get("entry_price"))
        qty = signal.get("quantity", 1.0)
        sl = self._safe_float(signal.get("stop_loss"))
        tp = self._safe_float(signal.get("take_profit"))
        rr = self._safe_float(signal.get("risk_reward"))
        score = self._safe_float(signal.get("signal_score"))

        tf = signal.get("timeframe", "5M")

        ts = signal.get(
            "timestamp",
            datetime.now(timezone.utc).isoformat()
        )

        msg = (
            "🚀 TRADE SIGNAL DISPATCHED (SENT TO TRADINGVIEW)\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 Symbol: {sym}\n"
            "🟢 Action: BUY\n"
            f"🆔 Signal ID: {sig_id}\n"
            f"🎯 Expected Entry: ${entry:.2f}\n"
            f"📦 Quantity: {qty} shares\n"
            f"🛑 Stop Loss: ${sl:.2f}\n"
            f"🎯 Take Profit: ${tp:.2f}\n"
            f"⚖️ Risk/Reward: {rr:.2f}:1\n"
            f"⭐ Signal Score: {score:.1f}/100\n"
            f"⏱️ Timeframe: {tf} "
            "(1H BOS + 15M Zone + 5M Entry)\n"
            f"🕒 Dispatched At: {ts}\n"
            "⚡ Execution Status: SENT_TO_EXTENSION\n"
            "(Awaiting TradingView Confirmation)\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ Notice: This order is queued for Paper Trading "
            "execution. A confirmation will follow once "
            "verified on the chart."
        )

        return self.send_message(
            msg,
            notification_type="SIGNAL_DISPATCHED",
            signal_id=sig_id
        )

    # ---------------------------------------------------------
    # EXECUTION STATUS NOTIFICATION
    # ---------------------------------------------------------

    def send_execution_status_notification(
        self,
        trade: Dict[str, Any],
        success: bool,
        details: Optional[str] = None
    ) -> bool:
        """
        Sends confirmation or failure alert when TradingView
        confirms or rejects execution.
        """

        sym = trade.get("symbol", "UNKNOWN")
        trd_id = trade.get("id", "N/A")
        sig_id = trade.get("signal_id", "N/A")

        if success:

            entry = self._safe_float(
                trade.get("executed_entry")
                or trade.get("requested_entry", 0.0)
            )

            qty = trade.get("quantity", 1.0)

            sl = self._safe_float(trade.get("stop_loss"))
            tp = self._safe_float(trade.get("take_profit"))

            msg = (
                "✅ ORDER EXECUTED IN TRADINGVIEW PAPER TRADING\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📈 Symbol: {sym}\n"
                f"🆔 Trade ID: {trd_id}\n"
                f"🟢 Executed Entry Price: ${entry:.2f}\n"
                f"📦 Position Size: {qty} shares\n"
                f"🛑 Protective SL Active: ${sl:.2f}\n"
                f"🎯 Protective TP Active: ${tp:.2f}\n"
                f"🕒 Executed At: "
                f"{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🛡️ Environment: TradingView Paper Trading (Simulated)"
            )

            return self.send_message(
                msg,
                notification_type="TRADE_EXECUTED",
                trade_id=trd_id,
                signal_id=sig_id
            )

        else:

            failure_reason = (
                details
                or "Could not complete order ticket in TradingView"
            )

            msg = (
                "❌ TRADE EXECUTION FAILED IN TRADINGVIEW\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📈 Symbol: {sym}\n"
                f"🆔 Trade ID: {trd_id}\n"
                f"⚠️ Failure Reason: {failure_reason}\n"
                f"🕒 Timestamp: "
                f"{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "Order was canceled to protect system state."
            )

            return self.send_message(
                msg,
                notification_type="EXECUTION_FAILED",
                trade_id=trd_id,
                signal_id=sig_id
            )

    # ---------------------------------------------------------
    # NOTIFICATION 2: TRADE CLOSED
    # ---------------------------------------------------------

    def send_trade_closed_notification(
        self,
        trade: Dict[str, Any]
    ) -> bool:
        """
        Mandatory notification 2.

        Sent when a trade closes.
        Uses actual TradingView-confirmed data.
        """

        sym = trade.get("symbol", "UNKNOWN")
        trd_id = trade.get("id", "N/A")
        sig_id = trade.get("signal_id", "N/A")

        direction = trade.get("direction", "BUY")

        entry_price = self._safe_float(
            trade.get("executed_entry")
            or trade.get("requested_entry", 0.0)
        )

        exit_price = self._safe_float(
            trade.get("actual_exit_price")
        )

        qty = trade.get("quantity", 1.0)

        exit_reason = trade.get("exit_reason", "MANUAL")

        gross_pnl = self._safe_float(
            trade.get("gross_pnl")
        )

        fees = self._safe_float(
            trade.get("trading_fees")
        )

        net_pnl = self._safe_float(
            trade.get("net_pnl", gross_pnl - fees)
        )

        ret_pct = self._safe_float(
            trade.get("return_pct")
        )

        duration_sec = max(
            0,
            self._safe_int(
                trade.get("holding_duration_seconds")
            )
        )

        closed_at = trade.get(
            "closed_at",
            datetime.now(timezone.utc).isoformat()
        )

        hours, rem = divmod(duration_sec, 3600)
        minutes, seconds = divmod(rem, 60)

        duration_str = (
            f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
        )

        pnl_emoji = "🟢" if net_pnl >= 0 else "🔴"
        win_label = "PROFIT" if net_pnl >= 0 else "LOSS"

        msg = (
            f"{pnl_emoji} TRADE CLOSED — {win_label}\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 Symbol: {sym}\n"
            f"🆔 Trade ID: {trd_id}\n"
            f"🔄 Direction: {direction}\n"
            f"📥 Entry Price: ${entry_price:.2f}\n"
            f"📤 Actual Exit Price: ${exit_price:.2f}\n"
            f"📦 Quantity: {qty} shares\n"
            f"🚪 Exit Reason: {exit_reason}\n"
            f"💵 Gross P&L: ${gross_pnl:+.2f}\n"
            f"🏷️ Trading Fees: ${fees:.2f}\n"
            f"💰 Net Realized P&L: ${net_pnl:+.2f}\n"
            f"📊 Return: {ret_pct:+.2f}%\n"
            f"⏳ Holding Duration: {duration_str}\n"
            f"🕒 Closed At: {closed_at}\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📊 Realized data verified from TradingView "
            "Paper Trading panel."
        )

        return self.send_message(
            msg,
            notification_type="TRADE_CLOSED",
            trade_id=trd_id,
            signal_id=sig_id
        )

    # ---------------------------------------------------------
    # DATABASE NOTIFICATION LOGGING
    # ---------------------------------------------------------

    def _log_notification(
        self,
        trade_id: Optional[str],
        signal_id: Optional[str],
        notif_type: str,
        preview: str,
        status: str,
        err: Optional[str]
    ):
        """
        Persists Telegram notification delivery status
        in the existing SQLite notifications table.
        """

        conn = None

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            now = datetime.now(timezone.utc).isoformat()

            cursor.execute(
                """
                INSERT INTO notifications (
                    trade_id,
                    signal_id,
                    notification_type,
                    message,
                    status,
                    sent_at,
                    error_message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade_id,
                    signal_id,
                    notif_type,
                    preview,
                    status,
                    now,
                    err
                )
            )

            conn.commit()

        except Exception:
            logger.exception("Error logging Telegram notification.")

        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    logger.exception(
                        "Error closing notification database connection."
                    )
