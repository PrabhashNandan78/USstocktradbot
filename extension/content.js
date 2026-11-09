/**
 * TradingView Chrome Extension Content Script
 * Establishes communication with FastAPI backend, manages UI indicator,
 * coordinates orders, executes single-flight lifecycle verification,
 * and maintains continuous telemetry.
 */

(function () {
  console.log('[Antigravity Bridge] Content script initialized on TradingView.');

  const BACKEND_WS_URL = 'ws://127.0.0.1:8000/ws/extension';
  const BACKEND_HTTP_URL = 'http://127.0.0.1:8000';

  let ws = null;
  let isConnected = false;
  let retryCount = 0;
  let lastEnvironmentState = null;
  let lastKnownSymbol = null;
  let lastKnownUrl = window.location.href;

  // Verification Lifecycle & Single-Flight Cache State
  let cachedVerification = null;
  let cacheTimestamp = 0;
  const CACHE_TTL_MS = 5000;
  let inFlightPromise = null;
  let isVerifying = false;

  // Initialize UI Status Badge
  injectStatusBadge();

  // Connect to Backend WebSocket
  connectWebSocket();

  // Initial immediate verification
  triggerVerification(true);

  /**
   * Invalidates cached verification result
   */
  function invalidateCache() {
    cachedVerification = null;
    cacheTimestamp = 0;
  }

  /**
   * Single-flight verification runner with deduplication and timeout
   */
  async function runVerification(forceFresh = false) {
    const now = Date.now();
    if (!forceFresh && cachedVerification && (now - cacheTimestamp < CACHE_TTL_MS)) {
      return cachedVerification;
    }

    if (inFlightPromise) {
      return inFlightPromise;
    }

    isVerifying = true;

    // Timeout protection: prevent verification from hanging indefinitely in UNKNOWN
    inFlightPromise = Promise.race([
      window.PaperTradingGuard.verifyEnvironment(),
      new Promise((_, reject) => setTimeout(() => reject(new Error('Verification timed out after 4000ms')), 4000))
    ]).then((result) => {
      cachedVerification = result;
      cacheTimestamp = Date.now();
      
      // Invalidate if symbol changed
      if (result.current_symbol && result.current_symbol !== lastKnownSymbol) {
        lastKnownSymbol = result.current_symbol;
      }
      return result;
    }).catch((err) => {
      console.warn('[Antigravity Bridge] Verification error:', err);
      const fallbackResult = {
        account_state: 'UNKNOWN',
        tv_tab_detected: window.location.hostname.includes('tradingview.com'),
        tv_login_detected: false,
        username: null,
        current_symbol: lastKnownSymbol,
        raw_tv_symbol: null,
        exchange: null,
        paper_trading_connected: false,
        paper_trading_account_verified: false,
        broker_name: 'UNKNOWN',
        account_balance: null,
        error_message: `Verification error: ${err.message || err}`,
        last_verified_at: new Date().toISOString(),
        indicators: {
          tv_tab_detected: window.location.hostname.includes('tradingview.com'),
          bottom_tab_title: null,
          panel_visible: false,
          active_broker_text: null,
          has_account_tabs: false,
          found_account_tabs: [],
          has_balance: false,
          is_gallery_visible: false,
          account_state: 'UNKNOWN',
          error_message: err.message || 'Verification failed',
          matched_selectors: [],
          last_verified_at: new Date().toISOString()
        }
      };
      cachedVerification = fallbackResult;
      cacheTimestamp = Date.now();
      return fallbackResult;
    }).finally(() => {
      isVerifying = false;
      inFlightPromise = null;
    });

    return inFlightPromise;
  }

  /**
   * Triggers verification and broadcasts state to UI & Backend
   */
  async function triggerVerification(forceFresh = false) {
    try {
      const env = await runVerification(forceFresh);
      lastEnvironmentState = env;

      // Update Floating Badge
      updateStatusBadge(env);

      // Transmit full telemetry via WebSocket or HTTP fallback
      const telemetry = {
        type: 'HEARTBEAT',
        data: env
      };

      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(telemetry));
      } else {
        sendHttpFallback('/api/extension/heartbeat', env);
      }

      // Check and sync open positions if Paper Trading is confirmed
      if (env.paper_trading_connected && window.PositionTracker && window.PositionTracker.scrapePositions) {
        const positions = window.PositionTracker.scrapePositions();
        if (positions && positions.length > 0) {
          sendPositionSync(positions);
        }
      }
    } catch (e) {
      console.warn('[Antigravity Bridge] Monitoring error:', e);
    }
  }

  // Periodic Telemetry & Verification Loop (every 3000ms)
  setInterval(() => {
    // Check if URL changed (SPA navigation)
    if (window.location.href !== lastKnownUrl) {
      lastKnownUrl = window.location.href;
      invalidateCache();
      triggerVerification(true);
      return;
    }
    triggerVerification(false);
  }, 3000);

  // Targeted Event Listener: Invalidate cache on clicks to Trading Panel or account switcher
  document.addEventListener('click', (e) => {
    const target = e.target;
    if (!target) return;
    const isPanelClick = target.closest && (
      target.closest('[data-name="trading"]') ||
      target.closest('[data-name="trading-panel"]') ||
      target.closest('[data-name="account-manager"]') ||
      target.closest('[class*="bottomWidgetBar-"]') ||
      target.closest('[class*="accountManager-"]') ||
      target.closest('button[aria-label*="Trading" i]') ||
      target.closest('button[data-name="account-select"]') ||
      target.closest('button[data-name="broker-select"]')
    );
    if (isPanelClick) {
      invalidateCache();
      setTimeout(() => triggerVerification(true), 200);
    }
  }, { passive: true });

  // Debounced MutationObserver for relevant TradingView DOM mutations only
  let domDebounce = null;
  const observer = new MutationObserver((mutations) => {
    let isRelevant = false;
    for (const m of mutations) {
      if (m.target && m.target.nodeType === Node.ELEMENT_NODE) {
        const el = m.target;
        if (el.closest && (
          el.closest('[data-name="trading"]') ||
          el.closest('[data-name="trading-panel"]') ||
          el.closest('[data-name="account-manager"]') ||
          el.closest('[class*="bottomWidgetBar-"]') ||
          el.closest('[class*="accountManager-"]') ||
          el.closest('[id="header-toolbar-symbol-search"]') ||
          el.closest('[data-name="legend-series-item"]')
        )) {
          isRelevant = true;
          break;
        }
      }
    }

    if (isRelevant) {
      invalidateCache();
      if (domDebounce) clearTimeout(domDebounce);
      domDebounce = setTimeout(() => {
        triggerVerification(true);
      }, 350);
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });

  // Navigation Popstate listener
  window.addEventListener('popstate', () => {
    invalidateCache();
    triggerVerification(true);
  });

  function connectWebSocket() {
    try {
      ws = new WebSocket(BACKEND_WS_URL);

      ws.onopen = () => {
        isConnected = true;
        retryCount = 0;
        console.log('[Antigravity Bridge] Connected to backend WebSocket.');
        if (lastEnvironmentState) {
          ws.send(JSON.stringify({ type: 'HEARTBEAT', data: lastEnvironmentState }));
        } else {
          triggerVerification(true);
        }
      };

      ws.onmessage = async (event) => {
        try {
          const msg = JSON.parse(event.data);
          console.log('[Antigravity Bridge] Received message from backend:', msg);

          if (msg.type === 'EXECUTE_ORDER') {
            const execResult = await window.OrderExecutor.executeOrder(msg);
            
            const confirmationMsg = {
              type: 'EXECUTION_CONFIRMATION',
              data: execResult
            };

            if (ws && ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify(confirmationMsg));
            } else {
              sendHttpFallback('/api/extension/confirm-execution', execResult);
            }
          } else if (msg.type === 'KILL_SWITCH') {
            console.warn('[Antigravity Bridge] EMERGENCY KILL SWITCH RECEIVED!');
            showBanner('EMERGENCY STOP TRIGGERED: Orders halted by backend.', 'danger');
          }
        } catch (err) {
          console.error('[Antigravity Bridge] Error handling message:', err);
        }
      };

      ws.onerror = (err) => {
        console.warn('[Antigravity Bridge] WebSocket connection error:', err);
      };

      ws.onclose = () => {
        isConnected = false;
        updateStatusBadge(lastEnvironmentState);
        const delay = Math.min(10000, 1000 * Math.pow(1.5, retryCount));
        retryCount++;
        setTimeout(connectWebSocket, delay);
      };
    } catch (e) {
      console.warn('[Antigravity Bridge] Failed to initialize WebSocket:', e);
      setTimeout(connectWebSocket, 5000);
    }
  }

  function sendHttpFallback(endpoint, data) {
    fetch(`${BACKEND_HTTP_URL}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    }).catch(() => {});
  }

  function sendPositionSync(positions) {
    const payload = { positions: positions };
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'POSITIONS_SYNC', data: payload }));
    } else {
      sendHttpFallback('/api/extension/sync-positions', payload);
    }
  }

  // Visual status pill injected into TradingView chart
  function injectStatusBadge() {
    if (document.getElementById('antigravity-bridge-badge')) return;

    const badge = document.createElement('div');
    badge.id = 'antigravity-bridge-badge';
    badge.className = 'antigravity-badge-init';
    badge.innerHTML = `
      <div class="antigravity-badge-content">
        <span class="antigravity-badge-dot"></span>
        <span class="antigravity-badge-text">Trading Bot: Connecting...</span>
      </div>
    `;
    document.body.appendChild(badge);
  }

  function updateStatusBadge(env) {
    const badge = document.getElementById('antigravity-bridge-badge');
    if (!badge) return;

    const text = badge.querySelector('.antigravity-badge-text');

    if (!isConnected) {
      badge.className = 'antigravity-badge-disconnected';
      text.innerText = 'Trading Bot: Backend Offline';
      return;
    }

    if (!env) {
      badge.className = 'antigravity-badge-verifying';
      text.innerText = 'Trading Bot: Verification In Progress...';
      return;
    }

    if (env.account_state === 'LIVE_BROKER_CONNECTED') {
      badge.className = 'antigravity-badge-danger';
      text.innerText = 'Live Broker Detected — Execution Blocked';
      return;
    }

    if (env.account_state === 'PAPER_TRADING_CONNECTED') {
      badge.className = 'antigravity-badge-connected';
      const sym = env.current_symbol ? ` | ${env.current_symbol}` : '';
      const bal = env.account_balance ? ` ($${Number(env.account_balance).toLocaleString()})` : '';
      text.innerText = `Paper Trading Connected${sym}${bal}`;
      return;
    }

    if (env.account_state === 'DISCONNECTED') {
      badge.className = 'antigravity-badge-warning';
      text.innerText = 'Paper Trading Disconnected';
      return;
    }

    // UNKNOWN state
    badge.className = 'antigravity-badge-disconnected';
    if (env.error_message && env.error_message !== 'Verifying TradingView account state...') {
      text.innerText = `Verification Failed — ${env.error_message}`;
    } else {
      text.innerText = 'Trading Bot: Verification In Progress...';
    }
  }

  function showBanner(message, type = 'info') {
    const banner = document.createElement('div');
    banner.className = `antigravity-banner antigravity-banner-${type}`;
    banner.innerText = message;
    document.body.appendChild(banner);
    setTimeout(() => banner.remove(), 6000);
  }
})();
