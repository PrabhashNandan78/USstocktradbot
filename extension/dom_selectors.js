/**
 * DOM Selector Registry & Adaptive Heuristic Engine for TradingView
 * Provides multi-layer fallback strategies to resist TradingView DOM updates.
 */

const TVSelectors = {
  // 1. User Authentication & Profile
  userMenu: [
    'button[id="header-toolbar-user-menu"]',
    'button[data-name="header-user-menu"]',
    'div[data-role="user-menu"]',
    'button[aria-label*="User menu"]',
    'button[aria-label*="Profile"]',
    'div[class*="userMenu-"]',
    '.tv-header__user-menu'
  ],

  // 2. Active Chart Symbol
  symbolHeader: [
    'button[id="header-toolbar-symbol-search"]',
    'div[id="header-toolbar-symbol-search"]',
    'div[data-name="legend-series-item"] [data-name="legend-source-title"]',
    'div[class*="symbolSearch-"] button',
    'div[class*="legend-"] div[class*="title-"]',
    'button[class*="symbol-"]'
  ],

  symbolSearchInput: [
    'input[data-role="search"]',
    'input[placeholder*="Search"]',
    'input[class*="searchBox-"]',
    'input[class*="search-"]',
    'input[type="text"][placeholder*="Symbol"]'
  ],

  // 3. Trading Panel (Bottom Area)
  bottomTradingTab: [
    'button[data-name="bottom-area-trading"]',
    'div[data-name="trading-panel"]',
    'button[data-name="trading"]',
    'button[aria-label*="Trading Panel"]',
    'div[class*="tabBar-"] button[data-name="trading"]'
  ],

  bottomBarTabs: [
    'button[data-name="bottom-area-trading"]',
    'button[data-name="trading"]',
    'button[aria-label*="Trading Panel" i]',
    'button[aria-label*="Paper Trading" i]',
    'div[class*="bottomWidgetBar-"] button',
    'div[class*="widgetbar-pages"] button',
    '.bottom-widget-bar button',
    'div[class*="tabBar-"] button',
    'div[id="footer-chart-panel"] button'
  ],

  tradingPanelContainer: [
    'div[data-name="trading-panel"]',
    'div[data-name="account-manager"]',
    'div[class*="tradingPanel-"]',
    'div[class*="accountManager-"]',
    'div[class*="bottom-widget-bar"]',
    'div[id="footer-chart-panel"]',
    'div[class*="bottomWidgetBar-"]'
  ],

  // 4. Broker / Paper Trading Panel
  brokerHeaderTitle: [
    'button[data-name="account-select"]',
    'button[data-name="broker-select"]',
    'div[data-name="account-manager-header"]',
    'div[data-name="broker-title"]',
    'div[class*="brokerTitle-"]',
    'div[class*="broker-title"]',
    'span[class*="brokerTitle"]',
    'div[data-role="tab"][class*="active"] span',
    'div[data-name="broker-top-bar"]',
    'div[class*="brokerTopBar-"]',
    'button[class*="brokerButton-"]',
    'div[class*="brokerName-"]',
    'button[class*="accountMenuButton"]',
    'button[class*="brokerButton"]'
  ],

  accountTabs: [
    'div[data-name="positions"]',
    'button[data-name="positions"]',
    'div[role="tab"][data-name="positions"]',
    'div[data-name="orders"]',
    'button[data-name="orders"]',
    'div[role="tab"][data-name="orders"]',
    'div[data-name="order-history"]',
    'button[data-name="order-history"]',
    'div[data-name="balance-history"]',
    'button[data-name="balance-history"]',
    'div[data-name="trade-history"]',
    'button[data-name="trade-history"]',
    'div[data-name="analytics"]',
    'button[data-name="analytics"]',
    'div[data-name="account-summary"]',
    'button[data-name="account-summary"]',
    'div[class*="accountManager-"] [role="tab"]',
    'div[data-name="account-manager"] [role="tab"]'
  ],

  brokerAccountSummary: [
    'div[class*="accountSummary-"]',
    'div[data-name="account-summary"]',
    'div[class*="summary-"] span[class*="value-"]'
  ],

  brokerConnectButtons: [
    'button[data-name="connect-button"]',
    'div[data-name="broker-list"] button',
    'div[class*="brokerList-"] button',
    'div[class*="broker-card"] button',
    'div[class*="brokerCard-"] button'
  ],

  accountBalanceElements: [
    'div[data-name="account-balance"]',
    'div[class*="accountBalance-"]',
    'div[class*="accountSummary-"] span[class*="value-"]',
    'div[class*="summaryItem-"] span[class*="value-"]',
    'span[class*="balanceValue-"]',
    'div[data-name="account-summary"] span[class*="value-"]',
    'div[data-name="account-summary"]',
    'div[class*="accountSummary-"]'
  ],

  // 5. Order Ticket Controls
  quickBuyButton: [
    'button[data-name="buy"]',
    'button[class*="buyButton-"]',
    'div[data-name="order-ticket"] button[data-name="buy"]',
    'button[aria-label*="Buy"]',
    'div[class*="buttons-"] button[class*="buy-"]'
  ],

  orderTicketModal: [
    'div[data-name="order-ticket"]',
    'div[class*="orderTicket-"]',
    'div[data-dialog-name="Order Ticket"]',
    'div[class*="dialog-"][data-name="order-ticket"]'
  ],

  quantityInput: [
    'input[data-name="quantity"]',
    'input[aria-label*="Quantity"]',
    'input[class*="quantity-"]',
    'input[type="text"][name*="quantity"]',
    'div[data-name="quantity"] input'
  ],

  marketOrderTab: [
    'button[data-name="market"]',
    'div[role="tab"][data-name="market"]',
    'button[data-value="market"]',
    'button[aria-label*="Market" i]'
  ],

  takeProfitCheckbox: [
    'input[data-name="take-profit-checkbox"]',
    'input[name*="takeProfit"]',
    'input[type="checkbox"][aria-label*="Take Profit" i]',
    'label[data-name="take-profit"] input[type="checkbox"]'
  ],

  takeProfitPriceInput: [
    'input[data-name="take-profit-price"]',
    'input[aria-label*="Take Profit Price" i]',
    'div[data-name="take-profit"] input[type="text"]',
    'input[class*="takeProfitPrice-"]'
  ],

  stopLossCheckbox: [
    'input[data-name="stop-loss-checkbox"]',
    'input[name*="stopLoss"]',
    'input[type="checkbox"][aria-label*="Stop Loss" i]',
    'label[data-name="stop-loss"] input[type="checkbox"]'
  ],

  stopLossPriceInput: [
    'input[data-name="stop-loss-price"]',
    'input[aria-label*="Stop Loss Price" i]',
    'div[data-name="stop-loss"] input[type="text"]',
    'input[class*="stopLossPrice-"]'
  ],

  submitBuyOrderButton: [
    'button[data-name="submit-buy"]',
    'button[data-name="submit-order"]',
    'button[class*="submitButton-"]',
    'button[type="submit"]',
    'button[aria-label*="Buy" i]'
  ],

  // 6. Positions Table
  positionsTab: [
    'button[data-name="positions"]',
    'div[data-name="positions"]',
    'button[data-name="positions-tab"]',
    'div[role="tab"][data-name="positions"]',
    'div[role="tab"][aria-label*="Positions" i]'
  ],

  positionsRows: [
    'div[data-name="positions-table"] div[role="row"]',
    'div[class*="table-"] tr[class*="row-"]',
    'div[class*="positions-"] div[role="row"]'
  ],

  // 7. Orders & History Table
  historyTab: [
    'button[data-name="order-history"]',
    'button[data-name="history-tab"]',
    'div[role="tab"][data-name="history"]',
    'div[role="tab"][data-name="order-history"]',
    'div[role="tab"][data-name="trade-history"]',
    'div[role="tab"][aria-label*="History" i]'
  ],

  historyRows: [
    'div[data-name="history-table"] div[role="row"]',
    'div[class*="historyTable-"] div[role="row"]'
  ]
};

