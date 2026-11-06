/**
 * Dashboard Controller & View Router
 */
document.addEventListener('DOMContentLoaded', () => {
  setupNavigation();
  setupKillSwitch();
  startOverviewPolling();
});

function setupNavigation() {
  const links = document.querySelectorAll('.nav-link');
  const sections = document.querySelectorAll('.view-section');
  const titleEl = document.getElementById('view-title');
  const descEl = document.getElementById('view-desc');

  const meta = {
    overview: { title: 'System Overview', desc: 'Live status, broker connection, and portfolio performance' },
    scanner: { title: 'Stock Scanner', desc: 'Automated multi-stock universe scanning with SMC filters' },
    signals: { title: 'Generated Signals', desc: 'Active trade candidates and execution pipeline' },
    'active-trades': { title: 'Active Positions', desc: 'Positions currently open in TradingView Paper Trading' },
    'trade-history': { title: 'Trade History', desc: 'Closed trade results, exit reasons, and realized P&L' },
    analytics: { title: 'Performance Analytics', desc: 'Win rate, profit factor, drawdown, and score correlations' },
    'test-center': { title: 'Integration Test Centre', desc: 'Run end-to-end and component tests with live audit log' },
    settings: { title: 'Settings & Credentials', desc: 'Configure Alpaca, Telegram, and execution parameters' }
  };

  links.forEach(link => {
    link.addEventListener('click', () => {
      const targetView = link.getAttribute('data-view');
      links.forEach(l => l.classList.remove('active'));
      link.classList.add('active');

      sections.forEach(sec => {
        sec.classList.remove('active');
        if (sec.id === `section-${targetView}`) {
          sec.classList.add('active');
        }
      });

      if (meta[targetView]) {
        titleEl.innerText = meta[targetView].title;
        descEl.innerText = meta[targetView].desc;
      }

      // Trigger view-specific loads
      if (targetView === 'scanner' && window.loadScannerView) window.loadScannerView();
      if (targetView === 'signals' && window.loadSignalsView) window.loadSignalsView();
      if (targetView === 'active-trades' && window.loadActiveTradesView) window.loadActiveTradesView();
      if (targetView === 'trade-history' && window.loadTradeHistoryView) window.loadTradeHistoryView();
      if (targetView === 'analytics' && window.loadAnalyticsView) window.loadAnalyticsView();
      if (targetView === 'test-center' && window.loadTestCenterView) window.loadTestCenterView();
      if (targetView === 'settings' && window.loadSettingsView) window.loadSettingsView();
    });
  });
}

function setupKillSwitch() {
  const killBtn = document.getElementById('global-kill-switch');
  if (!killBtn) return;

  killBtn.addEventListener('click', async () => {
    if (!confirm('⚠️ WARNING: Trigger EMERGENCY KILL SWITCH? This immediately halts all trading orders!')) return;
    try {
      const res = await window.API.triggerKillSwitch();
      alert(`🛑 Kill Switch Engaged: ${res.message}`);
    } catch (e) {
      alert(`Failed to trigger kill switch: ${e.message}`);
    }
  });

  const manualScanTop = document.getElementById('manual-scan-top-btn');
  if (manualScanTop) {
    manualScanTop.addEventListener('click', async () => {
      manualScanTop.disabled = true;
      manualScanTop.innerText = 'Scanning...';
      try {
        await window.API.scanNow();
        if (window.loadScannerView) window.loadScannerView();
        alert('Scan completed successfully.');
      } catch (e) {
        alert(`Scan failed: ${e.message}`);
      } finally {
        manualScanTop.disabled = false;
        manualScanTop.innerText = '🔍 Scan Universe Now';
      }
    });
  }

  const refreshBtn = document.getElementById('refresh-overview-btn');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', refreshOverview);
  }
}

