/**
 * TradingView Paper Trading Position Tracker & Exit Scraper
 * Continuously monitors open positions, catches stop-loss / take-profit fills,
 * and extracts realized P&L and closing reasons.
 */

const PositionTracker = {
  activePositions: [],
  lastKnownSymbols: new Set(),

  /**
   * Scrapes currently open positions in TradingView Paper Trading
   */
  scrapePositions() {
    const rows = window.findTVAllElements(window.TVSelectors.positionsRows);
    const positions = [];

    for (const row of rows) {
      const text = row.innerText || row.textContent;
      if (!text || text.includes('Symbol') || text.includes('Side')) continue;

      const cells = row.querySelectorAll('div[class*="cell-"], td');
      if (cells.length >= 4) {
        const symbolText = cells[0].textContent.trim().split(/[\s,·\n]+/)[0];
        const sideText = cells[1].textContent.trim();
        const qtyText = cells[2].textContent.trim().replace(/,/g, '');
        const avgPriceText = cells[3].textContent.trim().replace(/[$,]/g, '');
        const curPriceText = cells.length > 4 ? cells[4].textContent.trim().replace(/[$,]/g, '') : avgPriceText;
        const pnlText = cells.length > 5 ? cells[5].textContent.trim().replace(/[$,+]/g, '') : '0';

        if (symbolText && symbolText.length > 0) {
          positions.push({
            symbol: symbolText.toUpperCase(),
            side: sideText,
            quantity: parseFloat(qtyText) || 1.0,
            avg_price: parseFloat(avgPriceText) || 0.0,
            current_price: parseFloat(curPriceText) || 0.0,
            unrealized_pnl: parseFloat(pnlText) || 0.0,
            stop_loss: 0.0,
            take_profit: 0.0
          });
        }
      }
    }

    this.activePositions = positions;
    return positions;
  },

  /**
   * Scrapes closed trade history from History tab
   */
  scrapeClosedTrades() {
    const historyRows = window.findTVAllElements(window.TVSelectors.historyRows);
    const closed = [];

    for (const row of historyRows) {
      const cells = row.querySelectorAll('div[class*="cell-"], td');
      if (cells.length >= 5) {
        const symbol = cells[0].textContent.trim();
        const typeOrSide = cells[1].textContent.trim();
        const exitPrice = parseFloat(cells[2].textContent.replace(/[$,]/g, '')) || 0.0;
        const pnl = parseFloat(cells[3].textContent.replace(/[$,+]/g, '')) || 0.0;
        const time = cells[4].textContent.trim();

        if (symbol) {
          closed.push({
            symbol: symbol.toUpperCase(),
            exit_price: exitPrice,
            gross_pnl: pnl,
            closed_at: time
          });
        }
      }
    }

    return closed;
  }
};

window.PositionTracker = PositionTracker;
