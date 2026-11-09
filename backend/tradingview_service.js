/**
 * TradingView Market Data Bridge Service
 * 
 * Community-maintained TradingView-API (@mathieuc/tradingview v4.1.1) integration.
 * Provides HTTP REST and WebSocket streaming interface for live US equities market data:
 * - Quotes & Snaphots (getQuote, getQuotes)
 * - Historical & Real-Time OHLCV Bars (getCandles, watchCandles)
 * - Screener & Hotlists (getScreener)
 * - Market Search (searchMarkets)
 */

const http = require('http');
const { WebSocketServer, WebSocket } = require('ws');
const { 
  getCandles, 
  watchCandles, 
  getQuote, 
  getQuotes, 
  getScreener, 
  searchMarkets 
} = require('@mathieuc/tradingview/data');

const PORT = parseInt(process.env.TV_SERVICE_PORT || '8002', 10);
const HOST = '127.0.0.1';

// Active live watchers: key -> { watcher, clients: Set<WebSocket>, lastCandles: Array }
const activeWatchers = new Map();

// Known US exchange mappings for standard large-caps
const KNOWN_US_EXCHANGES = {
  'AAPL': 'NASDAQ', 'MSFT': 'NASDAQ', 'NVDA': 'NASDAQ', 'AMZN': 'NASDAQ',
  'GOOGL': 'NASDAQ', 'GOOG': 'NASDAQ', 'META': 'NASDAQ', 'TSLA': 'NASDAQ',
  'AMD': 'NASDAQ', 'NFLX': 'NASDAQ', 'INTC': 'NASDAQ', 'QCOM': 'NASDAQ',
  'AVGO': 'NASDAQ', 'CSCO': 'NASDAQ', 'PYPL': 'NASDAQ', 'ADBE': 'NASDAQ',
  'CRM': 'NYSE', 'TXN': 'NASDAQ', 'MU': 'NASDAQ', 'AMAT': 'NASDAQ',
  'LRCX': 'NASDAQ', 'ADI': 'NASDAQ', 'KLAC': 'NASDAQ', 'SNPS': 'NASDAQ',
  'CDNS': 'NASDAQ', 'JPM': 'NYSE', 'BAC': 'NYSE', 'WFC': 'NYSE',
  'GS': 'NYSE', 'MS': 'NYSE', 'SPY': 'AMEX', 'QQQ': 'NASDAQ',
  'IWM': 'AMEX', 'DIA': 'NYSE', 'DIS': 'NYSE', 'BA': 'NYSE',
  'CAT': 'NYSE', 'GE': 'NYSE', 'XOM': 'NYSE', 'CVX': 'NYSE'
};

function resolveSymbol(sym) {
  if (!sym) return '';
  const clean = sym.trim().toUpperCase();
  if (clean.includes(':')) return clean;
  const ex = KNOWN_US_EXCHANGES[clean] || 'NASDAQ';
  return `${ex}:${clean}`;
}

function normalizeTimeframe(tf) {
  if (!tf) return '5';
  const str = String(tf).toLowerCase().trim();
  if (str === '1' || str === '1m' || str === '1min') return '1';
  if (str === '5' || str === '5m' || str === '5min') return '5';
  if (str === '15' || str === '15m' || str === '15min') return '15';
  if (str === '60' || str === '1h' || str === '1hour' || str === '60m' || str === '60min') return '60';
  if (str === 'd' || str === '1d' || str === '1day' || str === 'day') return 'D';
  if (str === 'w' || str === '1w' || str === '1week') return 'W';
  return tf;
}

// Format candle array to standard ISO format
function formatCandles(candles) {
  if (!Array.isArray(candles)) return [];
  return candles.map(c => {
    const tsSec = typeof c.time === 'number' ? c.time : Math.floor(Date.now() / 1000);
    const iso = new Date(tsSec * 1000).toISOString();
    const open = parseFloat(c.open || 0);
    const high = parseFloat(c.high || 0);
    const low = parseFloat(c.low || 0);
    const close = parseFloat(c.close || 0);
    const volume = parseFloat(c.volume || 0);
    const vwap = (high + low + close) / 3.0;

    return {
      timestamp: iso,
      time: tsSec,
      open,
      high,
      low,
      close,
      volume,
      vwap
    };
  });
}

