import pytest
import time
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

from backend.execution_bridge import bridge
from backend.database import init_db, get_db_connection
from backend.signals import SignalManager
from backend.api.routes_extension import HeartbeatModel

def setup_function():
    init_db()
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM positions")
        c.execute("DELETE FROM orders")
        c.execute("DELETE FROM trades")
        c.execute("DELETE FROM signals")
        conn.commit()
    finally:
        conn.close()

    # Reset bridge state
    bridge.extension_state = {
        "installed": True,
        "connected": True,
        "tv_tab_detected": True,
        "tv_login_detected": True,
        "paper_trading_connected": False,
        "paper_trading_account_verified": False,
        "account_state": "UNKNOWN",
        "account_balance": None,
        "last_verified_at": None,
        "current_symbol": "AAPL",
        "last_heartbeat": None,
        "broker_name": None,
        "error_message": None,
        "indicators": None
    }

def get_js_helpers():
    with open("extension/dom_selectors.js", "r", encoding="utf-8") as f:
        dom_selectors_js = f.read()
    with open("extension/paper_trading.js", "r", encoding="utf-8") as f:
        paper_trading_js = f.read()
    return dom_selectors_js, paper_trading_js

def evaluate_in_browser(html_content: str, script_to_run: str):
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            pytest.skip(f"Playwright Chromium browser binary not installed: {e}")

        page = browser.new_page()
        page.set_content(html_content)
        dom_js, pt_js = get_js_helpers()
        page.evaluate(dom_js)
        page.evaluate(pt_js)
        result = page.evaluate(script_to_run)
        browser.close()
        return result

# -------------------------------------------------------------
# 12 Automated Verification Scenarios
# -------------------------------------------------------------

def test_scenario_1_connected_native_paper_trading():
    """Scenario 1: Positively verified Paper Trading account with tabs and balance."""
    html = """
    <div id="header-toolbar-symbol-search">AAPL</div>
    <div class="bottom-widget-bar">
      <button data-name="trading">Paper Trading</button>
    </div>
    <div data-name="trading-panel" style="display:block; width:800px; height:300px;">
      <div data-name="account-manager">
        <button data-name="account-select">Paper Trading</button>
        <div role="tablist">
          <div role="tab" data-name="positions">Positions</div>
          <div role="tab" data-name="orders">Orders</div>
          <div role="tab" data-name="order-history">Order history</div>
          <div role="tab" data-name="balance-history">Balance history</div>
          <div role="tab" data-name="trade-history">Trade history</div>
          <div role="tab" data-name="analytics">Analytics</div>
        </div>
        <div data-name="account-balance">
          <span>Balance</span> <span class="value-">100,000.00 USD</span>
        </div>
      </div>
    </div>
    """
    res = evaluate_in_browser(html, "() => window.PaperTradingGuard.verifyEnvironment()")
    assert res["account_state"] == "PAPER_TRADING_CONNECTED"
    assert res["paper_trading_connected"] is True
    assert res["paper_trading_account_verified"] is True
    assert res["broker_name"] == "Paper Trading by TradingView"
    assert res["account_balance"] == 100000.0
    assert res["error_message"] is None
    assert res["indicators"]["has_account_tabs"] is True
    assert res["indicators"]["has_balance"] is True
    assert "Positions" in res["indicators"]["found_account_tabs"]
    assert "Orders" in res["indicators"]["found_account_tabs"]

def test_scenario_2_disconnected_paper_trading_gallery():
    """Scenario 2: Disconnected state with broker gallery (Connect buttons)."""
    html = """
    <div id="header-toolbar-symbol-search">AAPL</div>
    <div data-name="trading-panel" style="display:block; width:800px; height:300px;">
      <div data-name="broker-list">
        <div class="broker-card">
          <span>Paper Trading by TradingView</span>
          <button data-name="connect-button">Connect</button>
        </div>
        <div class="broker-card">
          <span>Interactive Brokers</span>
          <button data-name="connect-button">Connect</button>
        </div>
      </div>
    </div>
    """
    res = evaluate_in_browser(html, "() => window.PaperTradingGuard.verifyEnvironment()")
    assert res["account_state"] == "DISCONNECTED"
    assert res["paper_trading_connected"] is False
    assert res["broker_name"] == "NONE"
    assert res["indicators"]["is_gallery_visible"] is True
    assert "not connected" in res["error_message"].lower()

