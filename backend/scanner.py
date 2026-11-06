import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from backend.alpaca_client import AlpacaClient, DEFAULT_US_UNIVERSE
from backend.strategy.engine import StrategyEngine
from backend.signals import SignalManager
from backend.database import get_config_val, set_config_val, log_system_event

logger = logging.getLogger(__name__)

class StockScanner:
    def __init__(self, alpaca_client: Optional[AlpacaClient] = None):
        self.alpaca = alpaca_client or AlpacaClient()
        self.strategy = StrategyEngine()
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self.latest_scan_results: Dict[str, Any] = {
            "status": "IDLE",
            "last_scan_time": None,
            "total_universe_count": 0,
            "filtered_count": 0,
            "qualified_count": 0,
            "scanned_symbols": [],
            "qualified_stocks": [],
            "rejections": []
        }
        self._bar_cache: Dict[str, Dict[str, Any]] = {}

    def get_config(self) -> Dict[str, Any]:
        return {
            "min_price": float(get_config_val("scanner_min_price", 10.0)),
            "min_avg_volume": float(get_config_val("scanner_min_avg_volume", 100000.0)),
            "min_dollar_volume": float(get_config_val("scanner_min_dollar_volume", 2000000.0)),
            "max_stocks_to_analyze": int(get_config_val("scanner_max_stocks", 20)),
            "scan_interval_seconds": int(get_config_val("scanner_interval_seconds", 300)),
            "custom_watchlist": get_config_val("scanner_custom_watchlist", []),
            "exclusions": get_config_val("scanner_exclusions", ["SQQQ", "TQQQ", "SOXL", "SOXS"])
        }

    def save_config(self, cfg: Dict[str, Any]):
        for k, v in cfg.items():
            set_config_val(f"scanner_{k}", v)

    def scan_once(self) -> Dict[str, Any]:
        """
        Executes a single synchronous scan across the universe.
        """
        cfg = self.get_config()
        self.latest_scan_results["status"] = "SCANNING"
        scan_time = datetime.now(timezone.utc).isoformat()
        self.latest_scan_results["last_scan_time"] = scan_time

        # 1. Determine Universe
        universe = cfg["custom_watchlist"]
        if not universe or len(universe) == 0:
            if self.alpaca.is_configured():
                universe = self.alpaca.fetch_active_us_equities()
            else:
                universe = list(DEFAULT_US_UNIVERSE)

        # Apply exclusions
        exclusions = set(cfg.get("exclusions", []))
        candidate_symbols = [s for s in universe if s not in exclusions][:150] # Batch limit for safety
        self.latest_scan_results["total_universe_count"] = len(candidate_symbols)

        # 2. Fetch Snapshots for Universe Screening
        filtered_symbols = []
        rejections = []
        snapshots = {}

        if self.alpaca.is_configured():
            snapshots = self.alpaca.get_snapshots(candidate_symbols)

        for sym in candidate_symbols:
            snap = snapshots.get(sym, {})
            daily_bar = snap.get("dailyBar", {})
            latest_trade = snap.get("latestTrade", {})
            
            price = latest_trade.get("p") or daily_bar.get("c", 0.0)
            vol = daily_bar.get("v", 0.0)
            dollar_vol = price * vol

            # If snapshots are empty (e.g. market closed, paper feed, or demo testing), allow symbol through with fallback
            if not price or price == 0:
                price = 100.0
                vol = 1000000.0
                dollar_vol = price * vol

            if price < cfg["min_price"]:
                rejections.append({
                    "symbol": sym, 
                    "reason": f"Price (${price:.2f}) < Min (${cfg['min_price']:.2f})"
                })
                continue
            
            if vol < cfg["min_avg_volume"] and self.alpaca.is_configured():
                rejections.append({
                    "symbol": sym, 
                    "reason": f"Volume ({vol:,.0f}) < Min ({cfg['min_avg_volume']:,.0f})"
                })
                continue

            if dollar_vol < cfg["min_dollar_volume"] and self.alpaca.is_configured():
                rejections.append({
                    "symbol": sym, 
                    "reason": f"Dollar Volume (${dollar_vol:,.0f}) < Min (${cfg['min_dollar_volume']:,.0f})"
                })
                continue

            filtered_symbols.append({"symbol": sym, "price": price, "dollar_vol": dollar_vol})

        # Sort filtered candidates by liquidity
        filtered_symbols.sort(key=lambda x: x["dollar_vol"], reverse=True)
        top_candidates = [item["symbol"] for item in filtered_symbols[:cfg["max_stocks_to_analyze"]]]
        self.latest_scan_results["filtered_count"] = len(top_candidates)

        # 3. Analyze Multi-Timeframe Strategy for Each Top Candidate
        qualified_stocks = []
        scanned_symbols = []

        for sym in top_candidates:
            # Fetch 1H, 15M, 5M bars
            candles_1h = self._get_cached_or_fetch_bars(sym, "1Hour", limit=50)
            candles_15m = self._get_cached_or_fetch_bars(sym, "15Min", limit=50)
            candles_5m = self._get_cached_or_fetch_bars(sym, "5Min", limit=50)

            if len(candles_1h) < 10 or len(candles_15m) < 12 or len(candles_5m) < 30:
                rejections.append({
                    "symbol": sym, 
                    "reason": f"Insufficient historical bars (1H:{len(candles_1h)}, 15M:{len(candles_15m)}, 5M:{len(candles_5m)})"
                })
                scanned_symbols.append({"symbol": sym, "status": "INSUFFICIENT_DATA", "score": 0.0})
                continue

            analysis = self.strategy.analyze_symbol(sym, candles_1h, candles_15m, candles_5m)
            
            scanned_symbols.append({
                "symbol": sym,
                "status": analysis["status"],
                "score": analysis["score"],
                "risk_reward": analysis["risk_reward"],
                "reasons": analysis["reasons"]
            })

            if analysis["status"] == "QUALIFIED" and analysis["signal"]:
                # Attempt to register signal in SignalManager
                created_signal = SignalManager.create_signal(analysis["signal"])
                if created_signal:
                    qualified_stocks.append(created_signal)
                else:
                    rejections.append({
                        "symbol": sym, 
                        "reason": "Duplicate signal prevented for active demand zone"
                    })
            else:
                rejections.append({
                    "symbol": sym, 
                    "reason": "; ".join(analysis["reasons"][:2])
                })

        self.latest_scan_results["status"] = "IDLE" if not self.is_running else "RUNNING"
        self.latest_scan_results["qualified_count"] = len(qualified_stocks)
        self.latest_scan_results["scanned_symbols"] = scanned_symbols
        self.latest_scan_results["qualified_stocks"] = qualified_stocks
        self.latest_scan_results["rejections"] = rejections

        log_system_event(
            "SCANNER", 
            f"Scan completed: {len(top_candidates)} analyzed, {len(qualified_stocks)} qualified.",
            metadata={"qualified": [q["symbol"] for q in qualified_stocks]}
        )

        return self.latest_scan_results

    def _get_cached_or_fetch_bars(self, symbol: str, timeframe: str, limit: int = 50) -> List[Dict[str, Any]]:
        cache_key = f"{symbol}_{timeframe}"
        now_ts = time.time()
        
        # Cache for 60 seconds to avoid repeated calls within the same minute
        if cache_key in self._bar_cache:
            entry = self._bar_cache[cache_key]
            if (now_ts - entry["timestamp"]) < 60:
                return entry["bars"]

        bars = self.alpaca.get_bars(symbol, timeframe, limit=limit)
        if bars:
            self._bar_cache[cache_key] = {"timestamp": now_ts, "bars": bars}
        return bars

    async def _scan_loop(self):
        logger.info("StockScanner background loop started.")
        while self.is_running:
            try:
                self.scan_once()
            except Exception as e:
                logger.error(f"Error in scanner loop: {e}", exc_info=True)
                log_system_event("SCANNER", f"Scanner loop error: {str(e)}", severity="ERROR")
            
            cfg = self.get_config()
            interval = max(30, cfg["scan_interval_seconds"])
            for _ in range(interval):
                if not self.is_running:
                    break
                await asyncio.sleep(1)

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.latest_scan_results["status"] = "RUNNING"
        set_config_val("scanner_is_running", True)
        self._task = asyncio.create_task(self._scan_loop())
        logger.info("StockScanner started.")

    def stop(self):
        self.is_running = False
        self.latest_scan_results["status"] = "STOPPED"
        set_config_val("scanner_is_running", False)
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("StockScanner stopped.")
