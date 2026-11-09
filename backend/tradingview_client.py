"""
TradingView Market Data Client.

Replaces Alpaca as the primary live US equities market data provider.
Integrates with the Node.js TradingView-API bridge service (@mathieuc/tradingview)
running locally, and enforces strict automated data verification via DataValidator.

Strict Rules:
- Market data ONLY. Execution is never performed here.
- Never silently fabricate or substitute missing data.
- Enforce OHLCV structural integrity and chronological monotonicity.
- Support 5M, 15M, and 1H timeframes.
"""

import logging
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

import httpx

from backend.database import get_config_val, set_config_val, log_system_event
from backend.data_validator import DataValidator

logger = logging.getLogger(__name__)

# Strict ticker validation: 1–5 uppercase letters, optional suffix like .A or -B
_VALID_TICKER_RE = re.compile(r'^[A-Z]{1,5}([.\-][A-Z]{1,2})?$')
# Known test/placeholder symbols that must never reach production TradingView API
_KNOWN_PLACEHOLDERS = frozenset({"EMPTY_SYM", "ZERO_PRICE_SYM", "TEST", "FAKE", "DUMMY"})


def is_valid_ticker(symbol: str) -> bool:
    """Returns True only for real US equity tickers; rejects test placeholders and malformed strings."""
    s = symbol.strip().upper() if symbol else ""
    if not s or s in _KNOWN_PLACEHOLDERS:
        return False
    return bool(_VALID_TICKER_RE.match(s))

# Curated high-liquidity US equities default universe
DEFAULT_US_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD",
    "NFLX", "INTC", "QCOM", "AVGO", "CSCO", "PYPL", "ADBE", "CRM",
    "TXN", "MU", "AMAT", "LRCX", "ADI", "KLAC", "SNPS", "CDNS",
    "JPM", "BAC", "WFC", "GS", "MS", "SPY", "QQQ", "IWM", "DIA"
]

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
SERVICE_SCRIPT = PROJECT_ROOT / "backend" / "tradingview_service.js"