def test_scenario_3_live_broker_connected_safety_halt():
    """Scenario 3: Live broker connected (e.g. Interactive Brokers) triggers CRITICAL SAFETY HALT."""
    html = """
    <div id="header-toolbar-symbol-search">AAPL</div>
    <div data-name="trading-panel" style="display:block; width:800px; height:300px;">
      <div data-name="account-manager">
        <button data-name="account-select">Interactive Brokers (Live)</button>
        <div role="tab" data-name="positions">Positions</div>
        <div data-name="account-balance">
          <span class="value-">54,230.00 USD</span>
        </div>
      </div>
    </div>
    """
    res = evaluate_in_browser(html, "() => window.PaperTradingGuard.verifyEnvironment()")
    assert res["account_state"] == "LIVE_BROKER_CONNECTED"
    assert res["paper_trading_connected"] is False
    assert res["paper_trading_account_verified"] is False
    assert "CRITICAL SAFETY HALT" in res["error_message"]
    assert "INTERACTIVE BROKERS" in res["error_message"]

def test_scenario_4_unknown_broker_rejected():
    """Scenario 4: Unknown third-party broker must be rejected as UNKNOWN, never Paper Trading."""
    html = """
    <div id="header-toolbar-symbol-search">AAPL</div>
    <div data-name="trading-panel" style="display:block; width:800px; height:300px;">
      <div data-name="account-manager">
        <button data-name="account-select">CustomForexBrokerXYZ</button>
        <div role="tab" data-name="positions">Positions</div>
        <div data-name="account-balance">
          <span class="value-">10,000.00 USD</span>
        </div>
      </div>
    </div>
    """
    res = evaluate_in_browser(html, "() => window.PaperTradingGuard.verifyEnvironment()")
    assert res["account_state"] == "UNKNOWN"
    assert res["paper_trading_connected"] is False
    assert "not verified as TradingView Paper Trading" in res["error_message"]

def test_scenario_5_trading_panel_still_loading():
    """Scenario 5: TradingView panel open but still loading/rendering elements."""
    html = """
    <div id="header-toolbar-symbol-search">AAPL</div>
    <div data-name="trading-panel" style="display:block; width:800px; height:300px;">
      <div class="spinner-loading">Loading...</div>
    </div>
    """
    res = evaluate_in_browser(html, "() => window.PaperTradingGuard.verifyEnvironment()")
    assert res["account_state"] == "UNKNOWN"
    assert res["paper_trading_connected"] is False
    assert "loading account data" in res["error_message"].lower()

def test_scenario_6_trading_panel_collapsed():
    """Scenario 6: Trading panel collapsed with bottom tab indicating state."""
    # 6a: Bottom tab says Paper Trading while panel is hidden
    html_collapsed_paper = """
    <div id="header-toolbar-symbol-search">AAPL</div>
    <div class="bottom-widget-bar">
      <button data-name="trading">Paper Trading</button>
    </div>
    <div data-name="trading-panel" style="display:none; width:0px; height:0px;"></div>
    """
    res_paper = evaluate_in_browser(html_collapsed_paper, "() => window.PaperTradingGuard.verifyEnvironment()")
    assert res_paper["account_state"] == "PAPER_TRADING_CONNECTED"
    assert res_paper["paper_trading_connected"] is True

    # 6b: Bottom tab says Trading Panel while panel is hidden
    html_collapsed_trading = """
    <div id="header-toolbar-symbol-search">AAPL</div>
    <div class="bottom-widget-bar">
      <button data-name="trading">Trading Panel</button>
    </div>
    <div data-name="trading-panel" style="display:none; width:0px; height:0px;"></div>
    """
    res_trading = evaluate_in_browser(html_collapsed_trading, "() => window.PaperTradingGuard.verifyEnvironment()")
    assert res_trading["account_state"] == "UNKNOWN"
    assert "Trading Panel is collapsed" in res_trading["error_message"]

def test_scenario_7_account_manager_visible_with_balance_and_tabs():
    """Scenario 7: Account manager visible with all sub-tabs and balance parsing."""
    html = """
    <div id="header-toolbar-symbol-search">AAPL</div>
    <div data-name="account-manager" style="display:block; width:800px; height:300px;">
      <div data-name="account-manager-header">
        <button data-name="broker-select">Paper Trading</button>
      </div>
      <div class="account-tabs">
        <button data-name="positions">Positions</button>
        <button data-name="orders">Orders</button>
        <button data-name="order-history">Order history</button>
        <button data-name="balance-history">Balance history</button>
        <button data-name="trade-history">Trade history</button>
        <button data-name="analytics">Analytics</button>
      </div>
      <div data-name="account-summary">
        <span class="value-">Equity: $100,000.00</span>
      </div>
    </div>
    """
    res = evaluate_in_browser(html, "() => window.PaperTradingGuard.verifyEnvironment()")
    assert res["account_state"] == "PAPER_TRADING_CONNECTED"
    assert res["account_balance"] == 100000.0
    found_tabs = res["indicators"]["found_account_tabs"]
    assert len(found_tabs) >= 6
    for expected_tab in ["Positions", "Orders", "Order history", "Balance history", "Trade history", "Analytics"]:
        assert expected_tab in found_tabs

