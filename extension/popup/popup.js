document.addEventListener('DOMContentLoaded', async () => {
  const backendEl = document.getElementById('backend-status');
  const tvTabEl = document.getElementById('tv-tab-status');
  const accountStateEl = document.getElementById('account-state-status');
  const brokerEl = document.getElementById('broker-status');
  const ptEl = document.getElementById('pt-status');
  const balanceEl = document.getElementById('balance-status');
  const symbolEl = document.getElementById('symbol-status');
  const lastVerifiedEl = document.getElementById('last-verified-status');
  const errorBoxEl = document.getElementById('error-message-box');
  const openDashBtn = document.getElementById('open-dashboard-btn');

  if (openDashBtn) {
    openDashBtn.addEventListener('click', () => {
      if (typeof chrome !== 'undefined' && chrome.tabs && chrome.tabs.create) {
        chrome.tabs.create({ url: 'http://127.0.0.1:8000' });
      } else {
        window.open('http://127.0.0.1:8000', '_blank');
      }
    });
  }

  // Query Backend Status
  try {
    const res = await fetch('http://127.0.0.1:8000/api/extension/status');
    if (res.ok) {
      const data = await res.json();
      backendEl.innerText = 'Connected';
      backendEl.className = 'val ok';
      
      tvTabEl.innerText = data.tv_tab_detected ? 'Detected' : 'Not Found';
      tvTabEl.className = `val ${data.tv_tab_detected ? 'ok' : 'err'}`;

      const state = data.account_state || (data.paper_trading_connected ? 'PAPER_TRADING_CONNECTED' : 'DISCONNECTED');
      if (accountStateEl) {
        accountStateEl.innerText = state;
        if (state === 'PAPER_TRADING_CONNECTED') {
          accountStateEl.className = 'val ok';
        } else if (state === 'LIVE_BROKER_CONNECTED') {
          accountStateEl.className = 'val err';
        } else {
          accountStateEl.className = 'val warn';
        }
      }

      if (brokerEl) {
        brokerEl.innerText = data.broker_name || 'None';
        if (state === 'PAPER_TRADING_CONNECTED') {
          brokerEl.className = 'val ok';
        } else if (state === 'LIVE_BROKER_CONNECTED') {
          brokerEl.className = 'val err';
        } else {
          brokerEl.className = 'val';
        }
      }

      ptEl.innerText = (state === 'PAPER_TRADING_CONNECTED') ? 'Connected' : 'Disconnected';
      ptEl.className = `val ${(state === 'PAPER_TRADING_CONNECTED') ? 'ok' : 'warn'}`;

      if (balanceEl) {
        if (data.account_balance !== null && data.account_balance !== undefined) {
          const num = Number(data.account_balance);
          balanceEl.innerText = isNaN(num) ? String(data.account_balance) : `$${num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
          balanceEl.className = 'val ok';
        } else {
          balanceEl.innerText = '-';
          balanceEl.className = 'val';
        }
      }

      symbolEl.innerText = data.current_symbol || 'None';

      if (lastVerifiedEl) {
        const ts = data.last_verified_at || data.last_heartbeat;
        lastVerifiedEl.innerText = ts ? new Date(ts).toLocaleTimeString() : 'Never';
      }

      if (errorBoxEl) {
        if (data.error_message) {
          errorBoxEl.innerText = data.error_message;
          errorBoxEl.style.display = 'block';
        } else {
          errorBoxEl.style.display = 'none';
        }
      }
    } else {
      backendEl.innerText = 'Error';
      backendEl.className = 'val err';
    }
  } catch (e) {
    backendEl.innerText = 'Offline';
    backendEl.className = 'val err';
  }
});