class TradingViewClient:
    """
    Python client for the TradingView market data bridge service.
    Provides identical interfaces to downstream consumers with real-time consolidated tape data.
    """

    _service_process: Optional[subprocess.Popen] = None
    _last_quote_success_time: Optional[float] = None
    _last_candle_success_time: Optional[float] = None

    def __init__(self, service_url: Optional[str] = None):
        self.service_url = (service_url or get_config_val("tradingview_service_url", "http://127.0.0.1:8002")).rstrip("/")
        self.validator = DataValidator()
        self._last_health_check_ts: float = 0.0
        self._last_health_status: bool = False
        self.feed = "consolidated"

    def ensure_service_running(self, timeout_seconds: float = 6.0) -> bool:
        """
        Verifies that the Node.js bridge service is listening on service_url.
        If unreachable, automatically spawns backend/tradingview_service.js in background.
        """
        now = time.time()
        # Cache healthy state for 10 seconds to avoid unnecessary polling
        if self._last_health_status and (now - self._last_health_check_ts < 10.0):
            return True

        # 1. Quick probe to /health
        try:
            with httpx.Client(timeout=1.5) as client:
                res = client.get(f"{self.service_url}/health")
                if res.status_code == 200:
                    self._last_health_check_ts = now
                    self._last_health_status = True
                    return True
        except Exception:
            pass

        # 2. Service not responding, attempt to spawn
        logger.info(f"TradingView Node service not detected on {self.service_url}. Spawning process...")
        if not SERVICE_SCRIPT.exists():
            logger.error(f"TradingView service script not found at {SERVICE_SCRIPT}")
            self._last_health_status = False
            return False

        try:
            creation_flags = 0
            if os.name == "nt":
                creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

            proc = subprocess.Popen(
                ["node", str(SERVICE_SCRIPT)],
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags
            )
            TradingViewClient._service_process = proc
            logger.info(f"Spawned TradingView service PID {proc.pid}")
        except Exception as e:
            logger.error(f"Failed to spawn TradingView service process: {e}")
            self._last_health_status = False
            return False

        # 3. Wait for readiness
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                with httpx.Client(timeout=1.0) as client:
                    res = client.get(f"{self.service_url}/health")
                    if res.status_code == 200:
                        self._last_health_check_ts = time.time()
                        self._last_health_status = True
                        log_system_event(
                            "TRADINGVIEW_DATA",
                            f"TradingView market data service started successfully on {self.service_url}",
                            severity="INFO"
                        )
                        return True
            except Exception:
                time.sleep(0.5)

        logger.error(f"TradingView service did not respond within {timeout_seconds}s.")
        self._last_health_status = False
        return False

    def is_configured(self) -> bool:
        """
        Returns True if the TradingView market data service is responsive or can be started.
        """
        return self.ensure_service_running(timeout_seconds=3.0)

    def test_connection(self) -> Dict[str, Any]:
        """
        Validates live connection to TradingView market data service and tests data retrieval.
        - Probes service health.
        - Fetches sample 5M candle for AAPL.
        - Fetches real-time quote for AAPL.
        - Runs DataValidator on returned market data.
        """
        result = {
            "success": False,
            "status": "FAILED",
            "message": "",
            "feed": "TradingView Consolidated",
            "feed_description": "TradingView Consolidated US Equities Tape (NYSE + NASDAQ + AMEX)",
            "historical_candle_access": False,
            "real_time_access": False,
            "latency_ms": 0.0,
            "sample_candle": None,
            "sample_snapshot": None,
            "validation_report": None
        }

        start_time = time.time()
        if not self.ensure_service_running(timeout_seconds=5.0):
            result["message"] = f"TradingView bridge service is not running on {self.service_url}."
            set_config_val("tradingview_connection_status", {
                "status": "FAILED",
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "error": result["message"]
            })
            log_system_event("TRADINGVIEW_DATA", result["message"], severity="ERROR")
            return result

        test_symbol = "AAPL"
        received_bars = {}
        received_quotes = {}

        try:
            with httpx.Client(timeout=12.0) as client:
                # 1. Test Historical Candle Access
                bars_res = client.get(
                    f"{self.service_url}/bars",
                    params={"symbol": test_symbol, "timeframe": "5", "count": 10}
                )
                if bars_res.status_code == 200:
                    data = bars_res.json()
                    bars = data.get("bars", [])
                    if bars:
                        result["historical_candle_access"] = True
                        received_bars[test_symbol] = bars
                        last_b = bars[-1]
                        result["sample_candle"] = {
                            "symbol": test_symbol,
                            "time": last_b.get("timestamp"),
                            "open": last_b.get("open"),
                            "high": last_b.get("high"),
                            "low": last_b.get("low"),
                            "close": last_b.get("close"),
                            "volume": last_b.get("volume")
                        }

                # 2. Test Real-Time Quote Access
                quote_res = client.get(f"{self.service_url}/quote", params={"symbol": test_symbol})
                if quote_res.status_code == 200:
                    q = quote_res.json()
                    if q.get("success"):
                        result["real_time_access"] = True
                        received_quotes[test_symbol] = q
                        result["sample_snapshot"] = {
                            "symbol": test_symbol,
                            "price": q.get("price"),
                            "open": q.get("open"),
                            "high": q.get("high"),
                            "low": q.get("low"),
                            "volume": q.get("volume"),
                            "timestamp": q.get("timestamp")
                        }

        except Exception as e:
            result["message"] = f"Network communication error with TradingView service: {str(e)}"
            logger.error(result["message"])
            return result

        total_latency = (time.time() - start_time) * 1000.0
        result["latency_ms"] = round(total_latency, 2)

        # 3. Run Automated Validation Layer
        report = self.validator.generate_validation_report(
            requested_symbols=[test_symbol],
            received_bars=received_bars,
            received_quotes=received_quotes,
            latency_ms=total_latency,
            timeframe="5m"
        )
        result["validation_report"] = report

        if result["historical_candle_access"] and report["validation_passed"]:
            result["success"] = True
            result["status"] = "CONNECTED"
            result["message"] = (
                f"Successfully connected to TradingView Consolidated US Equities Feed. "
                f"Historical 5M candles validated. Real-time access: {'Active' if result['real_time_access'] else 'Unavailable'}. "
                f"Latency: {result['latency_ms']:.1f}ms."
            )
            set_config_val("tradingview_connection_status", {
                "status": "CONNECTED",
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "feed": result["feed"],
                "latency_ms": result["latency_ms"],
                "real_time": result["real_time_access"]
            })
            log_system_event("TRADINGVIEW_DATA", result["message"], severity="INFO")
        else:
            result["status"] = "FAILED"
            fail_reasons = report.get("failure_reasons", [])
            err_details = "; ".join(fail_reasons) if fail_reasons else "Data validation failed."
            result["message"] = f"TradingView connection succeeded, but data validation failed: {err_details}"
            set_config_val("tradingview_connection_status", {
                "status": "FAILED",
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "error": result["message"]
            })
            log_system_event("TRADINGVIEW_DATA", result["message"], severity="WARNING")

        return result

    def get_bars(
        self,
        symbol: str,
        timeframe: str = "5Min",
        limit: int = 100,
        end_dt: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch standardized OHLCV bars for a US equity symbol.
        Normalizes timeframes ('1Hour'/'60m' -> '60', '15Min'/'15m' -> '15', '5Min'/'5m' -> '5', '1Day' -> 'D').
        Enforces automated data validation before returning bars.
        Returns:
        [{'timestamp': str, 'open': float, 'high': float, 'low': float, 'close': float, 'volume': float, 'vwap': float}]
        """
        if not self.ensure_service_running():
            logger.error("TradingView service is unavailable for get_bars.")
            return []

        # Map timeframe to TradingView format
        tf_map = {
            "1m": "1", "1min": "1",
            "5m": "5", "5min": "5",
            "15m": "15", "15min": "15",
            "1h": "60", "1hour": "60", "60m": "60", "60min": "60",
            "1d": "D", "1day": "D", "d": "D"
        }
        tv_tf = tf_map.get(timeframe.lower(), "5")

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.get(
                    f"{self.service_url}/bars",
                    params={"symbol": symbol, "timeframe": tv_tf, "count": limit}
                )
                if res.status_code != 200:
                    logger.error(f"TradingView /bars request failed for {symbol} ({res.status_code}): {res.text}")
                    return []

                data = res.json()
                if not data.get("success"):
                    logger.error(f"TradingView returned failure for {symbol}: {data.get('error')}")
                    return []

                raw_bars = data.get("bars", [])
                if not raw_bars:
                    logger.warning(f"No bars returned for {symbol} ({tv_tf})")
                    return []

                # Enforce DataValidator constraints
                is_valid, errors, stats = self.validator.validate_bars_series(raw_bars, symbol, timeframe=tv_tf)
                if not is_valid:
                    logger.error(f"Market data validation failed for {symbol} ({tv_tf}): {'; '.join(errors[:3])}")
                    return []

                TradingViewClient._last_candle_success_time = time.time()
                return raw_bars

        except Exception as e:
            logger.error(f"Error fetching bars for {symbol} from TradingView service: {e}")
            return []

    def get_snapshots(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetch current market snapshots (latest trade, latest quote, daily bar) for multiple symbols.
        Returns standardized snapshot dictionary:
        {
            sym: {
                "symbol": sym,
                "latestTrade": {"p": price, "s": 100, "t": iso_ts},
                "dailyBar": {"o": open, "h": high, "l": low, "c": price, "v": volume},
                "volume": volume,
                "price": price
            }
        }
        """
        if not symbols or not self.ensure_service_running():
            return {}

        # Deduplicate while preserving order
        clean_symbols = list(dict.fromkeys(s.strip().upper() for s in symbols if s and isinstance(s, str)))
        try:
            with httpx.Client(timeout=20.0) as client:
                res = client.post(
                    f"{self.service_url}/quotes",
                    json={"symbols": clean_symbols}
                )
                if res.status_code != 200:
                    logger.error(f"TradingView /quotes request failed ({res.status_code}): {res.text}")
                    return {}

                data = res.json()
                if not data.get("success"):
                    logger.error(f"TradingView /quotes returned failure: {data.get('error')}")
                    return {}

                quotes = data.get("quotes", {})
                if quotes:
                    TradingViewClient._last_quote_success_time = time.time()
                return quotes

        except Exception as e:
            logger.error(f"Error fetching snapshots from TradingView service: {e}")
            return {}

    def get_diagnostics(self) -> Dict[str, Any]:
        """
        Gathers diagnostic health telemetry from the TradingView market data bridge.
        """
        is_healthy = self.ensure_service_running(timeout_seconds=2.0)
        bridge_info = {}
        if is_healthy:
            try:
                with httpx.Client(timeout=2.0) as client:
                    diag_res = client.get(f"{self.service_url}/diagnostics")
                    if diag_res.status_code == 200:
                        bridge_info = diag_res.json()
            except Exception:
                pass

        quote_ts = (
            datetime.fromtimestamp(TradingViewClient._last_quote_success_time, tz=timezone.utc).isoformat()
            if TradingViewClient._last_quote_success_time
            else None
        )
        candle_ts = (
            datetime.fromtimestamp(TradingViewClient._last_candle_success_time, tz=timezone.utc)
            if TradingViewClient._last_candle_success_time
            else None
        )

        freshness_threshold = int(get_config_val("quote_freshness_threshold_seconds", 120))

        return {
            "bridge_connected": is_healthy,
            "service_url": self.service_url,
            "provider": "@mathieuc/tradingview (Community)",
            "last_successful_quote_time": quote_ts,
            "last_successful_candle_time": candle_ts,
            "quote_freshness_threshold_seconds": freshness_threshold,
            "feed_status": "CONNECTED" if is_healthy else "DISCONNECTED",
            "feed_label": "TradingView Market Data Connected" if is_healthy else "TradingView Market Data Offline",
            "bridge_diagnostics": bridge_info
        }

    def fetch_active_us_equities(self) -> List[str]:
        """
        Fetch active US-listed common stock symbols using TradingView screener.
        Filters by minimum price ($10.0) and minimum volume (100,000).
        Falls back to curated liquid US universe if screener is unavailable.
        """
        if not self.ensure_service_running():
            return list(DEFAULT_US_UNIVERSE)

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.get(
                    f"{self.service_url}/screener",
                    params={"min_price": 10.0, "min_volume": 100000.0, "limit": 60}
                )
                if res.status_code == 200:
                    data = res.json()
                    stocks = data.get("stocks", [])
                    raw_symbols = [s["symbol"].strip().upper() for s in stocks if s.get("symbol")]
                    symbols = [s for s in raw_symbols if is_valid_ticker(s)]
                    symbols = list(dict.fromkeys(symbols))
                    if len(symbols) >= 10:
                        logger.info(f"Fetched {len(symbols)} active US equities from TradingView screener.")
                        return symbols

        except Exception as e:
            logger.warning(f"Failed to fetch assets from TradingView screener: {e}")

        return list(DEFAULT_US_UNIVERSE)

    def get_validation_report(
        self,
        symbols: Optional[List[str]] = None,
        timeframe: str = "5"
    ) -> Dict[str, Any]:
        """
        Runs comprehensive data verification across a basket of US equities and produces
        a structured validation report.
        """
        target_symbols = symbols or ["AAPL", "MSFT", "NVDA", "TSLA"]
        start_time = time.time()

        if not self.ensure_service_running():
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "validation_passed": False,
                "error": "TradingView service unreachable",
                "total_symbols_requested": len(target_symbols),
                "total_symbols_received": 0,
                "successful_subscriptions": 0,
                "failed_subscriptions": len(target_symbols),
                "candle_completeness_pct": 0.0,
                "invalid_record_count": len(target_symbols),
                "failure_reasons": ["TradingView bridge service is not running"],
                "data_latency_ms": 0.0,
                "latest_update_timestamp": None,
                "feed_source": "TradingView Real-Time Consolidated Tape",
                "feed_coverage": "Consolidated US Equities Tape (NYSE, NASDAQ, AMEX)",
                "known_limitations": [],
                "discrepancies": ["Service offline"],
                "symbol_details": {}
            }

        received_bars = {}
        for sym in target_symbols:
            bars = self.get_bars(sym, timeframe=timeframe, limit=30)
            if bars:
                received_bars[sym] = bars

        received_quotes = self.get_snapshots(target_symbols)
        latency = (time.time() - start_time) * 1000.0

        return self.validator.generate_validation_report(
            requested_symbols=target_symbols,
            received_bars=received_bars,
            received_quotes=received_quotes,
            latency_ms=latency,
            timeframe=timeframe
        )

