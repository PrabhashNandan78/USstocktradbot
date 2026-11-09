/**
 * Stock Scanner Controller
 */
window.loadScannerView = async function () {
  try {
    const status = await window.API.getScannerStatus();
    renderScannerStatus(status);
  } catch (e) {
    console.error('Failed to load scanner view:', e);
  }
};

document.addEventListener('DOMContentLoaded', () => {
  const startBtn = document.getElementById('scanner-start-btn');
  const stopBtn = document.getElementById('scanner-stop-btn');
  const nowBtn = document.getElementById('scanner-now-btn');

  if (startBtn) {
    startBtn.addEventListener('click', async () => {
      try {
        await window.API.startScanner();
        window.loadScannerView();
      } catch (e) {
        alert(`Error starting scanner: ${e.message}`);
      }
    });
  }

  if (stopBtn) {
    stopBtn.addEventListener('click', async () => {
      try {
        await window.API.stopScanner();
        window.loadScannerView();
      } catch (e) {
        alert(`Error pausing scanner: ${e.message}`);
      }
    });
  }

  if (nowBtn) {
    nowBtn.addEventListener('click', async () => {
      nowBtn.disabled = true;
      nowBtn.innerText = 'Scanning...';
      try {
        const res = await window.API.scanNow();
        renderScannerStatus({ is_running: false, results: res.results });
      } catch (e) {
        alert(`Scan error: ${e.message}`);
      } finally {
        nowBtn.disabled = false;
        nowBtn.innerText = '⚡ Scan Once Now';
      }
    });
  }
});

