/**
 * Settings and Configuration Controller
 */
window.loadSettingsView = async function () {
  try {
    const data = await window.API.getSettings();
    const alpaca = data.alpaca || {};
    const telegram = data.telegram || {};
    const strategy = data.strategy || {};

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

  } catch (e) {
    console.error('Failed to load settings:', e);
  }
};

document.addEventListener('DOMContentLoaded', () => {
  // Alpaca Test & Save
  const alpacaTestBtn = document.getElementById('alpaca-test-btn');
  const alpacaSaveBtn = document.getElementById('alpaca-save-btn');
  const alpacaStatusMsg = document.getElementById('alpaca-status-msg');

  if (alpacaTestBtn) {
    alpacaTestBtn.addEventListener('click', async () => {
      const key = document.getElementById('alpaca-api-key').value.trim();
      const secret = document.getElementById('alpaca-secret-key').value.trim();
      const feed = document.getElementById('alpaca-feed-select').value;

      alpacaTestBtn.disabled = true;
      alpacaStatusMsg.innerText = 'Testing Alpaca connection...';
      alpacaStatusMsg.style.color = 'var(--text-muted)';

      try {
        const res = await window.API.testAlpaca({ api_key: key, secret_key: secret, feed: feed });
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
      const key = document.getElementById('alpaca-api-key').value.trim();
      const secret = document.getElementById('alpaca-secret-key').value.trim();
      const feed = document.getElementById('alpaca-feed-select').value;

      if (!key || !secret) {
        alert('Please enter both Alpaca API Key and Secret Key.');
        return;
      }

      alpacaSaveBtn.disabled = true;
      alpacaStatusMsg.innerText = 'Validating and saving credentials securely...';
      try {
        const res = await window.API.saveAlpaca({ api_key: key, secret_key: secret, feed: feed });
        if (res.saved) {
          alpacaStatusMsg.innerText = `✅ Credentials saved locally. Status: ${res.connection_test.status}`;
          alpacaStatusMsg.style.color = 'var(--color-green)';
          alert('Alpaca settings saved successfully.');
        }
      } catch (e) {
        alpacaStatusMsg.innerText = `❌ Save failed: ${e.message}`;
        alpacaStatusMsg.style.color = 'var(--color-red)';
      } finally {
        alpacaSaveBtn.disabled = false;
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
});