def test_scenario_8_dom_selectors_multiple_matches():
    """Scenario 8: DOM selectors evaluate all fallbacks and combine unique matches into a Set."""
    html = """
    <div class="positions-row" role="row">Row 1</div>
    <div class="positions-row" role="row">Row 2</div>
    <div data-name="positions-table">
      <div role="row">Row 3</div>
    </div>
    """
    res = evaluate_in_browser(html, """() => {
      const els = window.findTVAllElements([
        'div[data-name="positions-table"] div[role="row"]',
        'div.positions-row[role="row"]'
      ]);
      return { count: els.length, isSetCombined: els.length === 3 };
    }""")
    assert res["count"] == 3
    assert res["isSetCombined"] is True

def test_scenario_9_dom_changes_after_initial_load():
    """Scenario 9: Dynamic DOM update correctly transitions account verification state."""
    html = """
    <div id="header-toolbar-symbol-search">AAPL</div>
    <div id="trading-dock" class="bottom-widget-bar">
      <button data-name="trading">Trading Panel</button>
    </div>
    <div id="panel-container" data-name="trading-panel" style="display:none; width:0px; height:0px;"></div>
    """
    script = """async () => {
      // 1. Initial State: collapsed
      const initial = await window.PaperTradingGuard.verifyEnvironment();

      // 2. DOM Mutation: open panel and connect Paper Trading
      const dock = document.getElementById('trading-dock');
      dock.innerHTML = '<button data-name="trading">Paper Trading</button>';

      const container = document.getElementById('panel-container');
      container.style.display = 'block';
      container.style.width = '800px';
      container.style.height = '300px';
      container.innerHTML = `
        <div data-name="account-manager">
          <button data-name="account-select">Paper Trading</button>
          <button data-name="positions">Positions</button>
          <div data-name="account-balance"><span class="value-">$100,000.00</span></div>
        </div>
      `;

      // 3. Re-verify after DOM change
      const after = await window.PaperTradingGuard.verifyEnvironment();
      return { initial_state: initial.account_state, after_state: after.account_state, balance: after.account_balance };
    }"""
    res = evaluate_in_browser(html, script)
    assert res["initial_state"] == "UNKNOWN"
    assert res["after_state"] == "PAPER_TRADING_CONNECTED"
    assert res["balance"] == 100000.0

def test_scenario_10_websocket_and_stale_telemetry_sync():
    """Scenario 10: Telemetry sync and stale out-of-order telemetry rejection."""
    # 1. Update with latest verified timestamp
    t_new = datetime.now(timezone.utc).isoformat()
    telemetry_new = {
        "tv_tab_detected": True,
        "tv_login_detected": True,
        "broker_name": "Paper Trading by TradingView",
        "account_state": "PAPER_TRADING_CONNECTED",
        "account_balance": 100000.0,
        "last_verified_at": t_new,
        "current_symbol": "AAPL",
        "indicators": {
            "has_account_tabs": True,
            "has_balance": True
        }
    }
    bridge.update_status_from_extension(telemetry_new)
    assert bridge.extension_state["account_state"] == "PAPER_TRADING_CONNECTED"
    assert bridge.extension_state["account_balance"] == 100000.0
    assert bridge.extension_state["indicators"] is not None
    assert bridge.extension_state["indicators"]["has_account_tabs"] is True

    # 2. Receive stale telemetry with timestamp 10 seconds in the past -> MUST BE IGNORED
    t_old = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    telemetry_stale = {
        "tv_tab_detected": True,
        "tv_login_detected": True,
        "broker_name": "NONE",
        "account_state": "DISCONNECTED",
        "account_balance": 0.0,
        "last_verified_at": t_old,
        "current_symbol": "AAPL"
    }
    bridge.update_status_from_extension(telemetry_stale)
    # State should remain PAPER_TRADING_CONNECTED because stale packet was discarded
    assert bridge.extension_state["account_state"] == "PAPER_TRADING_CONNECTED"
    assert bridge.extension_state["account_balance"] == 100000.0

