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

def test_telegram_subscribers_crud():
    init_db()
    notifier = TelegramNotifier(bot_token="test_tok", chat_id="99999")
    
    # Register subscriber
    success = notifier.register_subscriber(
        chat_id="111222",
        username="trader_joe",
        first_name="Joe",
        last_name="Trader",
        is_admin=False
    )
    assert success is True

    # Retrieve subscribers
    subs = notifier.get_subscribers(active_only=True)
    assert any(s["chat_id"] == "111222" for s in subs)
    
    found = next(s for s in subs if s["chat_id"] == "111222")
    assert found["username"] == "trader_joe"
    assert found["first_name"] == "Joe"
    assert found["is_active"] == 1

    # Unsubscribe
    unsub_ok = notifier.unsubscribe("111222")
    assert unsub_ok is True

    active_subs = notifier.get_subscribers(active_only=True)
    assert not any(s["chat_id"] == "111222" for s in active_subs)

    all_subs = notifier.get_subscribers(active_only=False)
    unsubbed = next(s for s in all_subs if s["chat_id"] == "111222")
    assert unsubbed["is_active"] == 0

def test_telegram_broadcast_and_delivery_state(monkeypatch):
    init_db()
    notifier = TelegramNotifier(bot_token="fake_token_123", chat_id="55555")
    notifier.register_subscriber("55555", is_admin=True)
    notifier.register_subscriber("66666", is_admin=False)

    class DummyResponse:
        status_code = 200
        text = '{"ok": true, "result": {"message_id": 100}}'
        def json(self):
            return {"ok": True, "result": {"message_id": 100}}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, json=None):
            return DummyResponse()

    import httpx
    monkeypatch.setattr(httpx, "Client", DummyClient)

    res = notifier.broadcast_message("Test broadcast message")
    assert res["total"] >= 2
    assert res["sent"] >= 2
    assert res["failed"] == 0

