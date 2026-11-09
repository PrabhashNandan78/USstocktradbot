import logging
import httpx
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from backend.database import get_config_val, set_config_val, log_system_event

logger = logging.getLogger(__name__)

ALPACA_DATA_URL = "https://data.alpaca.markets/v2"
ALPACA_PAPER_URL = "https://paper-api.alpaca.markets/v2"

# Curated high-liquidity US equities default universe
DEFAULT_US_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", 
    "NFLX", "INTC", "QCOM", "AVGO", "CSCO", "PYPL", "ADBE", "CRM",
    "TXN", "MU", "AMAT", "LRCX", "ADI", "KLAC", "SNPS", "CDNS",
    "JPM", "BAC", "WFC", "GS", "MS", "SPY", "QQQ", "IWM", "DIA"
]

class AlpacaClient:
    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None, feed: str = "iex"):
        self.api_key = api_key or get_config_val("alpaca_api_key", "")
        self.secret_key = secret_key or get_config_val("alpaca_secret_key", "")
        self.feed = feed or get_config_val("alpaca_feed", "iex")
        # Ensure feed is lowercase (iex or sip)
        self.feed = self.feed.lower() if self.feed else "iex"

    def _get_headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key.strip(),
            "APCA-API-SECRET-KEY": self.secret_key.strip(),
            "accept": "application/json"
        }

    def is_configured(self) -> bool:
        return bool(self.api_key and self.secret_key)

    def test_connection(self) -> Dict[str, Any]:
        """
        Validates credentials against Alpaca Data API without placing trades.
        Tests both historical candle access and snapshot access.
        """
        if not self.is_configured():
            return {
                "success": False,
                "status": "NOT_CONFIGURED",
                "message": "Alpaca API Key and Secret Key are required.",
                "feed": self.feed,
                "historical_candle_access": False,
                "real_time_access": False,
                "feed_notice": "No credentials supplied."
            }

        headers = self._get_headers()
        test_symbol = "AAPL"
        result = {
            "success": False,
            "status": "FAILED",
            "message": "",
            "feed": self.feed,
            "feed_description": (
                "Investors Exchange (IEX) - Top-of-book / partial US equity volume." 
                if self.feed == "iex" else 
                "Securities Information Processor (SIP) - Full consolidated US equity tape (requires paid subscription)."
            ),
            "historical_candle_access": False,
            "real_time_access": False,
            "sample_candle": None,
            "sample_snapshot": None
        }

        # 1. Test Historical Bars Access
        try:
            # End time yesterday or 15 mins ago to respect 15-min delay on free feed
            end_time = datetime.now(timezone.utc) - timedelta(minutes=16)
            start_time = end_time - timedelta(days=5)
            
            params = {
                "symbols": test_symbol,
                "timeframe": "1Hour",
                "start": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "limit": 5,
                "feed": self.feed
            }
            
            with httpx.Client(timeout=10.0) as client:
                res = client.get(f"{ALPACA_DATA_URL}/stocks/bars", headers=headers, params=params)
                
                if res.status_code == 401 or res.status_code == 403:
                    result["message"] = f"Authentication failed ({res.status_code}): Invalid Alpaca API Key or Secret."
                    log_system_event("ALPACA", f"Authentication failed: {res.text}", severity="ERROR")
                    return result
                elif res.status_code == 422:
                    result["message"] = f"Feed error ({res.status_code}): {res.text}. You may not have access to '{self.feed}' feed."
                    log_system_event("ALPACA", f"Feed error: {res.text}", severity="WARNING")
                    return result
                elif res.status_code != 200:
                    result["message"] = f"Historical bar request failed ({res.status_code}): {res.text}"
                    log_system_event("ALPACA", f"Bar request failed: {res.text}", severity="ERROR")
                    return result
                
                data = res.json()
                bars = data.get("bars", {}).get(test_symbol, [])
                if bars:
                    result["historical_candle_access"] = True
                    result["sample_candle"] = {
                        "symbol": test_symbol,
                        "time": bars[-1].get("t"),
                        "close": bars[-1].get("c"),
                        "volume": bars[-1].get("v")
                    }
                else:
                    result["historical_candle_access"] = True
                    result["message"] = "Connected, but no bars returned for test range."

        except httpx.RequestError as e:
            result["message"] = f"Network connection error to Alpaca: {str(e)}"
            return result
        except Exception as e:
            result["message"] = f"Unexpected error during historical bar test: {str(e)}"
            return result

        # 2. Test Real-time / Snapshot Access
        try:
            with httpx.Client(timeout=10.0) as client:
                snap_params = {"symbols": test_symbol, "feed": self.feed}
                res = client.get(f"{ALPACA_DATA_URL}/stocks/snapshots", headers=headers, params=snap_params)
                if res.status_code == 200:
                    snap_data = res.json()
                    if test_symbol in snap_data:
                        result["real_time_access"] = True
                        snap = snap_data[test_symbol]
                        latest_trade = snap.get("latestTrade", {})
                        result["sample_snapshot"] = {
                            "symbol": test_symbol,
                            "price": latest_trade.get("p"),
                            "size": latest_trade.get("s"),
                            "timestamp": latest_trade.get("t")
                        }
                else:
                    # Some accounts without live data might fail snapshot but pass bars
                    logger.warning(f"Snapshot test returned {res.status_code}: {res.text}")
        except Exception as e:
            logger.warning(f"Snapshot test failed: {e}")

        if result["historical_candle_access"]:
            result["success"] = True
            result["status"] = "CONNECTED"
            result["message"] = (
                f"Successfully connected to Alpaca Market Data ({self.feed.upper()} feed). "
                f"Historical candles validated. Real-time access: {'Active' if result['real_time_access'] else 'Unavailable/Delayed'}."
            )
            set_config_val("alpaca_connection_status", {
                "status": "CONNECTED",
                "feed": self.feed,
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "real_time": result["real_time_access"]
            })
            log_system_event("ALPACA", result["message"], severity="INFO")
        else:
            result["status"] = "FAILED"
            set_config_val("alpaca_connection_status", {
                "status": "FAILED",
                "feed": self.feed,
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "error": result["message"]
            })

        return result

    def get_bars(self, symbol: str, timeframe: str = "5Min", limit: int = 100, end_dt: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Fetch OHLCV bars for a symbol.
        Timeframe options: '1Hour', '15Min', '5Min', '1Day'.
        Returns list of standardized candle dicts:
        [{'timestamp': str, 'open': float, 'high': float, 'low': float, 'close': float, 'volume': float, 'vwap': float}]
        """
        if not self.is_configured():
            logger.warning("Alpaca credentials not configured.")
            return []

        # Standardize timeframe parameter
        tf_map = {
            "1h": "1Hour", "1hour": "1Hour", "60min": "1Hour",
            "15m": "15Min", "15min": "15Min",
            "5m": "5Min", "5min": "5Min",
            "1d": "1Day", "1day": "1Day"
        }
        api_tf = tf_map.get(timeframe.lower(), timeframe)

        headers = self._get_headers()
        params = {
            "symbols": symbol,
            "timeframe": api_tf,
            "limit": limit,
            "feed": self.feed,
            "sort": "asc"
        }

        if end_dt:
            params["end"] = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            with httpx.Client(timeout=12.0) as client:
                res = client.get(f"{ALPACA_DATA_URL}/stocks/bars", headers=headers, params=params)
                if res.status_code != 200:
                    logger.error(f"Alpaca get_bars failed for {symbol} ({res.status_code}): {res.text}")
                    return []
                
                data = res.json()
                bars_list = data.get("bars", {}).get(symbol, [])
                
                standardized = []
                for b in bars_list:
                    standardized.append({
                        "timestamp": b.get("t"),
                        "open": float(b.get("o", 0.0)),
                        "high": float(b.get("h", 0.0)),
                        "low": float(b.get("l", 0.0)),
                        "close": float(b.get("c", 0.0)),
                        "volume": float(b.get("v", 0.0)),
                        "vwap": float(b.get("vw", b.get("c", 0.0)))
                    })
                return standardized
        except Exception as e:
            logger.error(f"Error fetching bars for {symbol}: {e}")
            return []

    def get_snapshots(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetch current market snapshots (latest trade, latest quote, daily bar, previous daily bar).
        """
        if not self.is_configured() or not symbols:
            return {}

        headers = self._get_headers()
        # Alpaca allows comma-separated symbols up to ~100 per call
        chunk_size = 50
        snapshots = {}

        try:
            with httpx.Client(timeout=15.0) as client:
                for i in range(0, len(symbols), chunk_size):
                    chunk = symbols[i:i + chunk_size]
                    params = {
                        "symbols": ",".join(chunk),
                        "feed": self.feed
                    }
                    res = client.get(f"{ALPACA_DATA_URL}/stocks/snapshots", headers=headers, params=params)
                    if res.status_code == 200:
                        data = res.json()
                        snapshots.update(data)
                    else:
                        logger.warning(f"Snapshot chunk failed ({res.status_code}): {res.text}")
            return snapshots
        except Exception as e:
            logger.error(f"Error fetching snapshots: {e}")
            return {}

    def fetch_active_us_equities(self) -> List[str]:
        """
        Fetch active US-listed common stock symbols from Alpaca.
        Falls back to curated liquid US universe if credentials are absent or restricted.
        """
        if not self.is_configured():
            return list(DEFAULT_US_UNIVERSE)

        headers = self._get_headers()
        try:
            with httpx.Client(timeout=15.0) as client:
                # Query paper API assets endpoint for US equity common stocks
                res = client.get(
                    f"{ALPACA_PAPER_URL}/assets",
                    headers=headers,
                    params={"status": "active", "asset_class": "us_equity"}
                )
                if res.status_code == 200:
                    assets = res.json()
                    symbols = [
                        a["symbol"] for a in assets 
                        if a.get("tradable") and a.get("status") == "active" and "/" not in a.get("symbol", "")
                    ]
                    if symbols:
                        logger.info(f"Fetched {len(symbols)} active US equities from Alpaca.")
                        return symbols
        except Exception as e:
            logger.warning(f"Failed to fetch assets list from Alpaca paper API: {e}")

        return list(DEFAULT_US_UNIVERSE)