function renderScannerStatus(status) {
  const res = status.results || {};
  document.getElementById('sc-status-text').innerText = status.is_running ? 'Running (Periodic)' : 'Idle';
  document.getElementById('sc-last-scan').innerText = res.last_scan_time ? new Date(res.last_scan_time).toLocaleTimeString() : 'Never';

  // Feed transparency & market session banner (accurate labeling; no unverified SIP claims)
  const feedBanner = document.getElementById('scanner-feed-banner');
  if (feedBanner && res.feed_metadata) {
    feedBanner.style.display = 'block';
    const hasWarning = !!res.feed_metadata.warning;
    const mStatus = res.market_status || (res.feed_metadata && res.feed_metadata.market_status) || 'CLOSED';

    if (hasWarning) {
      feedBanner.style.background = 'rgba(239, 68, 68, 0.15)';
      feedBanner.style.border = '1px solid #ef4444';
      feedBanner.style.color = '#fca5a5';
      feedBanner.innerHTML = `⚠️ <strong>TradingView Market Data Warning</strong> — ${res.feed_metadata.warning}.`;
    } else if (mStatus === 'OPEN') {
      feedBanner.style.background = 'rgba(16, 185, 129, 0.15)';
      feedBanner.style.border = '1px solid #10b981';
      feedBanner.style.color = '#6ee7b7';
      feedBanner.innerHTML = `✅ <strong>TradingView Market Data Connected</strong> — US Regular Trading Session Active. Real-time quotes verified for order execution.`;
    } else {
      feedBanner.style.background = 'rgba(245, 158, 11, 0.15)';
      feedBanner.style.border = '1px solid #f59e0b';
      feedBanner.style.color = '#fcd34d';
      feedBanner.innerHTML = `🌙 <strong>TradingView Market Data Connected (Market ${mStatus})</strong> — Historical scanning active. Completed candles evaluated. Live order execution paused until market open.`;
    }
  }

  const acct = res.accounting || {};
  document.getElementById('sc-total-candidates').innerText = acct.universe_candidates_count || res.total_universe_count || 0;
  document.getElementById('sc-filtered-count').innerText = acct.liquidity_passed_count !== undefined ? `${acct.liquidity_passed_count} Passed` : (res.filtered_count || 0);
  document.getElementById('sc-qualified-count').innerText = acct.strategy_qualified_count !== undefined ? `${acct.strategy_qualified_count} Qualified` : (res.qualified_count || 0);
  document.getElementById('sc-rejected-count').innerText = (res.rejections || []).length;

  // Render accounting breakdown pills with fine-grained failure categories
  const breakdownContainer = document.getElementById('scanner-accounting-breakdown');
  if (breakdownContainer && res.rejection_reasons_summary) {
    const s = res.rejection_reasons_summary;
    breakdownContainer.innerHTML = `
      <div style="display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; font-size:11px;">
        <span class="status-badge badge-warning">Price &lt; Min: ${s.price_below_min || 0}</span>
        <span class="status-badge badge-warning">Volume &lt; Min: ${s.volume_below_min || 0}</span>
        <span class="status-badge badge-warning">Dollar Vol &lt; Min: ${s.dollar_volume_below_min || 0}</span>
        <span class="status-badge badge-disconnected">Missing Quotes: ${s.missing_quotes || 0}</span>
        <span class="status-badge badge-disconnected">Stale Quotes: ${s.stale_quotes || 0}</span>
        <span class="status-badge badge-disconnected">Invalid Quotes: ${s.invalid_quotes || 0}</span>
        <span class="status-badge badge-disconnected">Provider Errors: ${s.provider_errors || 0}</span>
        <span class="status-badge badge-disconnected">Resolution Errors: ${s.symbol_resolution_failures || 0}</span>
        <span class="status-badge badge-disconnected">Insufficient Bars: ${s.insufficient_bars || 0}</span>
        <span class="status-badge badge-disconnected">Strategy Unmet: ${s.strategy_unmet || 0}</span>
        <span class="status-badge badge-warning">Duplicates Prevented: ${s.duplicate_zone || 0}</span>
      </div>
    `;
  }

  // Render Qualified Setups Table
  const qualTbody = document.getElementById('scanner-qualified-tbody');
  const qualified = res.qualified_stocks || [];
  if (qualified.length === 0) {
    qualTbody.innerHTML = `<tr><td colspan="9" style="text-align:center; color:var(--text-dim); padding:20px;">No qualified setups currently detected. Click 'Scan Once Now' to evaluate.</td></tr>`;
  } else {
    qualTbody.innerHTML = qualified.map(s => {
      return `
        <tr>
          <td><strong>${s.symbol}</strong></td>
          <td><span class="status-badge ${s.is_live_executable ? 'badge-connected' : 'badge-warning'}">${s.is_live_executable ? 'LIVE BUY' : 'HISTORICAL'}</span></td>
          <td>$${s.entry_price.toFixed(2)}</td>
          <td class="negative">$${s.stop_loss.toFixed(2)}</td>
          <td class="positive">$${s.take_profit.toFixed(2)}</td>
          <td><strong>${s.risk_reward.toFixed(2)}:1</strong></td>
          <td><span class="status-badge badge-connected">${s.signal_score.toFixed(1)}/100</span></td>
          <td>[${s.demand_zone_low}, ${s.demand_zone_high}]</td>
          <td>
            ${s.is_live_executable
              ? `<button class="btn btn-primary btn-sm" onclick="dispatchSignalNow('${s.signal_id}')">Execute in TV</button>`
              : `<button class="btn btn-secondary btn-sm" onclick="dispatchSignalNow('${s.signal_id}')" title="${s.execution_blocked_reason || 'Execution disabled when market closed'}">Execute (Paused)</button>`
            }
          </td>
        </tr>
      `;
    }).join('');
  }

  // Render Rejections Table
  const rejTbody = document.getElementById('scanner-rejections-tbody');
  const rejections = res.rejections || [];
  if (rejections.length === 0) {
    rejTbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-dim); padding:16px;">No rejection telemetry recorded.</td></tr>`;
  } else {
    rejTbody.innerHTML = rejections.slice(0, 50).map(r => {
      return `
        <tr>
          <td><strong>${r.symbol}</strong></td>
          <td><span class="status-badge badge-disconnected">REJECTED</span></td>
          <td>${r.score !== undefined ? r.score : '-'}</td>
          <td style="color:var(--text-muted);">${r.reason}</td>
        </tr>
      `;
    }).join('');
  }
}

window.dispatchSignalNow = async function (signalId) {
  try {
    const res = await window.API.dispatchSignal(signalId);
    alert(`Signal dispatched: ${res.message || 'Queued for TradingView Paper Trading'}`);
    window.loadScannerView();
  } catch (e) {
    alert(`Dispatch failed: ${e.message}`);
  }
};

