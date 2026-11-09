/**
 * Centralized API Communication Client
 */
const API = {
  async get(endpoint) {
    const res = await fetch(endpoint);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  },

  async post(endpoint, data = {}) {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!res.ok) {
      const errText = await res.text();
      try {
        const parsed = JSON.parse(errText);
        throw new Error(parsed.detail || parsed.message || `HTTP ${res.status}`);
      } catch (e) {
        throw new Error(errText || `HTTP ${res.status}`);
      }
    }
    return await res.json();
  },

  // Settings
  getSettings() { return this.get('/api/settings/'); },
  getMarketStatus() { return this.get('/api/market/status'); },
  getMarketDiagnostics() { return this.get('/api/market/diagnostics'); },
  testTradingView(cfg) { return this.post('/api/settings/tradingview/test', cfg); },
  saveTradingView(cfg) { return this.post('/api/settings/tradingview/save', cfg); },
  getValidationReport(timeframe = '5') { return this.get(`/api/settings/tradingview/validation-report?timeframe=${timeframe}`); },
  testAlpaca(cfg) { return this.post('/api/settings/alpaca/test', cfg); },
  saveAlpaca(cfg) { return this.post('/api/settings/alpaca/save', cfg); },
  testTelegram(cfg) { return this.post('/api/settings/telegram/test', cfg); },
  saveTelegram(cfg) { return this.post('/api/settings/telegram/save', cfg); },
  saveStrategy(cfg) { return this.post('/api/settings/strategy/save', cfg); },

  // Scanner
  getScannerConfig() { return this.get('/api/scanner/config'); },
  saveScannerConfig(cfg) { return this.post('/api/scanner/config', cfg); },
  getScannerStatus() { return this.get('/api/scanner/status'); },
  startScanner() { return this.post('/api/scanner/start'); },
  stopScanner() { return this.post('/api/scanner/stop'); },
  scanNow() { return this.post('/api/scanner/scan-now'); },

  // Signals
  getSignals(limit = 50) { return this.get(`/api/signals/?limit=${limit}`); },
  dispatchSignal(signalId) { return this.post(`/api/signals/${signalId}/dispatch`); },

  // Trades & Analytics
  getActiveTrades() { return this.get('/api/trades/active'); },
  getTradeHistory(limit = 100, symbol = null, source = 'TRADINGVIEW_PAPER') {
    let q = `?limit=${limit}`;
    if (symbol) q += `&symbol=${encodeURIComponent(symbol)}`;
    if (source) q += `&source=${encodeURIComponent(source)}`;
    return this.get(`/api/trades/history${q}`);
  },
  getAnalytics(source = 'TRADINGVIEW_PAPER') {
    const q = source ? `?source=${encodeURIComponent(source)}` : '';
    return this.get(`/api/trades/analytics${q}`);
  },
  triggerKillSwitch() { return this.post('/api/trades/kill-switch'); },

  // Telegram Multi-User Subscribers
  getTelegramSubscribers() { return this.get('/api/settings/telegram/subscribers'); },
  broadcastTelegramTest(msg = null) { return this.post('/api/settings/telegram/broadcast', { message: msg }); },
  toggleTelegramSubscriber(chatId, isActive) { return this.post('/api/settings/telegram/toggle-subscriber', { chat_id: chatId, is_active: isActive }); },
  pollTelegramUpdates() { return this.post('/api/settings/telegram/poll'); },

  // Extension status
  getExtensionStatus() { return this.get('/api/extension/status'); },

  // Integration Tests
  testSuite(suite) { return this.post(`/api/tests/${suite}`); },
  getTestHistory() { return this.get('/api/tests/history'); }
};

window.API = API;

