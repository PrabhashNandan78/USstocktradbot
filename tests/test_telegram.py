import pytest
from backend.telegram_bot import TelegramNotifier
from backend.database import init_db, get_db_connection

def test_telegram_unconfigured():
    init_db()
    notifier = TelegramNotifier(bot_token="", chat_id="")
    assert notifier.is_configured() is False
    res = notifier.test_connection()
    assert res["success"] is False
    assert res["status"] == "NOT_CONFIGURED"

def test_notification_logging_to_db():
    init_db()
    notifier = TelegramNotifier(bot_token="test_tok", chat_id="12345")
    # Manually call _log_notification to verify schema insertion
    notifier._log_notification(
        trade_id="TRD-TEST-1",
        signal_id="SIG-TEST-1",
        notif_type="TEST",
        preview="Test message content",
        status="SENT",
        err=None
    )

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notifications WHERE trade_id = 'TRD-TEST-1'")
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row["notification_type"] == "TEST"
    assert row["status"] == "SENT"