// HTTP Server
const server = http.createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    return res.end();
  }

  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const pathname = url.pathname;

  // Helper to send JSON
  const sendJson = (statusCode, data) => {
    res.writeHead(statusCode, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(data));
  };

  // Helper to read POST body
  const readBody = () => new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (err) {
        reject(err);
      }
    });
    req.on('error', reject);
  });

  try {
    // 1. Health check
    if (pathname === '/health' || pathname === '/') {
      return sendJson(200, {
        status: 'HEALTHY',
        service: 'TradingView Market Data Engine',
        library: '@mathieuc/tradingview',
        version: '4.1.1',
        uptime_seconds: process.uptime(),
        active_watchers_count: activeWatchers.size,
        timestamp: new Date().toISOString()
      });
    }

    // 2. Single Symbol OHLCV Bars
    if (pathname === '/bars' && req.method === 'GET') {
      const rawSym = url.searchParams.get('symbol') || 'AAPL';
      const timeframe = normalizeTimeframe(url.searchParams.get('timeframe') || '5');
      const count = parseInt(url.searchParams.get('count') || '50', 10);
      const symbol = resolveSymbol(rawSym);

      const startTime = Date.now();
      try {
        const rawBars = await getCandles({
          symbol: symbol,
          timeframe: timeframe,
          count: count
        });

        const bars = formatCandles(rawBars);
        return sendJson(200, {
          success: true,
          symbol: rawSym.toUpperCase(),
          resolved_symbol: symbol,
          timeframe: timeframe,
          count: bars.length,
          latency_ms: Date.now() - startTime,
          bars: bars
        });
      } catch (err) {
        console.error(`[TradingView Service] getCandles error for ${symbol}:`, err.message);
        return sendJson(502, {
          success: false,
          symbol: rawSym.toUpperCase(),
          error: err.message || 'Failed to fetch candles from TradingView'
        });
      }
    }

    // 3. Batch Bars Request (POST)
    if (pathname === '/bars/batch' && req.method === 'POST') {
      const body = await readBody();
      const requests = body.requests || [];
      const startTime = Date.now();

      const results = {};
      const promises = requests.map(async (r) => {
        const sym = r.symbol || 'AAPL';
        const tf = normalizeTimeframe(r.timeframe || '5');
        const cnt = parseInt(r.count || '50', 10);
        const resolved = resolveSymbol(sym);
        const key = `${sym.toUpperCase()}_${tf}`;

        try {
          const rawBars = await getCandles({ symbol: resolved, timeframe: tf, count: cnt });
          results[key] = {
            success: true,
            symbol: sym.toUpperCase(),
            timeframe: tf,
            bars: formatCandles(rawBars)
          };
        } catch (e) {
          results[key] = {
            success: false,
            symbol: sym.toUpperCase(),
            timeframe: tf,
            error: e.message,
            bars: []
          };
        }
      });

      await Promise.allSettled(promises);
      return sendJson(200, {
        success: true,
        total_requested: requests.length,
        latency_ms: Date.now() - startTime,
        results: results
      });
    }

    // 4. Single Quote
    if (pathname === '/quote' && req.method === 'GET') {
      const rawSym = url.searchParams.get('symbol') || 'AAPL';
      const symbol = resolveSymbol(rawSym);
      const startTime = Date.now();

      try {
        const q = await getQuote(symbol);
        return sendJson(200, {
          success: true,
          symbol: rawSym.toUpperCase(),
          resolved_symbol: symbol,
          price: parseFloat(q.lp || 0),
          open: parseFloat(q.open_price || 0),
          high: parseFloat(q.high_price || 0),
          low: parseFloat(q.low_price || 0),
          prev_close: parseFloat(q.prev_close_price || 0),
          volume: parseFloat(q.volume || 0),
          change_pct: parseFloat(q.chp || 0),
          latency_ms: Date.now() - startTime,
          timestamp: q.lp_time ? new Date(q.lp_time * 1000).toISOString() : new Date().toISOString()
        });
      } catch (err) {
        return sendJson(502, {
          success: false,
          symbol: rawSym.toUpperCase(),
          error: err.message
        });
      }
    }

    // 5. Batch Quotes (POST) - equivalent to get_snapshots
    if (pathname === '/quotes' && req.method === 'POST') {
      const body = await readBody();
      const symbols = body.symbols || [];
      const startTime = Date.now();

      if (!symbols || symbols.length === 0) {
        return sendJson(200, { success: true, quotes: {} });
      }

      // Map to exchange-qualified
      const symbolMap = {};
      const tvSymbols = symbols.map(s => {
        const resolved = resolveSymbol(s);
        symbolMap[resolved] = s.toUpperCase();
        return resolved;
      });

      const standardizedQuotes = {};
      let batchError = null;

      try {
        const tvQuotes = await getQuotes({ symbols: tvSymbols });
        for (const [tvSym, q] of Object.entries(tvQuotes || {})) {
          if (!q) continue;
          const origSym = symbolMap[tvSym] || tvSym.split(':').pop();
          const price = parseFloat(q.lp || 0);
          const vol = parseFloat(q.volume || 0);
          const open = parseFloat(q.open_price || price);
          const high = parseFloat(q.high_price || price);
          const low = parseFloat(q.low_price || price);

          standardizedQuotes[origSym] = {
            symbol: origSym,
            resolved_symbol: tvSym,
            price: price,
            latestTrade: {
              p: price,
              s: 100,
              t: q.lp_time ? new Date(q.lp_time * 1000).toISOString() : new Date().toISOString()
            },
            dailyBar: {
              o: open,
              h: high,
              l: low,
              c: price,
              v: vol
            },
            volume: vol,
            change_pct: parseFloat(q.chp || 0)
          };
        }
      } catch (err) {
        batchError = err.message || String(err);
        console.warn(`[TradingView Service] Batch getQuotes failed (${batchError}). Falling back to per-symbol fetch...`);

        // Resilient fallback: fetch symbols individually using Promise.allSettled to isolate bad symbols
        const results = await Promise.allSettled(
          tvSymbols.map(async (tvSym) => {
            const q = await getQuote(tvSym);
            return { tvSym, q };
          })
        );

        for (const resItem of results) {
          if (resItem.status === 'fulfilled') {
            const { tvSym, q } = resItem.value;
            if (!q) continue;
            const origSym = symbolMap[tvSym] || tvSym.split(':').pop();
            const price = parseFloat(q.lp || 0);
            const vol = parseFloat(q.volume || 0);
            const open = parseFloat(q.open_price || price);
            const high = parseFloat(q.high_price || price);
            const low = parseFloat(q.low_price || price);

            standardizedQuotes[origSym] = {
              symbol: origSym,
              resolved_symbol: tvSym,
              price: price,
              latestTrade: {
                p: price,
                s: 100,
                t: q.lp_time ? new Date(q.lp_time * 1000).toISOString() : new Date().toISOString()
              },
              dailyBar: {
                o: open,
                h: high,
                l: low,
                c: price,
                v: vol
              },
              volume: vol,
              change_pct: parseFloat(q.chp || 0)
            };
          } else {
            console.warn(`[TradingView Service] Individual quote skipped: ${resItem.reason?.message || resItem.reason}`);
          }
        }
      }

      return sendJson(200, {
        success: true,
        total: Object.keys(standardizedQuotes).length,
        latency_ms: Date.now() - startTime,
        warning: batchError ? `Resilient fallback triggered: ${batchError}` : null,
        quotes: standardizedQuotes
      });
    }

    // 6. Screener & Universe Ranking
    if (pathname === '/screener' && (req.method === 'GET' || req.method === 'POST')) {
      const minPrice = parseFloat(url.searchParams.get('min_price') || '10.0');
      const minVolume = parseFloat(url.searchParams.get('min_volume') || '100000.0');
      const limit = parseInt(url.searchParams.get('limit') || '50', 10);
      const startTime = Date.now();

      try {
        const page = await getScreener({
          market: 'america',
          columns: ['name', 'close', 'volume', 'change', 'open', 'high', 'low'],
          filter: [
            { left: 'type', operation: 'equal', right: 'stock' },
            { left: 'close', operation: 'greater', right: minPrice },
            { left: 'volume', operation: 'greater', right: minVolume }
          ],
          sort: { sortBy: 'volume', sortOrder: 'desc' },
          range: [0, limit]
        });

        const stocks = (page.rows || []).map(r => {
          const symParts = (r.symbol || '').split(':');
          const exchange = symParts[0] || 'US';
          const ticker = symParts[1] || r.symbol;
          const vals = r.values || {};

          return {
            symbol: ticker,
            full_symbol: r.symbol,
            exchange: exchange,
            price: parseFloat(vals.close || 0),
            volume: parseFloat(vals.volume || 0),
            change_pct: parseFloat(vals.change || 0),
            open: parseFloat(vals.open || 0),
            high: parseFloat(vals.high || 0),
            low: parseFloat(vals.low || 0)
          };
        });

        return sendJson(200, {
          success: true,
          total_available: page.totalCount,
          count: stocks.length,
          latency_ms: Date.now() - startTime,
          stocks: stocks
        });
      } catch (err) {
        console.error('[TradingView Service] Screener error:', err.message);
        return sendJson(502, {
          success: false,
          error: err.message,
          stocks: []
        });
      }
    }

    // 7. Market Symbol Search
    if (pathname === '/search' && req.method === 'GET') {
      const text = url.searchParams.get('query') || 'AAPL';
      try {
        const results = await searchMarkets(text);
        const filtered = (results || []).slice(0, 10).map(m => ({
          id: m.id,
          symbol: m.symbol,
          exchange: m.exchange,
          description: m.description,
          type: m.type
        }));
        return sendJson(200, { success: true, results: filtered });
      } catch (err) {
        return sendJson(502, { success: false, error: err.message, results: [] });
      }
    }

    // 8. Service Diagnostics & Validation Report
    if (pathname === '/diagnostics' && req.method === 'GET') {
      return sendJson(200, {
        success: true,
        service: 'TradingView Market Data Service',
        provider: '@mathieuc/tradingview (Community Mathieu2301/TradingView-API)',
        status: 'CONNECTED',
        uptime_seconds: process.uptime(),
        active_watchers: Array.from(activeWatchers.keys()),
        feed_coverage: 'Consolidated US Equities Tape (NYSE + NASDAQ + AMEX)',
        supported_timeframes: ['1', '5', '15', '60', 'D'],
        known_limitations: [
          'Anonymous WebSocket sessions cap deep historical queries at ~7,000 bars',
          'Inter-session market closures (weekends/holidays) create normal timestamp gaps',
          'High concurrent bulk socket requests may encounter TradingView rate-limiting'
        ],
        timestamp: new Date().toISOString()
      });
    }

    // 404
    sendJson(404, { error: `Endpoint '${pathname}' not found` });
  } catch (err) {
    console.error('[TradingView Service] Request unhandled error:', err);
    sendJson(500, { error: err.message || 'Internal Server Error' });
  }
});

