document.addEventListener('DOMContentLoaded', async () => {
  const backendEl = document.getElementById('backend-status');
  const tvTabEl = document.getElementById('tv-tab-status');
  const ptEl = document.getElementById('pt-status');
  const symbolEl = document.getElementById('symbol-status');
  const openDashBtn = document.getElementById('open-dashboard-btn');

  openDashBtn.addEventListener('click', () => {
    chrome.tabs.create({ url: 'http://127.0.0.1:8000' });
  });

  // Query Backend Status
  try {
    const res = await fetch('http://127.0.0.1:8000/api/extension/status');
    if (res.ok) {
      const data = await res.json();
      backendEl.innerText = 'Connected';
      backendEl.className = 'val ok';
      
      tvTabEl.innerText = data.tv_tab_detected ? 'Detected' : 'Not Found';
      tvTabEl.className = `val ${data.tv_tab_detected ? 'ok' : 'err'}`;

      ptEl.innerText = data.paper_trading_connected ? 'Connected' : 'Disconnected';
      ptEl.className = `val ${data.paper_trading_connected ? 'ok' : 'warn'}`;

      symbolEl.innerText = data.current_symbol || 'None';
    } else {
      backendEl.innerText = 'Error';
      backendEl.className = 'val err';
    }
  } catch (e) {
    backendEl.innerText = 'Offline';
    backendEl.className = 'val err';
  }
});
