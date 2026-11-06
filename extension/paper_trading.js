/**
 * TradingView Paper Trading Verifier & Safety Guard
 * Verifies that the user is logged in, the Trading Panel is active,
 * and that the environment is STRICTLY Paper Trading (NEVER a live broker).
 */

const PaperTradingGuard = {
  // Known live money brokers that must NEVER be automated
  KNOWN_LIVE_BROKERS: [
    'interactive brokers', 'tradovate', 'amp', 'oanda', 'cqg', 'binance',
    'bybit', 'coinbase', 'forex.com', 'capital.com', 'saxo', 'easyforex',
    'ironbeam', 'wh selfinvest', 'optimus futures', 'tradeview'
  ],

  /**
   * Performs full verification of TradingView environment
   */
  async verifyEnvironment() {
    const isTVPage = window.location.hostname.includes('tradingview.com');
    const isChart = isTVPage && (window.location.pathname.includes('/chart') || document.querySelector('canvas') !== null);

    const loginStatus = this.detectUserLogin();
    const currentSymbol = this.detectCurrentSymbol();
    const paperTradingStatus = await this.inspectTradingPanel();

    const verification = {
      tv_tab_detected: isChart,
      tv_login_detected: loginStatus.isLoggedIn,
      username: loginStatus.username,
      current_symbol: currentSymbol,
      paper_trading_connected: paperTradingStatus.isConnected,
      paper_trading_account_verified: paperTradingStatus.isVerified,
      broker_name: paperTradingStatus.brokerName,
      account_balance: paperTradingStatus.balance,
      error_message: paperTradingStatus.errorMessage || null,
      timestamp: new Date().toISOString()
    };

    return verification;
  },

  /**
   * Detects if user is logged into TradingView
   */
  detectUserLogin() {
    const userMenuEl = window.findTVElement(window.TVSelectors.userMenu);
    if (!userMenuEl) {
      // Secondary check: look for sign in button
      const signInBtn = window.findTVElement(['button:contains("Sign in")', 'a[href*="/accounts/signin/"]']);
      if (signInBtn) {
        return { isLoggedIn: false, username: null };
      }
      return { isLoggedIn: false, username: null };
    }

    const ariaLabel = userMenuEl.getAttribute('aria-label') || '';
    const title = userMenuEl.getAttribute('title') || '';
    const username = (ariaLabel.replace(/User menu/i, '') || title || 'Authenticated User').trim();

    return { isLoggedIn: true, username: username || 'User' };
  },

  /**
   * Detects current chart symbol
   */
  detectCurrentSymbol() {
    const symbolEl = window.findTVElement(window.TVSelectors.symbolHeader);
    if (symbolEl && symbolEl.textContent) {
      const text = symbolEl.textContent.trim().split(/[\s,·\n]+/)[0];
      if (text && text.length >= 1 && text.length <= 10) {
        return text.toUpperCase();
      }
    }

    // Heuristic: check window document title (e.g. "AAPL 150.25 — TradingView")
    const titleMatch = document.title.match(/^([A-Z0-9.\-_]{1,10})\s+/);
    if (titleMatch && titleMatch[1]) {
      return titleMatch[1].toUpperCase();
    }

    return null;
  },

  /**
   * Inspects Trading Panel for Paper Trading connection and Broker Safety
   */
  async inspectTradingPanel() {
    // 1. Check if trading panel exists or can be opened
    let panelTab = window.findTVElement(window.TVSelectors.bottomTradingTab);
    
    // Check if bottom bar has "Trading Panel" or active broker name
    const brokerTitleEl = window.findTVElement(window.TVSelectors.brokerHeaderTitle);
    
    // Text search on bottom dock
    const bottomDock = document.querySelector('div[class*="bottom-widget-bar"], div[class*="trading-panel"]');
    const bottomText = bottomDock ? bottomDock.textContent.toLowerCase() : document.body.innerText.toLowerCase();

    // 2. SAFETY CHECK: Check for Live Broker
    for (const liveBroker of this.KNOWN_LIVE_BROKERS) {
      if (bottomText.includes(liveBroker)) {
        return {
          isConnected: false,
          isVerified: false,
          brokerName: liveBroker.toUpperCase(),
          errorMessage: `SAFETY HALT: Active broker appears to be '${liveBroker.toUpperCase()}'. Automated trades only allowed on Paper Trading!`
        };
      }
    }

    // 3. Verify Paper Trading
    const isPaperTradingPresent = bottomText.includes('paper trading') || 
                                  (brokerTitleEl && brokerTitleEl.textContent.toLowerCase().includes('paper trading'));

    if (!isPaperTradingPresent) {
      return {
        isConnected: false,
        isVerified: false,
        brokerName: 'NONE',
        errorMessage: 'Paper Trading is not connected. Open Trading Panel at the bottom and click "Paper Trading by TradingView".'
      };
    }

    // 4. Verify Account Status / Balance
    let balance = null;
    const balanceMatch = bottomText.match(/balance:?\s*(\$[\d,]+(?:\.\d{2})?|\d+(?:\.\d{2})?)/i);
    if (balanceMatch && balanceMatch[1]) {
      balance = parseFloat(balanceMatch[1].replace(/[^0-9.]/g, ''));
    }

    return {
      isConnected: true,
      isVerified: true,
      brokerName: 'Paper Trading by TradingView',
      balance: balance || 100000.0,
      errorMessage: null
    };
  }
};

window.PaperTradingGuard = PaperTradingGuard;
