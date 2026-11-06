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

  document.getElementById('sc-total-candidates').innerText = res.total_universe_count || 0;
  document.getElementById('sc-filtered-count').innerText = res.filtered_count || 0;
  document.getElementById('sc-qualified-count').innerText = res.qualified_count || 0;
  document.getElementById('sc-rejected-count').innerText = (res.rejections || []).length;

  // Render Qualified Setups Table
  const qualTbody = document.getElementById('scanner-qualified-tbody');
  const qualified = res.qualified_stocks || [];
  if (qualified.length === 0) {
    qualTbody.innerHTML = `<tr><td colspan="9" style="text-align:center; color:var(--text-dim);">No qualified setups currently detected. Click 'Scan Once Now' to evaluate.</td></tr>`;
  } else {
    qualTbody.innerHTML = qualified.map(s => {
      return `
        <tr>
          <td><strong>${s.symbol}</strong></td>
          <td><span class="status-badge badge-connected">BUY</span></td>
          <td>$${s.entry_price.toFixed(2)}</td>
          <td class="negative">$${s.stop_loss.toFixed(2)}</td>
          <td class="positive">$${s.take_profit.toFixed(2)}</td>
          <td><strong>${s.risk_reward.toFixed(2)}:1</strong></td>
          <td><span class="status-badge badge-connected">${s.signal_score.toFixed(1)}/100</span></td>
          <td>[${s.demand_zone_low}, ${s.demand_zone_high}]</td>
          <td>
            <button class="btn btn-primary btn-sm" onclick="dispatchSignalNow('${s.signal_id}')">Execute in TV</button>
          </td>
        </tr>
      `;
    }).join('');
  }

  // Render Rejections Table
  const rejTbody = document.getElementById('scanner-rejections-tbody');
  const rejections = res.rejections || [];
  if (rejections.length === 0) {
    rejTbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-dim);">No rejection telemetry recorded.</td></tr>`;
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
