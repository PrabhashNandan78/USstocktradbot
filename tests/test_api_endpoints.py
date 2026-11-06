import pytest
from starlette.testclient import TestClient
from backend.main import app
from backend.database import init_db

@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c

def test_health_check(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "HEALTHY"

def test_get_settings(client):
    res = client.get("/api/settings/")
    assert res.status_code == 200
    data = res.json()
    assert "alpaca" in data
    assert "telegram" in data
    assert "strategy" in data

def test_scanner_endpoints(client):
    cfg_res = client.get("/api/scanner/config")
    assert cfg_res.status_code == 200
    assert "min_price" in cfg_res.json()

    status_res = client.get("/api/scanner/status")
    assert status_res.status_code == 200

def test_extension_endpoints(client):
    status_res = client.get("/api/extension/status")
    assert status_res.status_code == 200
    assert "connected" in status_res.json()

    # Test Heartbeat POST
    hb_res = client.post("/api/extension/heartbeat", json={
        "tv_tab_detected": True,
        "tv_login_detected": True,
        "paper_trading_connected": True,
        "paper_trading_account_verified": True,
        "current_symbol": "AAPL",
        "broker_name": "Paper Trading by TradingView"
    })
    assert hb_res.status_code == 200
    assert hb_res.json()["received"] is True

    # Verify status reflects heartbeat
    check_res = client.get("/api/extension/status")
    assert check_res.json()["current_symbol"] == "AAPL"
    assert check_res.json()["paper_trading_connected"] is True

def test_integration_test_endpoints(client):
    # Test Alpaca API test endpoint
    alp_res = client.post("/api/tests/alpaca")
    assert alp_res.status_code == 200

    # Test Telegram test endpoint
    tg_res = client.post("/api/tests/telegram")
    assert tg_res.status_code == 200

    # Test Extension test endpoint
    ext_res = client.post("/api/tests/extension")
    assert ext_res.status_code == 200

    # Test Paper Trading test endpoint
    pt_res = client.post("/api/tests/paper-trading")
    assert pt_res.status_code == 200

    # Test E2E workflow test endpoint
    e2e_res = client.post("/api/tests/e2e-workflow")
    assert e2e_res.status_code == 200
    assert e2e_res.json()["overall_success"] is True

    # Test history endpoint
    hist_res = client.get("/api/tests/history")
    assert hist_res.status_code == 200
    assert len(hist_res.json()) > 0
