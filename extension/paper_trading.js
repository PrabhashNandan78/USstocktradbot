/**
 * TradingView Paper Trading Verifier & Safety Guard
 * 
 * Implements a strict 4-state machine:
 * - PAPER_TRADING_CONNECTED (Permits order execution)
 * - LIVE_BROKER_CONNECTED  (Strict safety halt)
 * - DISCONNECTED           (Blocks execution, prompts user to connect)
 * - UNKNOWN                (Blocks execution while verifying)
 */

const ACCOUNT_STATES = {
  PAPER_TRADING_CONNECTED: 'PAPER_TRADING_CONNECTED',
  LIVE_BROKER_CONNECTED: 'LIVE_BROKER_CONNECTED',
  DISCONNECTED: 'DISCONNECTED',
  UNKNOWN: 'UNKNOWN'
};

const PaperTradingGuard = {
  ACCOUNT_STATES,

  // Known live money brokers with exact word-boundary detection
  LIVE_BROKER_REGEX: /\b(interactive brokers|ibkr|tradovate|amp futures|amp clearing|oanda|cqg|binance|bybit|coinbase|forex\.com|capital\.com|saxo|easyforex|ironbeam|wh selfinvest|optimus futures|tradeview|tradestation|webull|schwab|td ameritrade|e\*trade|fidelity|robinhood|alor|whselfinvest)\b/i,

  // Known non-US equities exchanges
  NON_US_EXCHANGE_REGEX: /^(NSE|BSE|MCX|NFO|BINANCE|BYBIT|COINBASE|KRAKEN|BITFINEX|FOREX|FX|INDEX|LSE|TSX|MOEX|HKEX|SSE|SZSE|KRX|SGX|ASX|EURONEXT|FWB|SWX|B3)$/i,

  /**
   * Performs full verification of TradingView environment
   */
  async verifyEnvironment() {
    const isTVPage = typeof window !== 'undefined' && window.location && window.location.hostname ? window.location.hostname.includes('tradingview.com') : true;
    const isChart = isTVPage && (
      (window.location && window.location.pathname && window.location.pathname.includes('/chart')) || 
      (typeof document !== 'undefined' && document.querySelector('canvas') !== null) ||
      (typeof document !== 'undefined' && document.querySelector('div[id="header-toolbar-symbol-search"]') !== null)
    );

    const loginStatus = this.detectUserLogin();
    const symbolInfo = this.detectCurrentSymbol();
    const panelStatus = await this.inspectTradingPanel();

    // Determine strict state
    let accountState = panelStatus.state;
    let isConnected = false;
    let isVerified = false;
    let errorMessage = panelStatus.errorMessage;

    if (!isChart) {
      accountState = ACCOUNT_STATES.UNKNOWN;
      errorMessage = 'TradingView chart page not detected.';
    } else if (panelStatus.state === ACCOUNT_STATES.LIVE_BROKER_CONNECTED) {
      accountState = ACCOUNT_STATES.LIVE_BROKER_CONNECTED;
      isConnected = false;
      isVerified = false;
      errorMessage = panelStatus.errorMessage;
    } else if (panelStatus.state === ACCOUNT_STATES.PAPER_TRADING_CONNECTED) {
      accountState = ACCOUNT_STATES.PAPER_TRADING_CONNECTED;
      isConnected = true;
      isVerified = true;
      errorMessage = null;
    } else if (panelStatus.state === ACCOUNT_STATES.DISCONNECTED) {
      accountState = ACCOUNT_STATES.DISCONNECTED;
      isConnected = false;
      isVerified = false;
      errorMessage = panelStatus.errorMessage;
    } else {
      accountState = ACCOUNT_STATES.UNKNOWN;
      isConnected = false;
      isVerified = false;
      errorMessage = panelStatus.errorMessage || 'Verifying TradingView account state...';
    }

    const verification = {
      account_state: accountState,
      tv_tab_detected: isChart,
      tv_login_detected: loginStatus.isLoggedIn,
      username: loginStatus.username,
      current_symbol: symbolInfo.ticker,
      raw_tv_symbol: symbolInfo.raw,
      exchange: symbolInfo.exchange,
      paper_trading_connected: isConnected,
      paper_trading_account_verified: isVerified,
      broker_name: panelStatus.brokerName || (accountState === ACCOUNT_STATES.PAPER_TRADING_CONNECTED ? 'Paper Trading by TradingView' : 'NONE'),
      account_balance: panelStatus.balance,
      error_message: errorMessage,
      last_verified_at: new Date().toISOString(),
      indicators: {
        ...panelStatus.indicators,
        tv_tab_detected: isChart,
        account_state: accountState,
        error_message: errorMessage
      }
    };

    // Diagnostic logging without credentials
    if (typeof console !== 'undefined' && console.log) {
      console.log('[PaperTradingGuard] Verification diagnostic:', {
        account_state: verification.account_state,
        tv_tab_detected: verification.tv_tab_detected,
        bottom_tab_title: verification.indicators.bottom_tab_title,
        panel_visible: verification.indicators.panel_visible,
        active_broker_text: verification.indicators.active_broker_text,
        has_account_tabs: verification.indicators.has_account_tabs,
        found_account_tabs: verification.indicators.found_account_tabs,
        has_balance: verification.indicators.has_balance,
        is_gallery_visible: verification.indicators.is_gallery_visible,
        matched_selectors: verification.indicators.matched_selectors,
        error_message: verification.error_message,
        last_verified_at: verification.last_verified_at
      });
    }

    return verification;
  },

  /**
   * Detects if user is logged into TradingView
   */
  detectUserLogin() {
    if (typeof window === 'undefined' || typeof document === 'undefined') {
      return { isLoggedIn: true, username: 'TradingView User' };
    }

    const userMenuEl = window.findTVElement(window.TVSelectors.userMenu);
    if (!userMenuEl) {
      const signInBtn = window.findTVElement(['a[href*="/accounts/signin/"]', 'button[data-name="header-signin-button"]']) || 
                        window.findTVElementByText('button', 'Sign in') ||
                        window.findTVElementByText('a', 'Sign in');
      if (signInBtn) {
        return { isLoggedIn: false, username: null };
      }
      return { isLoggedIn: true, username: 'TradingView User' };
    }

    const ariaLabel = userMenuEl.getAttribute('aria-label') || '';
    const title = userMenuEl.getAttribute('title') || '';
    const username = (ariaLabel.replace(/User menu/i, '') || title || 'Authenticated User').trim();

    return { isLoggedIn: true, username: username || 'User' };
  },

  /**
   * Extracts raw symbol, ticker, and exchange from TradingView
   */
  detectCurrentSymbol() {
    if (typeof window === 'undefined' || typeof document === 'undefined') {
      return { raw: null, exchange: null, ticker: null };
    }

    let rawSymbol = '';

    // Strategy 1: Header symbol button
    const symbolEl = window.findTVElement(window.TVSelectors.symbolHeader);
    if (symbolEl && symbolEl.textContent) {
      rawSymbol = symbolEl.textContent.trim().split(/[\s,·\n]+/)[0];
    }

    // Strategy 2: URL parameter
    if (!rawSymbol) {
      try {
        const urlParams = new URLSearchParams(window.location.search);
        const symParam = urlParams.get('symbol');
        if (symParam) rawSymbol = decodeURIComponent(symParam);
      } catch (e) {}
    }

    // Strategy 3: Document Title (e.g. "AAPL 150.25 — TradingView" or "NSE:NIFTY1! 24000")
    if (!rawSymbol && document.title) {
      const titleMatch = document.title.match(/^([A-Z0-9.\-_:!]{1,20})\s+/);
      if (titleMatch && titleMatch[1]) {
        rawSymbol = titleMatch[1];
      }
    }

    rawSymbol = rawSymbol.trim().toUpperCase();

    // Parse Exchange and Ticker
    let exchange = null;
    let ticker = rawSymbol;

    if (rawSymbol.includes(':')) {
      const parts = rawSymbol.split(':');
      exchange = parts[0].trim().toUpperCase();
      ticker = parts[1].trim().toUpperCase();
    }

    return {
      raw: rawSymbol || null,
      exchange: exchange,
      ticker: ticker || null
    };
  },

  /**
   * Validates whether a signal symbol matches the active TradingView chart symbol
   */
  validateSymbolMatch(signalSymbol, rawTvSymbol) {
    if (!signalSymbol) {
      return { valid: false, reason: 'Signal symbol is empty or missing.' };
    }

    const tvInfo = this.detectCurrentSymbol();
    const effectiveRaw = rawTvSymbol || tvInfo.raw;
    const effectiveTicker = tvInfo.ticker;
    const effectiveExchange = tvInfo.exchange;

    if (!effectiveRaw || !effectiveTicker) {
      return {
        valid: false,
        reason: 'Execution blocked: TradingView symbol could not be verified from the active chart.'
      };
    }

    // 1. Check Exchange Compatibility (Reject Non-US Exchanges)
    if (effectiveExchange && this.NON_US_EXCHANGE_REGEX.test(effectiveExchange)) {
      return {
        valid: false,
        reason: `Execution blocked: TradingView exchange '${effectiveExchange}' is not a US equities exchange (Signal: ${signalSymbol}).`
      };
    }

    // 2. Normalize and Compare Ticker
    const cleanSignal = signalSymbol.replace(/[^A-Z0-9]/gi, '').toUpperCase();
    const cleanTvTicker = effectiveTicker.replace(/[^A-Z0-9]/gi, '').toUpperCase();

    if (cleanSignal !== cleanTvTicker) {
      return {
        valid: false,
        reason: `Execution blocked: TradingView symbol (${effectiveRaw}) does not match signal symbol (${signalSymbol}).`
      };
    }

    return {
      valid: true,
      normalized_symbol: cleanSignal,
      exchange: effectiveExchange || 'US',
      reason: null
    };
  },

  /**
   * Inspects Trading Panel using multiple independent DOM indicators
   */
  async inspectTradingPanel() {
    const matchedSelectors = [];
    const foundAccountTabs = [];

    const testSelector = (selectorName, list, parent = (typeof document !== 'undefined' ? document : null)) => {
      if (!parent || !window.findTVElement) return null;
      const el = window.findTVElement(list, parent);
      if (el) {
        matchedSelectors.push(selectorName);
      }
      return el;
    };

    const testAllSelectors = (selectorName, list, parent = (typeof document !== 'undefined' ? document : null)) => {
      if (!parent || !window.findTVAllElements) return [];
      const els = window.findTVAllElements(list, parent);
      if (els && els.length > 0) {
        matchedSelectors.push(selectorName);
      }
      return els;
    };

    // 1. Check Trading Panel Container & Visibility
    const panelContainer = testSelector('tradingPanelContainer', window.TVSelectors.tradingPanelContainer);
    let panelVisible = false;
    if (panelContainer) {
      const style = (typeof window !== 'undefined' && window.getComputedStyle) ? window.getComputedStyle(panelContainer) : null;
      const isDisplayNone = style && (style.display === 'none' || style.visibility === 'hidden');
      const isZeroSize = panelContainer.offsetHeight === 0 && panelContainer.offsetWidth === 0;
      panelVisible = !isDisplayNone && !isZeroSize;
    }

    // 2. Inspect Bottom Bar Tabs
    let bottomTabTitle = null;
    let foundBottomPaperTab = false;
    let foundBottomTradingTab = false;

    const bottomTabs = testAllSelectors('bottomBarTabs', window.TVSelectors.bottomBarTabs);
    for (const btn of bottomTabs) {
      const text = (btn.innerText || btn.textContent || '').trim();
      const aria = (btn.getAttribute('aria-label') || btn.getAttribute('title') || '').trim();
      const combined = `${text} ${aria}`.toLowerCase();
      if (combined.includes('paper trading')) {
        foundBottomPaperTab = true;
        bottomTabTitle = 'Paper Trading';
      } else if (combined.includes('trading panel') || btn.getAttribute('data-name') === 'trading') {
        foundBottomTradingTab = true;
        if (!bottomTabTitle) bottomTabTitle = 'Trading Panel';
      }
    }

    if (typeof document !== 'undefined') {
      const docTabs = document.querySelectorAll('button[aria-label*="Trading" i], button[title*="Trading" i], [data-name*="trading"]');
      for (const b of docTabs) {
        const aria = (b.getAttribute('aria-label') || b.getAttribute('title') || b.innerText || '').toLowerCase();
        if (aria.includes('paper trading')) {
          foundBottomPaperTab = true;
          bottomTabTitle = 'Paper Trading';
          matchedSelectors.push('docTabPaperTrading');
          break;
        } else if (aria.includes('trading panel')) {
          foundBottomTradingTab = true;
          if (!bottomTabTitle) bottomTabTitle = 'Trading Panel';
          matchedSelectors.push('docTabTradingPanel');
        }
      }
    }

    // 3. Check Active Broker Title / Header in Trading Panel
    let activeBrokerText = null;
    const brokerTitleEls = testAllSelectors('brokerHeaderTitle', window.TVSelectors.brokerHeaderTitle);
    for (const el of brokerTitleEls) {
      const t = (el.innerText || el.textContent || '').trim();
      if (t && t.length > 0 && !t.includes('Stock Screener') && !t.includes('Pine Editor') && !t.includes('Strategy Tester')) {
        activeBrokerText = t;
        break;
      }
    }

    // Fallback: search for paper trading text inside panelContainer
    if (!activeBrokerText && panelContainer) {
      const paperEl = window.findTVElementByText('div', 'Paper Trading', panelContainer) ||
                      window.findTVElementByText('button', 'Paper Trading', panelContainer) ||
                      window.findTVElementByText('span', 'Paper Trading', panelContainer);
      if (paperEl) {
        activeBrokerText = 'Paper Trading by TradingView';
        matchedSelectors.push('paperTradingTextInPanel');
      }
    }

    // 4. Check Active Account Sub-Tabs
    const standardTabs = [
      { name: 'Positions', sel: window.TVSelectors.positionsTab },
      { name: 'Orders', sel: ['button[data-name="orders"]', 'div[data-name="orders"]', 'div[role="tab"][data-name="orders"]'] },
      { name: 'Order history', sel: window.TVSelectors.historyTab },
      { name: 'Balance history', sel: ['button[data-name="balance-history"]', 'div[data-name="balance-history"]', 'div[role="tab"][data-name="balance-history"]'] },
      { name: 'Trade history', sel: ['button[data-name="trade-history"]', 'div[data-name="trade-history"]', 'div[role="tab"][data-name="trade-history"]'] },
      { name: 'Analytics', sel: ['button[data-name="analytics"]', 'div[data-name="analytics"]', 'div[role="tab"][data-name="analytics"]'] },
      { name: 'Account Summary', sel: ['button[data-name="account-summary"]', 'div[data-name="account-summary"]', 'div[role="tab"][data-name="account-summary"]'] }
    ];

    const searchContext = panelContainer || (typeof document !== 'undefined' ? document : null);
    if (searchContext) {
      for (const tab of standardTabs) {
        let el = window.findTVElement(tab.sel, searchContext);
        if (!el) {
          el = window.findTVElementByText('button', tab.name, searchContext) ||
               window.findTVElementByText('div[role="tab"]', tab.name, searchContext) ||
               window.findTVElementByText('div', tab.name, searchContext);
        }
        if (el) {
          foundAccountTabs.push(tab.name);
          matchedSelectors.push(`accountTab_${tab.name.replace(/\s+/g, '')}`);
        }
      }
    }
    const hasAccountTabs = foundAccountTabs.length > 0;

    // 5. Check Account Balance & Equity Elements
    let balance = null;
    let hasBalance = false;
    const balanceEls = testAllSelectors('accountBalanceElements', window.TVSelectors.accountBalanceElements);
    for (const el of balanceEls) {
      const t = el.innerText || el.textContent || '';
      const match = t.match(/\$?\s*([\d,]+(?:\.\d{2})?)/);
      if (match && match[1]) {
        const val = parseFloat(match[1].replace(/,/g, ''));
        if (!isNaN(val) && val > 0) {
          balance = val;
          hasBalance = true;
          break;
        }
      }
    }

    if (!balance && panelContainer) {
      const text = panelContainer.innerText || panelContainer.textContent || '';
      const match = text.match(/Balance:?\s*\$?\s*([\d,]+(?:\.\d{2})?)/i) || 
                    text.match(/Equity:?\s*\$?\s*([\d,]+(?:\.\d{2})?)/i);
      if (match && match[1]) {
        const val = parseFloat(match[1].replace(/,/g, ''));
        if (!isNaN(val) && val > 0) {
          balance = val;
          hasBalance = true;
          matchedSelectors.push('panelTextBalance');
        }
      }
    }

    // 6. Check for Disconnected Broker Gallery (Connect buttons)
    const connectButtons = testAllSelectors('brokerConnectButtons', window.TVSelectors.brokerConnectButtons);
    let isGalleryVisible = connectButtons.length >= 2;
    if (!isGalleryVisible && panelContainer) {
      const brokerList = panelContainer.querySelector('div[data-name="broker-list"], div[class*="brokerList-"]');
      if (brokerList) {
        const connects = window.findTVAllElementsByText('button', 'Connect', brokerList);
        if (connects.length >= 1) {
          isGalleryVisible = true;
          matchedSelectors.push('brokerGalleryConnectButtons');
        }
      }
    }

    const indicators = {
      tv_tab_detected: true,
      bottom_tab_title: bottomTabTitle,
      panel_visible: panelVisible,
      active_broker_text: activeBrokerText,
      has_account_tabs: hasAccountTabs,
      found_account_tabs: foundAccountTabs,
      has_balance: hasBalance,
      is_gallery_visible: isGalleryVisible,
      account_state: ACCOUNT_STATES.UNKNOWN,
      error_message: null,
      matched_selectors: Array.from(new Set(matchedSelectors)),
      last_verified_at: new Date().toISOString()
    };

    // Priority 1: Live Broker Check (Strict Safety Guard)
    if (activeBrokerText && this.LIVE_BROKER_REGEX.test(activeBrokerText)) {
      const match = activeBrokerText.match(this.LIVE_BROKER_REGEX)[0].toUpperCase();
      const err = `CRITICAL SAFETY HALT: Active broker is '${match}'. Real money broker detected. Automated orders are strictly prohibited!`;
      indicators.account_state = ACCOUNT_STATES.LIVE_BROKER_CONNECTED;
      indicators.error_message = err;
      return {
        state: ACCOUNT_STATES.LIVE_BROKER_CONNECTED,
        brokerName: match,
        balance: balance,
        errorMessage: err,
        indicators
      };
    }

    // Priority 2: Disconnected Broker Gallery Visible
    if (isGalleryVisible) {
      const err = 'TradingView Paper Trading is not connected. Open the Trading Panel at the bottom of TradingView and click "Paper Trading by TradingView" -> Connect.';
      indicators.account_state = ACCOUNT_STATES.DISCONNECTED;
      indicators.error_message = err;
      return {
        state: ACCOUNT_STATES.DISCONNECTED,
        brokerName: 'NONE',
        balance: null,
        errorMessage: err,
        indicators
      };
    }

    // Priority 3: Unknown / Ambiguous Third-Party Broker
    const isBrokerTitlePaper = Boolean(
      activeBrokerText && (
        activeBrokerText.toLowerCase().includes('paper trading') ||
        activeBrokerText.toLowerCase().includes('paper')
      )
    );

    if (activeBrokerText && !isBrokerTitlePaper && activeBrokerText !== 'NONE' && activeBrokerText !== 'Trading Panel') {
      const err = `Execution blocked: Active broker '${activeBrokerText}' is not verified as TradingView Paper Trading.`;
      indicators.account_state = ACCOUNT_STATES.UNKNOWN;
      indicators.error_message = err;
      return {
        state: ACCOUNT_STATES.UNKNOWN,
        brokerName: activeBrokerText,
        balance: balance,
        errorMessage: err,
        indicators
      };
    }

    // Priority 4: Positively Verified Paper Trading
    const isPaperTradingConfirmed = (
      (isBrokerTitlePaper && (hasAccountTabs || hasBalance || panelVisible)) ||
      (foundBottomPaperTab && (hasAccountTabs || hasBalance || !panelVisible)) ||
      (panelVisible && hasAccountTabs && hasBalance)
    );

    if (isPaperTradingConfirmed) {
      indicators.account_state = ACCOUNT_STATES.PAPER_TRADING_CONNECTED;
      indicators.error_message = null;
      return {
        state: ACCOUNT_STATES.PAPER_TRADING_CONNECTED,
        brokerName: 'Paper Trading by TradingView',
        balance: balance || 100000.0,
        errorMessage: null,
        indicators
      };
    }

    // Priority 5: Trading Panel Collapsed Check
    if (!panelVisible) {
      if (foundBottomPaperTab) {
        indicators.account_state = ACCOUNT_STATES.PAPER_TRADING_CONNECTED;
        indicators.error_message = null;
        return {
          state: ACCOUNT_STATES.PAPER_TRADING_CONNECTED,
          brokerName: 'Paper Trading by TradingView',
          balance: balance || 100000.0,
          errorMessage: null,
          indicators
        };
      }
      if (foundBottomTradingTab) {
        const err = "Trading Panel is collapsed. Click 'Trading Panel' at the bottom to verify Paper Trading.";
        indicators.account_state = ACCOUNT_STATES.UNKNOWN;
        indicators.error_message = err;
        return {
          state: ACCOUNT_STATES.UNKNOWN,
          brokerName: 'UNKNOWN',
          balance: null,
          errorMessage: err,
          indicators
        };
      }
    }

    // Priority 6: Trading Panel Open but Empty / Loading / Disconnected
    if (panelVisible && !hasAccountTabs && !hasBalance && !isBrokerTitlePaper && !foundBottomPaperTab) {
      if (foundBottomTradingTab) {
        const err = 'TradingView Paper Trading is not connected. Open the Trading Panel at the bottom of TradingView and click "Paper Trading by TradingView" -> Connect.';
        indicators.account_state = ACCOUNT_STATES.DISCONNECTED;
        indicators.error_message = err;
        return {
          state: ACCOUNT_STATES.DISCONNECTED,
          brokerName: 'NONE',
          balance: null,
          errorMessage: err,
          indicators
        };
      }
      const err = 'Trading Panel is loading account data...';
      indicators.account_state = ACCOUNT_STATES.UNKNOWN;
      indicators.error_message = err;
      return {
        state: ACCOUNT_STATES.UNKNOWN,
        brokerName: 'UNKNOWN',
        balance: null,
        errorMessage: err,
        indicators
      };
    }

    // Priority 7: Fallback UNKNOWN
    const fallbackErr = 'TradingView chart page or Trading Panel dock not fully initialized.';
    indicators.account_state = ACCOUNT_STATES.UNKNOWN;
    indicators.error_message = fallbackErr;
    return {
      state: ACCOUNT_STATES.UNKNOWN,
      brokerName: 'UNKNOWN',
      balance: null,
      errorMessage: fallbackErr,
      indicators
    };
  }
};

window.PaperTradingGuard = PaperTradingGuard;
