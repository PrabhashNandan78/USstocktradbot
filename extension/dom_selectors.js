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

  // 4. Broker / Paper Trading Panel
  brokerHeaderTitle: [
    'div[data-name="broker-title"]',
    'div[class*="brokerTitle-"]',
    'div[class*="broker-title"]',
    'span[class*="brokerTitle"]',
    'div[data-role="tab"][class*="active"] span',
    'button[data-name="broker-select"]'
  ],

  brokerAccountSummary: [
    'div[class*="accountSummary-"]',
    'div[data-name="account-summary"]',
    'div[class*="summary-"] span[class*="value-"]'
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
    'div[role="tab"]:contains("Market")',
    'button:contains("Market")'
  ],

  takeProfitCheckbox: [
    'input[data-name="take-profit-checkbox"]',
    'input[name*="takeProfit"]',
    'input[type="checkbox"][aria-label*="Take Profit"]',
    'span:contains("Take profit") input'
  ],

  takeProfitPriceInput: [
    'input[data-name="take-profit-price"]',
    'input[aria-label*="Take Profit Price"]',
    'div[data-name="take-profit"] input[type="text"]',
    'input[class*="takeProfitPrice-"]'
  ],

  stopLossCheckbox: [
    'input[data-name="stop-loss-checkbox"]',
    'input[name*="stopLoss"]',
    'input[type="checkbox"][aria-label*="Stop Loss"]',
    'span:contains("Stop loss") input'
  ],

  stopLossPriceInput: [
    'input[data-name="stop-loss-price"]',
    'input[aria-label*="Stop Loss Price"]',
    'div[data-name="stop-loss"] input[type="text"]',
    'input[class*="stopLossPrice-"]'
  ],

  submitBuyOrderButton: [
    'button[data-name="submit-buy"]',
    'button[data-name="submit-order"]',
    'button[class*="submitButton-"]',
    'button[type="submit"]',
    'button:contains("Buy")'
  ],

  // 6. Positions Table
  positionsTab: [
    'button[data-name="positions-tab"]',
    'div[role="tab"][data-name="positions"]',
    'div[role="tab"]:contains("Positions")',
    'button:contains("Positions")'
  ],

  positionsRows: [
    'div[data-name="positions-table"] div[role="row"]',
    'div[class*="table-"] tr[class*="row-"]',
    'div[class*="positions-"] div[role="row"]'
  ],

  // 7. Orders & History Table
  historyTab: [
    'button[data-name="history-tab"]',
    'div[role="tab"][data-name="history"]',
    'div[role="tab"]:contains("Account History")',
    'div[role="tab"]:contains("History")',
    'button:contains("History")'
  ],

  historyRows: [
    'div[data-name="history-table"] div[role="row"]',
    'div[class*="historyTable-"] div[role="row"]'
  ]
};

/**
 * Robust element finder that tests multiple selector strategies
 */
function findTVElement(selectorList, parent = document) {
  if (!selectorList) return null;
  const list = Array.isArray(selectorList) ? selectorList : [selectorList];

  for (const sel of list) {
    try {
      if (sel.includes(':contains(')) {
        // Pseudo-selector implementation for standard DOM
        const match = sel.match(/(.*?):contains\(["']?(.*?)["']?\)/);
        if (match) {
          const tag = match[1] || '*';
          const text = match[2];
          const candidates = parent.querySelectorAll(tag);
          for (const el of candidates) {
            if (el.textContent && el.textContent.trim().toLowerCase().includes(text.toLowerCase())) {
              return el;
            }
          }
        }
      } else {
        const el = parent.querySelector(sel);
        if (el) return el;
      }
    } catch (e) {
      // Ignore unsupported pseudo-selector errors
    }
  }
  return null;
}

/**
 * Finds all elements matching a selector list
 */
function findTVAllElements(selectorList, parent = document) {
  if (!selectorList) return [];
  const list = Array.isArray(selectorList) ? selectorList : [selectorList];

  for (const sel of list) {
    try {
      const els = parent.querySelectorAll(sel);
      if (els && els.length > 0) return Array.from(els);
    } catch (e) {}
  }
  return [];
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
window.waitForTVElement = waitForTVElement;