// WebSocket Server for live streaming
const wss = new WebSocketServer({ server });

wss.on('connection', (ws) => {
  ws.isAlive = true;
  ws.subscribedWatchers = new Set();

  ws.on('pong', () => { ws.isAlive = true; });

  ws.on('message', async (messageData) => {
    try {
      const msg = JSON.parse(messageData.toString());
      const action = msg.action;

      if (action === 'ping') {
        return ws.send(JSON.stringify({ type: 'pong', timestamp: new Date().toISOString() }));
      }

      if (action === 'watch') {
        const rawSym = msg.symbol || 'AAPL';
        const tf = normalizeTimeframe(msg.timeframe || '5');
        const count = parseInt(msg.count || '50', 10);
        const resolved = resolveSymbol(rawSym);
        const key = `${resolved}_${tf}`;

        ws.subscribedWatchers.add(key);

        // Check if existing watcher already active
        if (activeWatchers.has(key)) {
          const entry = activeWatchers.get(key);
          entry.clients.add(ws);
          if (entry.lastCandles && entry.lastCandles.length > 0) {
            ws.send(JSON.stringify({
              type: 'CANDLE_UPDATE',
              symbol: rawSym.toUpperCase(),
              resolved_symbol: resolved,
              timeframe: tf,
              candles: entry.lastCandles
            }));
          }
          return;
        }

        // Start new watchCandles
        try {
          const entry = {
            clients: new Set([ws]),
            lastCandles: [],
            watcher: null
          };
          activeWatchers.set(key, entry);

          const watcher = await watchCandles(
            { symbol: resolved, timeframe: tf, count: count },
            {
              onData(candles) {
                const formatted = formatCandles(candles);
                entry.lastCandles = formatted;

                const payload = JSON.stringify({
                  type: 'CANDLE_UPDATE',
                  symbol: rawSym.toUpperCase(),
                  resolved_symbol: resolved,
                  timeframe: tf,
                  candles: formatted
                });

                for (const client of entry.clients) {
                  if (client.readyState === WebSocket.OPEN) {
                    client.send(payload);
                  }
                }
              },
              onError(err) {
                console.warn(`[TradingView Service] Watcher error for ${key}:`, err.message);
              }
            }
          );

          entry.watcher = watcher;

          // Auto-reconnect handling if watcher closes unexpectedly
          watcher.closed.then(() => {
            if (activeWatchers.has(key) && entry.clients.size > 0) {
              console.log(`[TradingView Service] Watcher ${key} closed. Reconnecting in 3s...`);
              setTimeout(async () => {
                if (activeWatchers.has(key) && entry.clients.size > 0) {
                  try {
                    entry.watcher = await watchCandles({ symbol: resolved, timeframe: tf, count: count }, {
                      onData: (candles) => {
                        const formatted = formatCandles(candles);
                        entry.lastCandles = formatted;
                        const payload = JSON.stringify({
                          type: 'CANDLE_UPDATE',
                          symbol: rawSym.toUpperCase(),
                          resolved_symbol: resolved,
                          timeframe: tf,
                          candles: formatted
                        });
                        for (const client of entry.clients) {
                          if (client.readyState === WebSocket.OPEN) client.send(payload);
                        }
                      },
                      onError: (e) => console.warn(`Reconnected watcher error: ${e.message}`)
                    });
                  } catch (recErr) {
                    console.error(`Failed to reconnect watcher for ${key}:`, recErr.message);
                  }
                }
              }, 3000);
            }
          });

        } catch (watchErr) {
          console.error(`[TradingView Service] Failed to initialize watcher for ${key}:`, watchErr.message);
          activeWatchers.delete(key);
          ws.send(JSON.stringify({
            type: 'ERROR',
            symbol: rawSym.toUpperCase(),
            error: watchErr.message
          }));
        }
      }

      if (action === 'unwatch') {
        const rawSym = msg.symbol || 'AAPL';
        const tf = normalizeTimeframe(msg.timeframe || '5');
        const resolved = resolveSymbol(rawSym);
        const key = `${resolved}_${tf}`;

        ws.subscribedWatchers.delete(key);
        if (activeWatchers.has(key)) {
          const entry = activeWatchers.get(key);
          entry.clients.delete(ws);
          if (entry.clients.size === 0) {
            if (entry.watcher && entry.watcher.stop) {
              entry.watcher.stop().catch(() => {});
            }
            activeWatchers.delete(key);
          }
        }
      }
    } catch (err) {
      console.warn('[TradingView Service] Invalid WebSocket message:', err.message);
    }
  });

  ws.on('close', () => {
    for (const key of ws.subscribedWatchers) {
      if (activeWatchers.has(key)) {
        const entry = activeWatchers.get(key);
        entry.clients.delete(ws);
        if (entry.clients.size === 0) {
          if (entry.watcher && entry.watcher.stop) {
            entry.watcher.stop().catch(() => {});
          }
          activeWatchers.delete(key);
        }
      }
    }
  });
});

// Periodic heartbeat for WebSocket clients
setInterval(() => {
  for (const ws of wss.clients) {
    if (!ws.isAlive) return ws.terminate();
    ws.isAlive = false;
    ws.ping();
  }
}, 30000);

server.listen(PORT, HOST, () => {
  console.log(`[TradingView Service] Running on http://${HOST}:${PORT} (PID: ${process.pid})`);
});

// Handle graceful exit
function shutdown() {
  console.log('[TradingView Service] Shutting down gracefully...');
  for (const [key, entry] of activeWatchers.entries()) {
    if (entry.watcher && entry.watcher.stop) {
      entry.watcher.stop().catch(() => {});
    }
  }
  server.close(() => {
    process.exit(0);
  });
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

