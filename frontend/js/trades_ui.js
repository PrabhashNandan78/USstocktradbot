/**
 * Signals, Trades, History and Analytics Controller
 */

// 1. Signals View
window.loadSignalsView = async function () {
  try {
    const signals = await window.API.getSignals(50);
    const tbody = document.getElementById('signals-tbody');
    if (!tbody) return;

    if (signals.length === 0) {
      tbody.innerHTML = `<tr><td colspan="11" style="text-align:center; color:var(--text-dim);">No signals generated yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = signals.map(s => {
      const isSent = s.status === 'SENT_TO_EXTENSION' || s.status === 'EXECUTED';
      const badgeClass = s.status === 'EXECUTED' ? 'badge-connected' : (s.status === 'SENT_TO_EXTENSION' ? 'badge-warning' : (s.status === 'EXECUTION_FAILED' ? 'badge-danger' : 'badge-disconnected'));
      return `
        <tr>
          <td><code style="font-size:11px;">${s.id}</code></td>
          <td><strong>${s.symbol}</strong></td>
          <td><span class="status-badge badge-connected">BUY</span></td>
          <td>$${s.entry_price.toFixed(2)}</td>
          <td class="negative">$${s.stop_loss.toFixed(2)}</td>
          <td class="positive">$${s.take_profit.toFixed(2)}</td>
          <td>${s.risk_reward.toFixed(2)}:1</td>
          <td><span class="status-badge badge-connected">${s.signal_score.toFixed(1)}/100</span></td>
          <td><span class="status-badge ${badgeClass}">${s.status}</span></td>
          <td style="font-size:11px; color:var(--text-dim);">${new Date(s.timestamp).toLocaleTimeString()}</td>
          <td>
            ${isSent ? '<span style="color:var(--text-dim); font-size:12px;">Sent</span>' : `<button class="btn btn-primary btn-sm" onclick="dispatchSignalNow('${s.id}')">Send to TV</button>`}
          </td>
        </tr>
      `;
    }).join('');
  } catch (e) {
    console.error('Failed to load signals:', e);
  }
};

// 2. Active Trades View
window.loadActiveTradesView = async function () {
  try {
    const positions = await window.API.getActiveTrades();
    const tbody = document.getElementById('active-trades-tbody');
    if (!tbody) return;

    if (positions.length === 0) {
      tbody.innerHTML = `<tr><td colspan="10" style="text-align:center; color:var(--text-dim);">No open trades in TradingView Paper Trading.</td></tr>`;
      return;
    }

    tbody.innerHTML = positions.map(p => {
      const pnl = p.unrealized_pnl || 0.0;
      const pnlClass = pnl >= 0 ? 'positive' : 'negative';
      return `
        <tr>
          <td><strong>${p.symbol}</strong></td>
          <td><code style="font-size:11px;">${p.trade_id}</code></td>
          <td><span class="status-badge badge-connected">${p.direction || 'BUY'}</span></td>
          <td>${p.quantity}</td>
          <td>$${p.entry_price.toFixed(2)}</td>
          <td>$${p.current_price.toFixed(2)}</td>
          <td class="negative">$${p.stop_loss.toFixed(2)}</td>
          <td class="positive">$${p.take_profit.toFixed(2)}</td>
          <td class="${pnlClass}">${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}</td>
          <td style="font-size:11px; color:var(--text-dim);">${new Date(p.updated_at).toLocaleTimeString()}</td>
        </tr>
      `;
    }).join('');
  } catch (e) {
    console.error('Failed to load active trades:', e);
  }
};

// 3. Trade History View
window.loadTradeHistoryView = async function () {
  const symFilter = document.getElementById('history-filter-symbol');
  const symbol = symFilter ? symFilter.value.trim() : null;

  try {
    const history = await window.API.getTradeHistory(100, symbol);
    const tbody = document.getElementById('history-tbody');
    if (!tbody) return;

    if (history.length === 0) {
      tbody.innerHTML = `<tr><td colspan="12" style="text-align:center; color:var(--text-dim);">No closed trade history recorded.</td></tr>`;
      return;
    }

    tbody.innerHTML = history.map(t => {
      const pnl = t.net_pnl || 0.0;
      const pnlClass = pnl >= 0 ? 'positive' : 'negative';
      const durSec = t.holding_duration_seconds || 0;
      const hours = Math.floor(durSec / 3600);
      const mins = Math.floor((durSec % 3600) / 60);
      const secs = durSec % 60;
      const durStr = `${hours}h ${mins}m ${secs}s`;

      return `
        <tr>
          <td><code style="font-size:11px;">${t.id}</code></td>
          <td><strong>${t.symbol}</strong></td>
          <td><span class="status-badge badge-connected">${t.direction}</span></td>
          <td>$${(t.executed_entry || t.requested_entry).toFixed(2)}</td>
          <td>$${(t.actual_exit_price || 0.0).toFixed(2)}</td>
          <td>${t.quantity}</td>
          <td><span class="status-badge badge-disconnected">${t.exit_reason || 'MANUAL'}</span></td>
          <td>$${(t.gross_pnl || 0.0).toFixed(2)}</td>
          <td class="${pnlClass}">${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}</td>
          <td class="${pnlClass}">${(t.return_pct || 0.0).toFixed(2)}%</td>
          <td style="font-size:11px;">${durStr}</td>
          <td style="font-size:11px; color:var(--text-dim);">${t.closed_at ? new Date(t.closed_at).toLocaleString() : '-'}</td>
        </tr>
      `;
    }).join('');
  } catch (e) {
    console.error('Failed to load trade history:', e);
  }
};

// 4. Performance Analytics View
window.loadAnalyticsView = async function () {
  try {
    const a = await window.API.getAnalytics();
    
    document.getElementById('an-winrate').innerText = `${a.win_rate_pct.toFixed(1)}%`;
    document.getElementById('an-win-loss-count').innerText = `${a.winning_trades} Wins / ${a.losing_trades} Losses (Total: ${a.total_trades})`;
    
    document.getElementById('an-profit-factor').innerText = a.profit_factor.toFixed(2);
    
    const netEl = document.getElementById('an-net-pnl');
    netEl.innerText = `${a.net_pnl >= 0 ? '+' : ''}$${a.net_pnl.toFixed(2)}`;
    netEl.className = a.net_pnl >= 0 ? 'card-value positive' : 'card-value negative';
    
    document.getElementById('an-gross-pnl').innerText = `Gross: $${a.total_gross_pnl.toFixed(2)} | Fees: $${a.total_fees.toFixed(2)}`;
    document.getElementById('an-max-dd').innerText = `-$${a.max_drawdown.toFixed(2)}`;
    document.getElementById('an-avg-win').innerText = `+$${a.average_profit.toFixed(2)}`;
    document.getElementById('an-avg-loss').innerText = `-$${a.average_loss.toFixed(2)}`;

    // Render By Stock Table
    const stockTbody = document.getElementById('analytics-by-stock-tbody');
    const stocks = Object.keys(a.by_stock || {});
    if (stocks.length === 0) {
      stockTbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-dim);">No closed trades recorded.</td></tr>`;
    } else {
      stockTbody.innerHTML = stocks.map(s => {
        const item = a.by_stock[s];
        return `
          <tr>
            <td><strong>${s}</strong></td>
            <td>${item.trades}</td>
            <td>${item.win_rate}%</td>
            <td class="${item.net_pnl >= 0 ? 'positive' : 'negative'}">${item.net_pnl >= 0 ? '+' : ''}$${item.net_pnl.toFixed(2)}</td>
          </tr>
        `;
      }).join('');
    }

    // Render By Score Tier Table
    const scoreTbody = document.getElementById('analytics-by-score-tbody');
    const tiers = Object.keys(a.by_score_tier || {});
    scoreTbody.innerHTML = tiers.map(t => {
      const item = a.by_score_tier[t];
      return `
        <tr>
          <td><strong>Tier ${t}</strong></td>
          <td>${item.count}</td>
          <td>${item.wins}</td>
          <td class="${item.net_pnl >= 0 ? 'positive' : 'negative'}">${item.net_pnl >= 0 ? '+' : ''}$${item.net_pnl.toFixed(2)}</td>
        </tr>
      `;
    }).join('');

  } catch (e) {
    console.error('Failed to load analytics:', e);
  }
};

document.addEventListener('DOMContentLoaded', () => {
  const refreshHistory = document.getElementById('refresh-history-btn');
  if (refreshHistory) refreshHistory.addEventListener('click', window.loadTradeHistoryView);

  const searchBtn = document.getElementById('history-search-btn');
  if (searchBtn) searchBtn.addEventListener('click', window.loadTradeHistoryView);

  const refreshSignals = document.getElementById('refresh-signals-btn');
  if (refreshSignals) refreshSignals.addEventListener('click', window.loadSignalsView);

  const refreshActive = document.getElementById('refresh-active-trades-btn');
  if (refreshActive) refreshActive.addEventListener('click', window.loadActiveTradesView);
});
