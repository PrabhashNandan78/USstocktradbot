/**
 * Integration Test Centre Controller
 */
window.loadTestCenterView = async function () {
  try {
    const history = await window.API.getTestHistory();
    renderTestHistoryTable(history);
  } catch (e) {
    console.error('Failed to load test history:', e);
  }
};

document.addEventListener('DOMContentLoaded', () => {
  const consoleEl = document.getElementById('test-console-output');

  function logConsole(msg, isAppend = false) {
    if (!consoleEl) return;
    const time = new Date().toLocaleTimeString();
    const line = `[${time}] ${msg}\n`;
    if (isAppend) {
      consoleEl.textContent += line;
    } else {
      consoleEl.textContent = line;
    }
    consoleEl.scrollTop = consoleEl.scrollHeight;
  }

  // 1. Test TradingView Market Data
  const btnAlpaca = document.getElementById('test-btn-alpaca');
  if (btnAlpaca) {
    btnAlpaca.addEventListener('click', async () => {
      btnAlpaca.disabled = true;
      logConsole('Executing TradingView Market Data Connectivity & OHLCV Validation Test...');
      try {
        const res = await window.API.testSuite('tradingview');
        logConsole(JSON.stringify(res, null, 2), true);
        window.loadTestCenterView();
      } catch (e) {
        logConsole(`❌ Error executing TradingView test: ${e.message}`, true);
      } finally {
        btnAlpaca.disabled = false;
      }
    });
  }

  // 1b. Test Validation Report
  const btnValReport = document.getElementById('test-btn-validation-report');
  if (btnValReport) {
    btnValReport.addEventListener('click', async () => {
      btnValReport.disabled = true;
      logConsole('Generating Comprehensive Data Validation Report (AAPL, MSFT, NVDA, TSLA across 5M bars)...');
      try {
        const res = await window.API.getValidationReport('5');
        logConsole(JSON.stringify(res, null, 2), true);
      } catch (e) {
        logConsole(`❌ Error generating validation report: ${e.message}`, true);
      } finally {
        btnValReport.disabled = false;
      }
    });
  }

  // 2. Test Telegram
  const btnTelegram = document.getElementById('test-btn-telegram');
  if (btnTelegram) {
    btnTelegram.addEventListener('click', async () => {
      btnTelegram.disabled = true;
      logConsole('Executing Telegram Bot API & Delivery Test...');
      try {
        const res = await window.API.testSuite('telegram');
        logConsole(JSON.stringify(res, null, 2), true);
        window.loadTestCenterView();
      } catch (e) {
        logConsole(`❌ Error executing Telegram test: ${e.message}`, true);
      } finally {
        btnTelegram.disabled = false;
      }
    });
  }

  // 3. Test Extension
  const btnExtension = document.getElementById('test-btn-extension');
  if (btnExtension) {
    btnExtension.addEventListener('click', async () => {
      btnExtension.disabled = true;
      logConsole('Executing Chrome Extension Telemetry & Heartbeat Test...');
      try {
        const res = await window.API.testSuite('extension');
        logConsole(JSON.stringify(res, null, 2), true);
        window.loadTestCenterView();
      } catch (e) {
        logConsole(`❌ Error executing Extension test: ${e.message}`, true);
      } finally {
        btnExtension.disabled = false;
      }
    });
  }

  // 4. Test Paper Trading
  const btnPaper = document.getElementById('test-btn-paper');
  if (btnPaper) {
    btnPaper.addEventListener('click', async () => {
      btnPaper.disabled = true;
      logConsole('Inspecting TradingView DOM & Paper Trading Environment...');
      try {
        const res = await window.API.testSuite('paper-trading');
        logConsole(JSON.stringify(res, null, 2), true);
        window.loadTestCenterView();
      } catch (e) {
        logConsole(`❌ Error inspecting Paper Trading: ${e.message}`, true);
      } finally {
        btnPaper.disabled = false;
      }
    });
  }

  // 5. Test End-to-End Workflow
  const btnE2E = document.getElementById('test-btn-e2e');
  if (btnE2E) {
    btnE2E.addEventListener('click', async () => {
      btnE2E.disabled = true;
      logConsole('⚡ Launching Complete Multi-Stock End-to-End Workflow Simulation...');
      logConsole('Step 1: Evaluating 1H BOS + 15M Demand Zone + 5M Confirmation...', true);
      try {
        const res = await window.API.testSuite('e2e-workflow');
        logConsole(JSON.stringify(res, null, 2), true);
        window.loadTestCenterView();
        alert('End-to-End Workflow Test completed. Audit log updated.');
      } catch (e) {
        logConsole(`❌ Error executing End-to-End test: ${e.message}`, true);
      } finally {
        btnE2E.disabled = false;
      }
    });
  }
});

function renderTestHistoryTable(history) {
  const tbody = document.getElementById('test-history-tbody');
  if (!tbody) return;

  if (history.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-dim);">No test executions logged.</td></tr>`;
    return;
  }

  tbody.innerHTML = history.slice(0, 20).map(t => {
    const isPass = t.status === 'PASSED';
    const badgeClass = isPass ? 'badge-connected' : 'badge-danger';
    const details = t.details || {};
    const summary = details.message || (details.overall_success ? 'All steps succeeded' : JSON.stringify(details).slice(0, 80));

    return `
      <tr>
        <td><strong>${t.test_suite}</strong></td>
        <td><span class="status-badge ${badgeClass}">${t.status}</span></td>
        <td style="font-size:11px; color:var(--text-dim);">${new Date(t.executed_at).toLocaleString()}</td>
        <td style="font-size:12px; color:var(--text-muted);">${summary}</td>
      </tr>
    `;
  }).join('');
}