/**
 * Safe text finder: returns elements of a given tag whose textContent contains search text
 */
function findTVElementByText(tag = '*', text = '', parent = document, exact = false) {
  if (!text) return null;
  const lowerText = text.trim().toLowerCase();
  const candidates = parent.querySelectorAll(tag);
  for (const el of candidates) {
    const content = (el.textContent || '').trim().toLowerCase();
    if (exact ? content === lowerText : content.includes(lowerText)) {
      return el;
    }
  }
  return null;
}

function findTVAllElementsByText(tag = '*', text = '', parent = document, exact = false) {
  if (!text) return [];
  const lowerText = text.trim().toLowerCase();
  const candidates = parent.querySelectorAll(tag);
  const matched = [];
  for (const el of candidates) {
    const content = (el.textContent || '').trim().toLowerCase();
    if (exact ? content === lowerText : content.includes(lowerText)) {
      matched.push(el);
    }
  }
  return matched;
}

/**
 * Robust element finder that tests multiple selector strategies
 */
function findTVElement(selectorList, parent = document) {
  if (!selectorList) return null;
  const list = Array.isArray(selectorList) ? selectorList : [selectorList];

  for (const sel of list) {
    if (!sel || typeof sel !== 'string') continue;
    try {
      if (sel.includes(':contains(')) {
        const match = sel.match(/^(.*?):contains\(["']?(.*?)["']?\)$/);
        if (match) {
          const baseTag = match[1].trim() || '*';
          const searchText = match[2].trim();
          const el = findTVElementByText(baseTag, searchText, parent);
          if (el) return el;
        }
      } else {
        const el = parent.querySelector(sel);
        if (el) return el;
      }
    } catch (e) {
      // Ignore invalid CSS selector syntax safely
    }
  }
  return null;
}

/**
 * Finds all unique elements matching a selector list across all fallback selectors
 */
function findTVAllElements(selectorList, parent = document) {
  if (!selectorList) return [];
  const list = Array.isArray(selectorList) ? selectorList : [selectorList];
  const uniqueElements = new Set();

  for (const sel of list) {
    if (!sel || typeof sel !== 'string') continue;
    try {
      if (sel.includes(':contains(')) {
        const match = sel.match(/^(.*?):contains\(["']?(.*?)["']?\)$/);
        if (match) {
          const baseTag = match[1].trim() || '*';
          const searchText = match[2].trim();
          const els = findTVAllElementsByText(baseTag, searchText, parent);
          for (const el of els) {
            uniqueElements.add(el);
          }
        }
      } else {
        const els = parent.querySelectorAll(sel);
        for (const el of els) {
          uniqueElements.add(el);
        }
      }
    } catch (e) {
      // Ignore invalid CSS selector syntax safely
    }
  }
  return Array.from(uniqueElements);
}

/**
 * Wait for an element to appear in DOM with timeout
 */
function waitForTVElement(selectorList, timeoutMs = 5000, parent = document) {
  return new Promise((resolve) => {
    const el = findTVElement(selectorList, parent);
    if (el) return resolve(el);

    const startTime = Date.now();
    const interval = setInterval(() => {
      const found = findTVElement(selectorList, parent);
      if (found) {
        clearInterval(interval);
        return resolve(found);
      }
      if (Date.now() - startTime > timeoutMs) {
        clearInterval(interval);
        return resolve(null);
      }
    }, 150);
  });
}

// Export for extension content scripts
window.TVSelectors = TVSelectors;
window.findTVElement = findTVElement;
window.findTVAllElements = findTVAllElements;
window.findTVElementByText = findTVElementByText;
window.findTVAllElementsByText = findTVAllElementsByText;
window.waitForTVElement = waitForTVElement;