def test_scenario_11_overlapping_verification_single_flight():
    """Scenario 11: Overlapping concurrent verification requests reuse single in-flight promise."""
    html = """
    <div id="header-toolbar-symbol-search">AAPL</div>
    <div class="bottom-widget-bar">
      <button data-name="trading">Paper Trading</button>
    </div>
    <div data-name="trading-panel" style="display:block; width:800px; height:300px;">
      <div data-name="account-manager">
        <button data-name="account-select">Paper Trading</button>
        <div role="tab" data-name="positions">Positions</div>
        <div data-name="account-balance"><span class="value-">$100,000.00</span></div>
      </div>
    </div>
    """
    script = """async () => {
      // Simulate two concurrent overlapping verification promises
      const p1 = window.PaperTradingGuard.verifyEnvironment();
      const p2 = window.PaperTradingGuard.verifyEnvironment();
      const [res1, res2] = await Promise.all([p1, p2]);
      return {
        equal_state: res1.account_state === res2.account_state,
        state: res1.account_state
      };
    }"""
    res = evaluate_in_browser(html, script)
    assert res["equal_state"] is True
    assert res["state"] == "PAPER_TRADING_CONNECTED"

def test_scenario_12_account_switching_invalidation_and_lock():
    """Scenario 12: Account switching from Paper Trading to Live Broker immediately engages safety halt."""
    html = """
    <div id="header-toolbar-symbol-search">AAPL</div>
    <div id="account-container" data-name="trading-panel" style="display:block; width:800px; height:300px;">
      <div data-name="account-manager">
        <button id="broker-btn" data-name="account-select">Paper Trading</button>
        <div role="tab" data-name="positions">Positions</div>
        <div data-name="account-balance"><span class="value-">$100,000.00</span></div>
      </div>
    </div>
    """
    script = """async () => {
      // 1. Initial Paper Trading
      const initial = await window.PaperTradingGuard.verifyEnvironment();

      // 2. User switches account in UI to Tradovate (Live broker)
      const btn = document.getElementById('broker-btn');
      btn.innerText = 'Tradovate (Live Futures)';

      // 3. Verification must immediately recognize live broker
      const after = await window.PaperTradingGuard.verifyEnvironment();
      return {
        initial: initial.account_state,
        after: after.account_state,
        after_error: after.error_message
      };
    }"""
    res = evaluate_in_browser(html, script)
    assert res["initial"] == "PAPER_TRADING_CONNECTED"
    assert res["after"] == "LIVE_BROKER_CONNECTED"
    assert "CRITICAL SAFETY HALT" in res["after_error"]

@pytest.mark.anyio
async def test_execution_guard_blocks_non_paper_trading():
    """Safety check: Dispatching an order MUST be blocked unless PAPER_TRADING_CONNECTED."""
    signal_data = {
        "signal_id": "SIG-STRICT-TEST",
        "symbol": "AAPL",
        "direction": "BUY",
        "timestamp": "2026-11-06T12:00:00Z",
        "entry_price": 150.0,
        "stop_loss": 145.0,
        "take_profit": 160.0,
        "quantity": 1.0,
        "signal_score": 85.0,
        "risk_reward": 2.0,
        "demand_zone_low": 144.0,
        "demand_zone_high": 146.0,
        "timeframe": "5M"
    }
    SignalManager.create_signal(signal_data)

    # UNKNOWN state -> BLOCKED
    bridge.extension_state["connected"] = True
    bridge.extension_state["account_state"] = "UNKNOWN"
    res_unknown = await bridge.dispatch_signal_to_extension(signal_data)
    assert res_unknown["success"] is False
    assert res_unknown["status"] == "PAPER_TRADING_NOT_CONNECTED"

    # LIVE_BROKER_CONNECTED -> BLOCKED
    bridge.extension_state["account_state"] = "LIVE_BROKER_CONNECTED"
    res_live = await bridge.dispatch_signal_to_extension(signal_data)
    assert res_live["success"] is False
    assert res_live["status"] == "PAPER_TRADING_NOT_CONNECTED"

    # DISCONNECTED -> BLOCKED
    bridge.extension_state["account_state"] = "DISCONNECTED"
    res_disc = await bridge.dispatch_signal_to_extension(signal_data)
    assert res_disc["success"] is False
    assert res_disc["status"] == "PAPER_TRADING_NOT_CONNECTED"

    # PAPER_TRADING_CONNECTED -> PERMITTED
    bridge.extension_state["account_state"] = "PAPER_TRADING_CONNECTED"
    res_ok = await bridge.dispatch_signal_to_extension(signal_data)
    assert res_ok["success"] is True
    assert res_ok["status"] == "SENT_TO_EXTENSION"
