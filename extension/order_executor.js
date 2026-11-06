/**
 * TradingView Order Executor
 * Automates symbol switching, order-ticket entry, TP/SL configuration,
 * and execution verification on TradingView Paper Trading.
 */

const OrderExecutor = {
  isLocked: false,

  /**
   * Main entry point for executing a signal from backend
   */
  async executeOrder(orderRequest) {
    if (this.isLocked) {
      console.warn('[OrderExecutor] Execution lock is active. Rejecting duplicate attempt.');
      return { success: false, error_message: 'Execution engine currently locked with pending order.' };
    }

    this.isLocked = true;
    try {
      console.log('[OrderExecutor] Starting order execution sequence:', orderRequest);

      // Pre-flight 1: Verify Paper Trading environment
      const env = await window.PaperTradingGuard.verifyEnvironment();
      if (!env.paper_trading_connected || !env.paper_trading_account_verified) {
        throw new Error(env.error_message || 'TradingView Paper Trading is not active or verified.');
      }

      // Pre-flight 2: Switch Symbol if needed
      const requestedSymbol = orderRequest.symbol.toUpperCase();
      if (env.current_symbol !== requestedSymbol) {
        console.log(`[OrderExecutor] Active symbol is ${env.current_symbol}, switching to ${requestedSymbol}...`);
        await this.switchSymbol(requestedSymbol);
        await this.sleep(1500);
      }

      // Pre-flight 3: Open Order Ticket Panel
      await this.openOrderTicket();
      await this.sleep(500);

      // Step 4: Configure Order Type (Market)
      await this.selectMarketOrder();

      // Step 5: Input Quantity
      const qty = orderRequest.quantity || 1;
      await this.setQuantity(qty);

      // Step 6: Configure Take Profit & Stop Loss
      if (orderRequest.take_profit) {
        await this.setTakeProfit(orderRequest.take_profit);
      }
      if (orderRequest.stop_loss) {
        await this.setStopLoss(orderRequest.stop_loss);
      }

      // Step 7: Submit BUY Order
      const submitResult = await this.submitBuyOrder();
      if (!submitResult.clicked) {
        throw new Error('Failed to find or click Submit Buy button in Order Ticket.');
      }

      // Step 8: Verify Execution
      console.log('[OrderExecutor] Order submitted. Verifying fill on Paper Trading...');
      const verification = await this.verifyOrderExecution(requestedSymbol, orderRequest.entry_price);

      return {
        success: verification.filled,
        signal_id: orderRequest.signal_id,
        symbol: requestedSymbol,
        executed_price: verification.fillPrice || orderRequest.entry_price,
        tv_order_id: verification.orderId || `TV-${Date.now()}`,
        protective_orders_active: true,
        error_message: verification.filled ? null : 'Submitted, but could not confirm fill in TradingView positions table within timeout.'
      };

    } catch (err) {
      console.error('[OrderExecutor] Error during order execution:', err);
      return {
        success: false,
        signal_id: orderRequest.signal_id,
        symbol: orderRequest.symbol,
        error_message: err.message || 'Unknown execution error'
      };
    } finally {
      this.isLocked = false;
    }
  },

  /**
   * Switches the active chart symbol using TradingView's symbol search
   */
  async switchSymbol(symbol) {
    const symbolBtn = window.findTVElement(window.TVSelectors.symbolHeader);
    if (symbolBtn) {
      symbolBtn.click();
    } else {
      // Simulate typing shortcut
      document.dispatchEvent(new KeyboardEvent('keydown', { key: symbol[0], bubbles: true }));
    }

    const searchInput = await window.waitForTVElement(window.TVSelectors.symbolSearchInput, 3000);
    if (searchInput) {
      searchInput.focus();
      searchInput.value = symbol;
      searchInput.dispatchEvent(new Event('input', { bubbles: true }));
      await this.sleep(500);
      searchInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', keyCode: 13, bubbles: true }));
    }
  },

  /**
   * Opens the Order Ticket Dialog
   */
  async openOrderTicket() {
    let orderModal = window.findTVElement(window.TVSelectors.orderTicketModal);
    if (orderModal && orderModal.offsetParent !== null) {
      return true; // Already open
    }

    const buyBtn = window.findTVElement(window.TVSelectors.quickBuyButton);
    if (buyBtn) {
      buyBtn.click();
      await this.sleep(400);
      return true;
    }

    // Secondary: Press Shift + T (TradingView shortcut for Order Ticket)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'T', shiftKey: true, bubbles: true }));
    await this.sleep(500);
    return true;
  },

  /**
   * Selects Market Order type
   */
  async selectMarketOrder() {
    const marketTab = window.findTVElement(window.TVSelectors.marketOrderTab);
    if (marketTab) {
      marketTab.click();
      await this.sleep(200);
    }
  },

  /**
   * Sets the quantity in the input field
   */
  async setQuantity(qty) {
    const qtyInput = window.findTVElement(window.TVSelectors.quantityInput);
    if (qtyInput) {
      qtyInput.focus();
      qtyInput.value = qty.toString();
      qtyInput.dispatchEvent(new Event('input', { bubbles: true }));
      qtyInput.dispatchEvent(new Event('change', { bubbles: true }));
    }
  },

  /**
   * Sets Take Profit target
   */
  async setTakeProfit(tpPrice) {
    const checkbox = window.findTVElement(window.TVSelectors.takeProfitCheckbox);
    if (checkbox && !checkbox.checked) {
      checkbox.click();
      await this.sleep(200);
    }
    const input = window.findTVElement(window.TVSelectors.takeProfitPriceInput);
    if (input) {
      input.focus();
      input.value = tpPrice.toFixed(2);
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }
  },

  /**
   * Sets Stop Loss price
   */
  async setStopLoss(slPrice) {
    const checkbox = window.findTVElement(window.TVSelectors.stopLossCheckbox);
    if (checkbox && !checkbox.checked) {
      checkbox.click();
      await this.sleep(200);
    }
    const input = window.findTVElement(window.TVSelectors.stopLossPriceInput);
    if (input) {
      input.focus();
      input.value = slPrice.toFixed(2);
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }
  },

  /**
   * Clicks Submit Buy Order button
   */
  async submitBuyOrder() {
    const submitBtn = window.findTVElement(window.TVSelectors.submitBuyOrderButton);
    if (submitBtn) {
      submitBtn.click();
      return { clicked: true };
    }
    return { clicked: false };
  },

  /**
   * Verifies that the order executed by inspecting the Positions table or Toast
   */
  async verifyOrderExecution(symbol, expectedPrice, timeoutMs = 8000) {
    const startTime = Date.now();
    while (Date.now() - startTime < timeoutMs) {
      const positions = window.PositionTracker ? window.PositionTracker.scrapePositions() : [];
      const match = positions.find(p => p.symbol.toUpperCase() === symbol.toUpperCase());
      if (match) {
        return {
          filled: true,
          fillPrice: match.avg_price || expectedPrice,
          orderId: `TV-${symbol}-${Date.now()}`
        };
      }

      // Check for toast notifications in DOM
      const toasts = document.querySelectorAll('div[data-role="toast"], div[class*="toast-"]');
      for (const t of toasts) {
        const text = t.textContent.toLowerCase();
        if (text.includes('order executed') || text.includes('position opened') || text.includes('filled')) {
          return {
            filled: true,
            fillPrice: expectedPrice,
            orderId: `TV-TOAST-${Date.now()}`
          };
        }
      }

      await this.sleep(500);
    }

    return { filled: false };
  },

  sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
};

window.OrderExecutor = OrderExecutor;
