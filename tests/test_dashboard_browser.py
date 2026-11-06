import time
import threading
import uvicorn
import pytest
from playwright.sync_api import sync_playwright

from backend.main import app
from backend.database import init_db

class ServerThread(threading.Thread):
    def __init__(self, host="127.0.0.1", port=8001):
        super().__init__()
        self.host = host
        self.port = port
        self.config = uvicorn.Config(app, host=self.host, port=self.port, log_level="warning")
        self.server = uvicorn.Server(self.config)
        self.daemon = True

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True

def test_dashboard_ui_playwright():
    init_db()
    server = ServerThread(port=8001)
    server.start()
    time.sleep(1.5) # Allow server to bind

    try:
        with sync_playwright() as p:
            # Check if chromium is available
            browser = None
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as e:
                pytest.skip(f"Playwright Chromium browser binary not installed: {e}")

            page = browser.new_page()
            page.on("dialog", lambda dialog: dialog.accept())
            page.goto("http://127.0.0.1:8001")
            
            # 1. Verify Title & Sidebar
            assert "Antigravity Multi-Stock Bullish Trading System" in page.title()
            page.wait_for_selector(".logo-title")
            assert "Antigravity Bot" in page.locator(".logo-title").inner_text()

            # 2. Check Cards
            page.wait_for_selector("#ov-alpaca-status")
            page.wait_for_selector("#ov-extension-status")
            page.wait_for_selector("#ov-paper-status")

            # 3. Navigate to Integration Test Centre
            test_center_nav = page.locator('a[data-view="test-center"]')
            test_center_nav.click()
            page.wait_for_selector("#test-btn-e2e")

            # 4. Click Test End-to-End Workflow button
            page.click("#test-btn-e2e")
            
            # Wait for output in live console
            page.wait_for_function('document.getElementById("test-console-output").innerText.includes("Full End-to-End Workflow Simulation")')
            console_text = page.locator("#test-console-output").inner_text()
            assert "overall_success" in console_text

            browser.close()
    finally:
        server.stop()