async function refreshOverview() {
  try {
    // 1. Fetch Settings & Connection States
    const settings = await window.API.getSettings();
    const alpaca = settings.alpaca || {};
    const telegram = settings.telegram || {};

    const alpacaStatusEl = document.getElementById('ov-alpaca-status');
    const alpacaFeedEl = document.getElementById('ov-alpaca-feed');
    if (alpaca.status && alpaca.status.status === 'CONNECTED') {
      alpacaStatusEl.innerHTML = `<span class="status-badge badge-connected">Connected</span>`;
      alpacaFeedEl.innerText = `Feed: ${alpaca.feed.toUpperCase()} (${alpaca.feed === 'iex' ? 'Partial Tape' : 'Full SIP'})`;
    } else {
      alpacaStatusEl.innerHTML = `<span class="status-badge badge-disconnected">Not Connected</span>`;
      alpacaFeedEl.innerText = 'Feed: ' + (alpaca.feed ? alpaca.feed.toUpperCase() : 'IEX');
    }

    const tgStatusEl = document.getElementById('ov-telegram-status');
    const tgTimeEl = document.getElementById('ov-telegram-time');
    if (telegram.status && telegram.status.status === 'CONNECTED') {
      tgStatusEl.innerHTML = `<span class="status-badge badge-connected">Connected (@${telegram.status.bot_username})</span>`;
      tgTimeEl.innerText = `Chat: ${telegram.chat_id || 'Active'}`;
    } else {
      tgStatusEl.innerHTML = `<span class="status-badge badge-disconnected">Offline</span>`;
      tgTimeEl.innerText = 'Configure in Settings';
    }

    // 2. Fetch Extension State
    const ext = await window.API.getExtensionStatus();
    const extStatusEl = document.getElementById('ov-extension-status');
    const extSymEl = document.getElementById('ov-extension-symbol');
    const paperStatusEl = document.getElementById('ov-paper-status');
    const brokerNameEl = document.getElementById('ov-broker-name');

    if (ext.connected) {
      extStatusEl.innerHTML = `<span class="status-badge badge-connected">Connected</span>`;
      extSymEl.innerText = `Active Symbol: ${ext.current_symbol || 'Chart Ready'}`;
    } else {
      extStatusEl.innerHTML = `<span class="status-badge badge-disconnected">Offline</span>`;
      extSymEl.innerText = ext.installed ? 'Installed (No TV Tab)' : 'Not Installed';
    }

    if (ext.broker_name && !ext.broker_name.toLowerCase().includes('paper')) {
      paperStatusEl.innerHTML = `<span class="status-badge badge-danger">Live Broker (${ext.broker_name})</span>`;
      brokerNameEl.innerText = 'SAFETY HALT ENGAGED';
    } else if (ext.paper_trading_connected) {
      paperStatusEl.innerHTML = `<span class="status-badge badge-connected">Verified Active</span>`;
      brokerNameEl.innerText = ext.broker_name || 'Paper Trading by TradingView';
    } else {
      paperStatusEl.innerHTML = `<span class="status-badge badge-warning">Disconnected</span>`;
      brokerNameEl.innerText = 'Connect Paper Trading in Trading Panel';
    }

    // 3. Fetch Scanner Status
    const scanner = await window.API.getScannerStatus();
    const scStatusEl = document.getElementById('ov-scanner-status');
    const scDetailsEl = document.getElementById('ov-scanner-details');
    if (scanner.is_running) {
      scStatusEl.innerHTML = `<span class="status-badge badge-connected">Running</span>`;
    } else {
      scStatusEl.innerHTML = `<span class="status-badge badge-disconnected">Idle</span>`;
    }
    const qCount = scanner.results ? scanner.results.qualified_count || 0 : 0;
    const tCount = scanner.results ? scanner.results.filtered_count || 0 : 0;
    scDetailsEl.innerText = `${tCount} Analyzed • ${qCount} Qualified`;

    // 4. Fetch Active Positions
    const activePositions = await window.API.getActiveTrades();
    const activeCountEl = document.getElementById('ov-active-count');
    const unrealizedPnlEl = document.getElementById('ov-unrealized-pnl');
    activeCountEl.innerText = activePositions.length;

    let totalUnrealized = 0.0;
    activePositions.forEach(p => { totalUnrealized += (p.unrealized_pnl || 0.0); });
    unrealizedPnlEl.innerText = `Unrealized: ${totalUnrealized >= 0 ? '+' : ''}$${totalUnrealized.toFixed(2)}`;
    unrealizedPnlEl.className = totalUnrealized >= 0 ? 'card-subtext positive' : 'card-subtext negative';

    renderOverviewPositionsTable(activePositions);

    // 5. Fetch Realized Analytics
    const analytics = await window.API.getAnalytics();
    const netPnlEl = document.getElementById('ov-net-pnl');
    const winrateEl = document.getElementById('ov-winrate');
    netPnlEl.innerText = `${analytics.net_pnl >= 0 ? '+' : ''}$${analytics.net_pnl.toFixed(2)}`;
    netPnlEl.className = analytics.net_pnl >= 0 ? 'card-value positive' : 'card-value negative';
    winrateEl.innerText = `Win Rate: ${analytics.win_rate_pct.toFixed(1)}% (${analytics.winning_trades}W / ${analytics.losing_trades}L)`;

  } catch (e) {
    console.warn('Overview refresh failed:', e);
  }
}

function renderOverviewPositionsTable(positions) {
  const tbody = document.getElementById('overview-positions-tbody');
  if (!tbody) return;

  if (positions.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; color:var(--text-dim);">No active positions currently executing on TradingView Paper Trading.</td></tr>`;
    return;
  }

  tbody.innerHTML = positions.map(p => {
    const pnl = p.unrealized_pnl || 0.0;
    const pnlClass = pnl >= 0 ? 'positive' : 'negative';
    return `
      <tr>
        <td><strong>${p.symbol}</strong></td>
        <td><span class="status-badge badge-connected">${p.direction || 'BUY'}</span></td>
        <td>${p.quantity}</td>
        <td>$${p.entry_price.toFixed(2)}</td>
        <td>$${p.current_price.toFixed(2)}</td>
        <td class="negative">$${p.stop_loss.toFixed(2)}</td>
        <td class="positive">$${p.take_profit.toFixed(2)}</td>
        <td class="${pnlClass}">${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}</td>
        <td><span class="status-badge badge-connected">${p.status || 'OPEN'}</span></td>
      </tr>
    `;
  }).join('');
}

function startOverviewPolling() {
  refreshOverview();
  setInterval(refreshOverview, 5000);
}
