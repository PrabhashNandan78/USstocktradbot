/**
 * Settings and Configuration Controller
 */
window.loadSettingsView = async function () {
  try {
    const data = await window.API.getSettings();
    const tvData = data.tradingview || {};
    const alpaca = data.alpaca || {};
    const telegram = data.telegram || {};
    const strategy = data.strategy || {};

    const tvUrlEl = document.getElementById('tv-service-url');
    if (tvUrlEl && tvData.service_url) {
      tvUrlEl.value = tvData.service_url;
    }

    if (alpaca.api_key_masked) {
      document.getElementById('alpaca-api-key').placeholder = `Configured: ${alpaca.api_key_masked}`;
    }
    if (alpaca.has_secret) {
      document.getElementById('alpaca-secret-key').placeholder = `Configured (Stored Locally)`;
    }
    if (alpaca.feed) {
      document.getElementById('alpaca-feed-select').value = alpaca.feed.toLowerCase();
    }

    if (telegram.bot_token_masked) {
      document.getElementById('telegram-bot-token').placeholder = `Configured: ${telegram.bot_token_masked}`;
    }
    if (telegram.chat_id) {
      document.getElementById('telegram-chat-id').value = telegram.chat_id;
    }

    if (strategy.min_score) document.getElementById('strat-min-score').value = strategy.min_score;
    if (strategy.min_rr) document.getElementById('strat-min-rr').value = strategy.min_rr;
    if (strategy.trading_quantity) document.getElementById('strat-quantity').value = strategy.trading_quantity;

    // Load Scanner Config
    const scCfg = await window.API.getScannerConfig();
    document.getElementById('sc-cfg-min-price').value = scCfg.min_price || 10.0;
    document.getElementById('sc-cfg-min-vol').value = scCfg.min_avg_volume || 100000;
    document.getElementById('sc-cfg-dollar-vol').value = scCfg.min_dollar_volume || 2000000;
    document.getElementById('sc-cfg-max-stocks').value = scCfg.max_stocks_to_analyze || 20;
    document.getElementById('sc-cfg-interval').value = scCfg.scan_interval_seconds || 300;
    document.getElementById('sc-cfg-watchlist').value = (scCfg.custom_watchlist || []).join(', ');

    // Load Telegram Subscribers
    if (window.renderTelegramSubscribers) {
      await window.renderTelegramSubscribers();
    }

  } catch (e) {
    console.error('Failed to load settings:', e);
  }
};

window.renderTelegramSubscribers = async function() {
  const tbody = document.getElementById('tg-subscribers-tbody');
  const activeCountEl = document.getElementById('tg-sub-active-count');
  const totalCountEl = document.getElementById('tg-sub-total-count');
  if (!tbody) return;

  try {
    const data = await window.API.getTelegramSubscribers();
    const subs = data.subscribers || [];
    if (activeCountEl) activeCountEl.innerText = data.active_count || 0;
    if (totalCountEl) totalCountEl.innerText = data.total_count || 0;

    if (subs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:var(--text-dim); padding:16px;">No subscribers registered yet. Message <code>/start</code> to your bot or save Chat ID to register.</td></tr>`;
      return;
    }

    tbody.innerHTML = subs.map(s => {
      const name = [s.first_name, s.last_name].filter(Boolean).join(' ') || (s.username ? `@${s.username}` : '-');
      const isActive = s.is_active === 1;
      const statusBadge = isActive
        ? `<span class="status-badge badge-connected">Active</span>`
        : `<span class="status-badge badge-disconnected">Inactive</span>`;
      const roleBadge = s.is_admin === 1
        ? `<span class="status-badge badge-connected">Admin</span>`
        : `<span class="status-badge badge-disconnected">Subscriber</span>`;
      const toggleAction = isActive
        ? `<button class="btn btn-secondary btn-sm" onclick="toggleSubStatus('${s.chat_id}', false)">Mute</button>`
        : `<button class="btn btn-primary btn-sm" onclick="toggleSubStatus('${s.chat_id}', true)">Enable</button>`;

      return `
        <tr>
          <td><code>${s.chat_id}</code></td>
          <td><strong>${name}</strong></td>
          <td>${roleBadge}</td>
          <td>${statusBadge}</td>
          <td style="font-size:11px; color:var(--text-dim);">${s.subscribed_at ? new Date(s.subscribed_at).toLocaleDateString() : '-'}</td>
          <td style="font-size:11px; color:var(--text-dim);">${s.last_delivery_at ? new Date(s.last_delivery_at).toLocaleTimeString() : 'Never'}</td>
          <td>${toggleAction}</td>
        </tr>
      `;
    }).join('');
  } catch (e) {
    console.error('Failed to load subscribers:', e);
  }
};

window.toggleSubStatus = async function(chatId, makeActive) {
  try {
    await window.API.toggleTelegramSubscriber(chatId, makeActive);
    await window.renderTelegramSubscribers();
  } catch (e) {
    alert(`Failed to update subscriber: ${e.message}`);
  }
};

