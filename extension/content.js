/**
 * TradingView Chrome Extension Content Script
 * Establishes communication with FastAPI backend, manages UI indicator,
 * coordinates orders and continuous telemetry.
 */

(function () {
  console.log('[Antigravity Bridge] Content script initialized on TradingView.');

  const BACKEND_WS_URL = 'ws://127.0.0.1:8000/ws/extension';
  const BACKEND_HTTP_URL = 'http://127.0.0.1:8000';

  let ws = null;
  let isConnected = false;
  let retryCount = 0;
  let lastEnvironmentState = null;

  // Initialize UI Status Badge
  injectStatusBadge();

  // Connect to Backend WebSocket
  connectWebSocket();

  // Periodic Telemetry & Position Monitoring Loop
  setInterval(async () => {
    try {
      const env = await window.PaperTradingGuard.verifyEnvironment();
      lastEnvironmentState = env;

      // Update UI Status Badge
      updateStatusBadge(env);

      // Send telemetry via WebSocket or HTTP fallback
      const telemetry = {
        type: 'HEARTBEAT',
        data: env
      };

      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(telemetry));
      } else {
        sendHttpFallback('/api/extension/heartbeat', env);
      }

      // Check and sync open positions
      if (env.paper_trading_connected) {
        const positions = window.PositionTracker.scrapePositions();
        if (positions.length > 0) {
          sendPositionSync(positions);
        }
      }
    } catch (e) {
      console.warn('[Antigravity Bridge] Monitoring error:', e);
    }
  }, 3000);

  function connectWebSocket() {
    try {
      ws = new WebSocket(BACKEND_WS_URL);

      ws.onopen = () => {
        isConnected = true;
        retryCount = 0;
        console.log('[Antigravity Bridge] Connected to backend WebSocket.');
        if (lastEnvironmentState) {
          ws.send(JSON.stringify({ type: 'HEARTBEAT', data: lastEnvironmentState }));
        }
      };

      ws.onmessage = async (event) => {
        try {
          const msg = JSON.parse(event.data);
          console.log('[Antigravity Bridge] Received message from backend:', msg);

          if (msg.type === 'EXECUTE_ORDER') {
            const execResult = await window.OrderExecutor.executeOrder(msg);
            
            // Send execution confirmation back to backend
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

    const dot = badge.querySelector('.antigravity-badge-dot');
    const text = badge.querySelector('.antigravity-badge-text');

    if (!isConnected) {
      badge.className = 'antigravity-badge-disconnected';
      text.innerText = 'Trading Bot: Backend Offline';
      return;
    }

    if (env.broker_name && !env.broker_name.toLowerCase().includes('paper')) {
      badge.className = 'antigravity-badge-danger';
      text.innerText = `HALTED: Live Broker (${env.broker_name}) Detected!`;
      return;
    }

    if (!env.paper_trading_connected) {
      badge.className = 'antigravity-badge-warning';
      text.innerText = 'Trading Bot: Paper Trading Disconnected';
      return;
    }

    badge.className = 'antigravity-badge-connected';
    text.innerText = `Trading Bot: Active (Paper Trading) | ${env.current_symbol || 'N/A'}`;
  }

  function showBanner(message, type = 'info') {
    const banner = document.createElement('div');
    banner.className = `antigravity-banner antigravity-banner-${type}`;
    banner.innerText = message;
    document.body.appendChild(banner);
    setTimeout(() => banner.remove(), 6000);
  }
})();