document.addEventListener('DOMContentLoaded', () => {
  // TradingView Market Data Test & Save
  const alpacaTestBtn = document.getElementById('alpaca-test-btn');
  const alpacaSaveBtn = document.getElementById('alpaca-save-btn');
  const tvValReportBtn = document.getElementById('tv-val-report-btn');
  const alpacaStatusMsg = document.getElementById('alpaca-status-msg');

  if (alpacaTestBtn) {
    alpacaTestBtn.addEventListener('click', async () => {
      const tvUrlInput = document.getElementById('tv-service-url');
      const serviceUrl = tvUrlInput ? tvUrlInput.value.trim() : 'http://127.0.0.1:8002';

      alpacaTestBtn.disabled = true;
      alpacaStatusMsg.innerText = 'Testing TradingView market data connection & running automated validation...';
      alpacaStatusMsg.style.color = 'var(--text-muted)';

      try {
        const res = await window.API.testTradingView({ service_url: serviceUrl });
        if (res.success) {
          alpacaStatusMsg.innerText = `✅ ${res.message}`;
          alpacaStatusMsg.style.color = 'var(--color-green)';
        } else {
          alpacaStatusMsg.innerText = `❌ ${res.message}`;
          alpacaStatusMsg.style.color = 'var(--color-red)';
        }
      } catch (e) {
        alpacaStatusMsg.innerText = `❌ Error: ${e.message}`;
        alpacaStatusMsg.style.color = 'var(--color-red)';
      } finally {
        alpacaTestBtn.disabled = false;
      }
    });
  }

  if (alpacaSaveBtn) {
    alpacaSaveBtn.addEventListener('click', async () => {
      const tvUrlInput = document.getElementById('tv-service-url');
      const serviceUrl = tvUrlInput ? tvUrlInput.value.trim() : 'http://127.0.0.1:8002';

      alpacaSaveBtn.disabled = true;
      alpacaStatusMsg.innerText = 'Validating and saving TradingView settings...';
      try {
        const res = await window.API.saveTradingView({ service_url: serviceUrl });
        if (res.saved) {
          alpacaStatusMsg.innerText = `✅ Settings saved. Status: ${res.connection_test.status} (${res.connection_test.latency_ms}ms)`;
          alpacaStatusMsg.style.color = 'var(--color-green)';
          alert('TradingView market data settings saved successfully.');
        }
      } catch (e) {
        alpacaStatusMsg.innerText = `❌ Save failed: ${e.message}`;
        alpacaStatusMsg.style.color = 'var(--color-red)';
      } finally {
        alpacaSaveBtn.disabled = false;
      }
    });
  }

  if (tvValReportBtn) {
    tvValReportBtn.addEventListener('click', async () => {
      tvValReportBtn.disabled = true;
      alpacaStatusMsg.innerText = 'Generating automated Market Data Validation Report for AAPL, MSFT, NVDA, TSLA...';
      alpacaStatusMsg.style.color = 'var(--text-muted)';
      try {
        const report = await window.API.getValidationReport('5');
        const passBadge = report.validation_passed ? '✅ PASSED' : '❌ FAILED';
        alpacaStatusMsg.innerText = `${passBadge} | Completeness: ${report.candle_completeness_pct}% | Subscriptions: ${report.successful_subscriptions}/${report.total_symbols_requested} | Latency: ${report.data_latency_ms}ms | Feed: ${report.feed_source}`;
        alpacaStatusMsg.style.color = report.validation_passed ? 'var(--color-green)' : 'var(--color-red)';
      } catch (e) {
        alpacaStatusMsg.innerText = `❌ Report error: ${e.message}`;
        alpacaStatusMsg.style.color = 'var(--color-red)';
      } finally {
        tvValReportBtn.disabled = false;
      }
    });
  }

  // Telegram Test & Save
  const tgTestBtn = document.getElementById('telegram-test-btn');
  const tgSaveBtn = document.getElementById('telegram-save-btn');
  const tgStatusMsg = document.getElementById('telegram-status-msg');

  if (tgTestBtn) {
    tgTestBtn.addEventListener('click', async () => {
      const token = document.getElementById('telegram-bot-token').value.trim();
      const chat = document.getElementById('telegram-chat-id').value.trim();

      tgTestBtn.disabled = true;
      tgStatusMsg.innerText = 'Validating bot token and sending test delivery...';
      tgStatusMsg.style.color = 'var(--text-muted)';

      try {
        const res = await window.API.testTelegram({ bot_token: token, chat_id: chat });
        if (res.success) {
          tgStatusMsg.innerText = `✅ ${res.message}`;
          tgStatusMsg.style.color = 'var(--color-green)';
        } else {
          tgStatusMsg.innerText = `❌ ${res.message}`;
          tgStatusMsg.style.color = 'var(--color-red)';
        }
      } catch (e) {
        tgStatusMsg.innerText = `❌ Error: ${e.message}`;
        tgStatusMsg.style.color = 'var(--color-red)';
      } finally {
        tgTestBtn.disabled = false;
      }
    });
  }

  if (tgSaveBtn) {
    tgSaveBtn.addEventListener('click', async () => {
      const token = document.getElementById('telegram-bot-token').value.trim();
      const chat = document.getElementById('telegram-chat-id').value.trim();

      if (!token || !chat) {
        alert('Please enter both Telegram Bot Token and Chat ID.');
        return;
      }

      tgSaveBtn.disabled = true;
      try {
        const res = await window.API.saveTelegram({ bot_token: token, chat_id: chat });
        if (res.saved) {
          tgStatusMsg.innerText = `✅ Telegram settings saved successfully.`;
          tgStatusMsg.style.color = 'var(--color-green)';
          alert('Telegram credentials verified and saved.');
        }
      } catch (e) {
        tgStatusMsg.innerText = `❌ Save failed: ${e.message}`;
        tgStatusMsg.style.color = 'var(--color-red)';
      } finally {
        tgSaveBtn.disabled = false;
      }
    });
  }

  // Scanner Config Save
  const scSaveBtn = document.getElementById('scanner-save-cfg-btn');
  if (scSaveBtn) {
    scSaveBtn.addEventListener('click', async () => {
      const watchlistRaw = document.getElementById('sc-cfg-watchlist').value.trim();
      const watchlist = watchlistRaw ? watchlistRaw.split(',').map(s => s.trim().toUpperCase()).filter(Boolean) : [];

      const cfg = {
        min_price: parseFloat(document.getElementById('sc-cfg-min-price').value),
        min_avg_volume: parseFloat(document.getElementById('sc-cfg-min-vol').value),
        min_dollar_volume: parseFloat(document.getElementById('sc-cfg-dollar-vol').value),
        max_stocks_to_analyze: parseInt(document.getElementById('sc-cfg-max-stocks').value),
        scan_interval_seconds: parseInt(document.getElementById('sc-cfg-interval').value),
        custom_watchlist: watchlist,
        exclusions: ["SQQQ", "TQQQ", "SOXL", "SOXS"]
      };

      try {
        await window.API.saveScannerConfig(cfg);
        alert('Scanner settings saved.');
      } catch (e) {
        alert(`Failed to save scanner settings: ${e.message}`);
      }
    });
  }

  // Strategy Config Save
  const stratSaveBtn = document.getElementById('strategy-save-cfg-btn');
  if (stratSaveBtn) {
    stratSaveBtn.addEventListener('click', async () => {
      const cfg = {
        min_score: parseFloat(document.getElementById('strat-min-score').value),
        min_rr: parseFloat(document.getElementById('strat-min-rr').value),
        trading_quantity: parseFloat(document.getElementById('strat-quantity').value)
      };

      try {
        await window.API.saveStrategy(cfg);
        alert('Strategy parameters saved.');
      } catch (e) {
        alert(`Failed to save strategy settings: ${e.message}`);
      }
    });
  }

  // Telegram Multi-User Poll & Broadcast
  const tgPollBtn = document.getElementById('tg-poll-btn');
  if (tgPollBtn) {
    tgPollBtn.addEventListener('click', async () => {
      tgPollBtn.disabled = true;
      tgPollBtn.innerText = 'Checking...';
      try {
        const res = await window.API.pollTelegramUpdates();
        alert(`Checked Telegram updates: processed ${res.processed || 0} command(s).`);
        await window.renderTelegramSubscribers();
      } catch (e) {
        alert(`Polling failed: ${e.message}`);
      } finally {
        tgPollBtn.disabled = false;
        tgPollBtn.innerText = '📥 Check for New Bot Commands';
      }
    });
  }

  const tgBcBtn = document.getElementById('tg-broadcast-test-btn');
  const tgBcStatus = document.getElementById('tg-broadcast-status-msg');
  if (tgBcBtn) {
    tgBcBtn.addEventListener('click', async () => {
      tgBcBtn.disabled = true;
      if (tgBcStatus) tgBcStatus.innerText = 'Broadcasting...';
      try {
        const res = await window.API.broadcastTelegramTest("📢 Multi-User Broadcast Test: Trading bot alerts verified.");
        if (tgBcStatus) {
          tgBcStatus.innerText = `Sent to ${res.sent}/${res.total} active subscribers.`;
          tgBcStatus.style.color = 'var(--color-green)';
        }
        await window.renderTelegramSubscribers();
      } catch (e) {
        if (tgBcStatus) {
          tgBcStatus.innerText = `Broadcast failed: ${e.message}`;
          tgBcStatus.style.color = 'var(--color-red)';
        }
      } finally {
        tgBcBtn.disabled = false;
      }
    });
  }
});

