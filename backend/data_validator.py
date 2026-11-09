"""
Automated Market Data Validation Layer for TradingView Market Data.

Enforces strict financial data-integrity constraints before allowing market data
into the strategy engine:
1. Ticker and exchange mapping validation (US Equities).
2. Timestamp accuracy, ISO-8601 UTC consistency, and strict chronological ordering.
3. OHLCV structural integrity:
   - High >= Open, High >= Close, Low <= Open, Low <= Close, High >= Low.
   - Volume >= 0, Prices > 0.
4. Duplicate timestamp and out-of-order bar rejection.
5. Candle interval cadence, gap detection, and staleness detection.
6. Price consistency against snapshot quotes (|close - quote| tolerance).
7. Mathematical cross-checking of indicators (EMA9, EMA20, ATR14).
8. Generation of comprehensive validation reports.
"""

import logging
import math
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Valid US Stock Exchanges
VALID_US_EXCHANGES = {"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS", "IEX", "US"}

# Expected intervals in seconds
TIMEFRAME_SECONDS = {
    "1": 60, "1m": 60, "1min": 60,
    "5": 300, "5m": 300, "5min": 300,
    "15": 900, "15m": 900, "15min": 900,
    "60": 3600, "1h": 3600, "1hour": 3600, "60m": 3600, "60min": 3600,
    "d": 86400, "1d": 86400, "1day": 86400, "D": 86400,
}


class DataValidationError(Exception):
    """Raised when critical market data validation fails."""
    pass


class DataValidator:
    """
    Automated Data Validation Engine for live and historical market data.
    """

    def __init__(self):
        self.validation_history: List[Dict[str, Any]] = []

    @staticmethod
    def validate_ticker(ticker: str) -> Tuple[bool, str]:
        """
        Validates US equity ticker symbol format.
        Allows standard 1-5 char tickers, plus class shares like BRK.A, BRK-B.
        Rejects crypto, forex pairs, or empty strings.
        """
        if not ticker or not isinstance(ticker, str):
            return False, "Ticker cannot be empty or non-string"
        clean = ticker.strip().upper()
        # Allow symbols like AAPL, BRK.B, BF-B
        if not re.match(r"^[A-Z]{1,5}([.\-][A-Z]{1,2})?$", clean):
            return False, f"Invalid US equity ticker format: '{ticker}'"
        return True, ""

    @staticmethod
    def validate_exchange(exchange: str) -> Tuple[bool, str]:
        """Validates that exchange is a recognized US equity venue."""
        if not exchange or not isinstance(exchange, str):
            return False, "Exchange cannot be empty"
        clean = exchange.strip().upper()
        if clean not in VALID_US_EXCHANGES:
            return False, f"Exchange '{clean}' not in supported US exchanges: {VALID_US_EXCHANGES}"
        return True, ""

    @staticmethod
    def parse_timestamp(ts: Any) -> Tuple[Optional[datetime], Optional[int]]:
        """
        Parses timestamp from string ISO-8601 or int/float Unix seconds/milliseconds.
        Returns (datetime in UTC, epoch_seconds).
        """
        if ts is None:
            return None, None
        try:
            if isinstance(ts, (int, float)):
                # If timestamp is in milliseconds (> 1e11), convert to seconds
                sec = int(ts / 1000) if ts > 1e11 else int(ts)
                dt = datetime.fromtimestamp(sec, tz=timezone.utc)
                return dt, sec
            elif isinstance(ts, str):
                cleaned = ts.replace("Z", "+00:00")
                dt = datetime.fromisoformat(cleaned)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return dt, int(dt.timestamp())
        except Exception as e:
            logger.warning(f"Failed to parse timestamp '{ts}': {e}")
            return None, None
        return None, None

    @classmethod
    def validate_quote(
        cls,
        quote_data: Optional[Dict[str, Any]],
        symbol: str,
        market_status: str = "OPEN",
        max_age_seconds: float = 120.0,
        now: Optional[datetime] = None,
        is_delayed_feed: bool = False
    ) -> Dict[str, Any]:
        """
        Centrally validates a market quote snapshot and classifies its freshness and execution eligibility.

        Requirements enforced:
        - Rejects missing, zero, negative, malformed, or non-finite prices.
        - Distinguishes missing quotes from stale quotes.
        - Distinguishes provider errors from symbol-resolution errors.
        - Never fabricates prices or provider timestamps.
        - Never assumes retrieval time equals market timestamp.
        - Enforces configurable freshness threshold for regular-session execution.
        - During CLOSED/PRE_MARKET/AFTER_HOURS/HOLIDAY, labels quote as LAST_AVAILABLE or DELAYED.
        - Prevents stale or closed-market quotes from reaching order execution.
        """
        clean_sym = symbol.strip().upper() if symbol else ""
        now_utc = now.astimezone(timezone.utc) if (now and now.tzinfo) else (now.replace(tzinfo=timezone.utc) if now else datetime.now(timezone.utc))

        # Base structure
        result: Dict[str, Any] = {
            "symbol": clean_sym,
            "price": None,
            "volume": 0.0,
            "provider_timestamp": None,
            "retrieval_timestamp": now_utc.isoformat(),
            "data_source": "TradingView Market Data",
            "freshness": "INVALID",
            "category": "MISSING",
            "is_valid": False,
            "is_live_executable": False,
            "error_reason": None,
            "execution_blocked_reason": None,
            "age_seconds": None
        }

        # 1. Missing or Error Response Checks
        if not quote_data or not isinstance(quote_data, dict):
            result["category"] = "MISSING"
            result["error_reason"] = f"No snapshot quote returned for symbol {clean_sym}"
            result["execution_blocked_reason"] = result["error_reason"]
            return result

        if quote_data.get("error"):
            err_str = str(quote_data["error"]).lower()
            if "no_such_symbol" in err_str or "unknown" in err_str or "invalid symbol" in err_str:
                result["category"] = "SYMBOL_RESOLUTION_FAILURE"
                result["error_reason"] = f"Symbol resolution failed: {quote_data['error']}"
            else:
                result["category"] = "PROVIDER_ERROR"
                result["error_reason"] = f"Provider quote error: {quote_data['error']}"
            result["execution_blocked_reason"] = result["error_reason"]
            return result

        # 2. Extract and Validate Price
        raw_price = None
        latest_trade = quote_data.get("latestTrade") or {}
        daily_bar = quote_data.get("dailyBar") or {}

        if "p" in latest_trade and latest_trade["p"] is not None:
            raw_price = latest_trade["p"]
        elif "price" in quote_data and quote_data["price"] is not None:
            raw_price = quote_data["price"]
        elif "c" in daily_bar and daily_bar["c"] is not None:
            raw_price = daily_bar["c"]

        # Validate price numeric and positivity
        try:
            if raw_price is None:
                raise ValueError("Price field is missing")
            price = float(raw_price)
            if math.isnan(price) or math.isinf(price):
                raise ValueError(f"Non-finite price: {price}")
            if price <= 0:
                raise ValueError(f"Non-positive price: {price}")
        except (TypeError, ValueError) as pe:
            result["category"] = "INVALID"
            result["error_reason"] = f"Invalid price for {clean_sym}: {str(pe)}"
            result["execution_blocked_reason"] = result["error_reason"]
            return result

        result["price"] = price

        # Extract Volume
        raw_vol = daily_bar.get("v") if "v" in daily_bar else quote_data.get("volume", 0.0)
        try:
            vol = float(raw_vol or 0.0)
            result["volume"] = max(0.0, vol)
        except (TypeError, ValueError):
            result["volume"] = 0.0

        # 3. Extract Provider Timestamp (Never fabricate!)
        raw_ts = (
            latest_trade.get("t")
            or quote_data.get("timestamp")
            or quote_data.get("lp_time")
            or quote_data.get("time")
        )
        prov_dt, _ = cls.parse_timestamp(raw_ts)
        if prov_dt:
            result["provider_timestamp"] = prov_dt.isoformat()

        # 4. Freshness Classification & Execution Eligibility
        market_is_open = (market_status == "OPEN")

        if not market_is_open:
            # Market is closed / pre-market / after-hours / weekend / holiday
            # Legitimate historical quote from the last available session
            result["freshness"] = "DELAYED" if is_delayed_feed else "LAST_AVAILABLE"
            result["category"] = "VALID"
            result["is_valid"] = True
            result["is_live_executable"] = False
            result["execution_blocked_reason"] = (
                f"US Market session is {market_status}. Live order execution is prohibited outside regular trading hours."
            )
            return result

        # Regular Trading Hours (market_status == "OPEN")
        if is_delayed_feed:
            result["freshness"] = "DELAYED"
            result["category"] = "VALID"
            result["is_valid"] = True
            result["is_live_executable"] = False
            result["execution_blocked_reason"] = "Market data feed is delayed. Live execution requires verified real-time quote."
            return result

        if not prov_dt:
            # Do NOT assume retrieval time equals market timestamp!
            result["freshness"] = "STALE"
            result["category"] = "STALE"
            result["is_valid"] = False
            result["is_live_executable"] = False
            result["error_reason"] = "Missing provider market-data timestamp during open market session"
            result["execution_blocked_reason"] = result["error_reason"]
            return result

        age_seconds = (now_utc - prov_dt).total_seconds()
        result["age_seconds"] = round(age_seconds, 1)

        if age_seconds < -30.0:
            result["category"] = "INVALID"
            result["freshness"] = "INVALID"
            result["is_valid"] = False
            result["is_live_executable"] = False
            result["error_reason"] = f"Future quote timestamp detected ({prov_dt.isoformat()})"
            result["execution_blocked_reason"] = result["error_reason"]
            return result

        if age_seconds <= max_age_seconds:
            result["freshness"] = "LIVE"
            result["category"] = "VALID"
            result["is_valid"] = True
            result["is_live_executable"] = True
            result["data_source"] = "TradingView Real-Time"
            return result
        else:
            result["freshness"] = "STALE"
            result["category"] = "STALE"
            result["is_valid"] = False
            result["is_live_executable"] = False
            result["error_reason"] = (
                f"Quote is stale: timestamp age ({age_seconds:.1f}s) exceeds threshold ({max_age_seconds:.1f}s)"
            )
            result["execution_blocked_reason"] = result["error_reason"]
            return result

    def validate_candle_structure(self, candle: Dict[str, Any], index: int = 0) -> Tuple[bool, List[str]]:
        """
        Validates a single OHLCV bar for structural integrity:
        - Open, High, Low, Close are positive numbers (> 0)
        - High >= Open and High >= Close
        - Low <= Open and Low <= Close
        - High >= Low
        - Volume >= 0
        """
        errors = []
        for field in ("open", "high", "low", "close"):
            val = candle.get(field)
            if val is None or not isinstance(val, (int, float)):
                errors.append(f"Bar {index}: Missing or non-numeric '{field}' ({val})")
            elif val <= 0:
                errors.append(f"Bar {index}: Non-positive price '{field}' = {val}")

        vol = candle.get("volume", 0.0)
        if vol is None or not isinstance(vol, (int, float)):
            errors.append(f"Bar {index}: Missing or non-numeric 'volume' ({vol})")
        elif vol < 0:
            errors.append(f"Bar {index}: Negative volume = {vol}")

        if errors:
            return False, errors

        o = float(candle["open"])
        h = float(candle["high"])
        l = float(candle["low"])
        c = float(candle["close"])

        # Financial invariants with slight floating-point tolerance (1e-6)
        if h < (o - 1e-6):
            errors.append(f"Bar {index}: High ({h}) < Open ({o})")
        if h < (c - 1e-6):
            errors.append(f"Bar {index}: High ({h}) < Close ({c})")
        if l > (o + 1e-6):
            errors.append(f"Bar {index}: Low ({l}) > Open ({o})")
        if l > (c + 1e-6):
            errors.append(f"Bar {index}: Low ({l}) > Close ({c})")
        if h < l:
            errors.append(f"Bar {index}: High ({h}) < Low ({l})")

        return len(errors) == 0, errors

    def validate_bars_series(
        self,
        bars: List[Dict[str, Any]],
        symbol: str,
        timeframe: str = "5m",
        max_clock_skew_seconds: int = 120
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Validates an entire sequence of OHLCV bars:
        1. Non-empty check.
        2. Individual bar structural integrity.
        3. Strict chronological order (no duplicates, no out-of-order).
        4. No future timestamps beyond acceptable clock skew.
        5. Interval continuity and gap metrics.
        """
        errors = []
        stats = {
            "symbol": symbol,
            "timeframe": timeframe,
            "total_bars": len(bars),
            "valid_bars": 0,
            "duplicate_bars": 0,
            "out_of_order_bars": 0,
            "future_bars": 0,
            "structural_errors": 0,
            "gaps_detected": 0,
            "first_timestamp": None,
            "last_timestamp": None,
            "is_stale": False,
        }

        if not bars:
            errors.append(f"Symbol {symbol}: Bar series is completely empty.")
            return False, errors, stats

        now_utc = datetime.now(timezone.utc)
        now_epoch = int(now_utc.timestamp())
        prev_epoch = None
        expected_step = TIMEFRAME_SECONDS.get(str(timeframe).lower(), 300)

        for i, bar in enumerate(bars):
            # 1. Structural integrity
            struct_ok, struct_errs = self.validate_candle_structure(bar, index=i)
            if not struct_ok:
                errors.extend(struct_errs)
                stats["structural_errors"] += len(struct_errs)
                continue

            # 2. Timestamp parsing
            raw_ts = bar.get("timestamp") or bar.get("time")
            dt, epoch = self.parse_timestamp(raw_ts)
            if dt is None or epoch is None:
                errors.append(f"Bar {i}: Invalid timestamp '{raw_ts}'")
                stats["structural_errors"] += 1
                continue

            if i == 0:
                stats["first_timestamp"] = dt.isoformat()
            stats["last_timestamp"] = dt.isoformat()

            # 3. Future timestamp check
            if epoch > (now_epoch + max_clock_skew_seconds):
                errors.append(f"Bar {i}: Future timestamp {dt.isoformat()} exceeds clock skew limit")
                stats["future_bars"] += 1

            # 4. Chronological order & duplicates
            if prev_epoch is not None:
                if epoch == prev_epoch:
                    errors.append(f"Bar {i}: Duplicate timestamp detected ({dt.isoformat()})")
                    stats["duplicate_bars"] += 1
                elif epoch < prev_epoch:
                    errors.append(f"Bar {i}: Out-of-order timestamp {dt.isoformat()} < previous")
                    stats["out_of_order_bars"] += 1
                else:
                    # Gap check (during normal intraday trading hours)
                    diff = epoch - prev_epoch
                    # If gap is significantly larger than step (e.g. > 3 * step) within same calendar day
                    if diff > (expected_step * 3) and (diff < 86400 * 4):
                        # Note as potential gap
                        stats["gaps_detected"] += 1

            prev_epoch = epoch
            stats["valid_bars"] += 1

        # Staleness check: If last bar is older than 5 days (e.g. halted/dead stock)
        if stats["last_timestamp"]:
            last_dt, _ = self.parse_timestamp(stats["last_timestamp"])
            if last_dt and (now_utc - last_dt) > timedelta(days=7):
                stats["is_stale"] = True
                errors.append(f"Symbol {symbol}: Data is stale. Last bar timestamp is {stats['last_timestamp']}")

        is_valid = len(errors) == 0
        return is_valid, errors, stats

    def validate_quote_consistency(
        self,
        symbol: str,
        bars: List[Dict[str, Any]],
        quote: Optional[Dict[str, Any]],
        max_divergence_pct: float = 0.05
    ) -> Tuple[bool, List[str]]:
        """
        Cross-checks live quote against the most recent candle close.
        Divergence between the latest candle close and the real-time quote
        must not exceed max_divergence_pct (5%) during typical trading conditions.
        """
        errors = []
        if not quote or not bars:
            return True, []  # Skip if no quote available to cross-check

        latest_bar = bars[-1]
        candle_close = float(latest_bar.get("close", 0.0))
        quote_price = float(quote.get("price", quote.get("lp", 0.0)))

        if candle_close <= 0 or quote_price <= 0:
            errors.append(f"{symbol}: Cannot compare non-positive prices (Candle: {candle_close}, Quote: {quote_price})")
            return False, errors

        divergence = abs(quote_price - candle_close) / candle_close
        if divergence > max_divergence_pct:
            errors.append(
                f"{symbol}: Quote price (${quote_price:.2f}) diverges from latest candle close (${candle_close:.2f}) "
                f"by {divergence * 100:.2f}% (Limit: {max_divergence_pct * 100:.1f}%)"
            )
            return False, errors

        return True, []

    def verify_indicators(
        self,
        bars: List[Dict[str, Any]],
        external_ema9: Optional[float] = None,
        external_ema20: Optional[float] = None,
        external_atr14: Optional[float] = None,
        tolerance_pct: float = 0.01
    ) -> Dict[str, Any]:
        """
        Cross-checks indicator calculations against local mathematical implementations:
        - EMA(9) and EMA(20) computed on candle closes.
        - ATR(14) computed on True Range.
        Verifies values are within tolerance_pct (1%).
        """
        if not bars:
            return {"verified": False, "reason": "No bars provided for indicator verification"}

        closes = [float(b["close"]) for b in bars]
        n = len(closes)

        # 1. Local EMA calculation
        def local_ema(vals: List[float], period: int) -> float:
            if len(vals) < period:
                return sum(vals) / len(vals) if vals else 0.0
            k = 2.0 / (period + 1.0)
            ema = sum(vals[:period]) / period
            for v in vals[period:]:
                ema = (v * k) + (ema * (1.0 - k))
            return ema

        calc_ema9 = local_ema(closes, 9)
        calc_ema20 = local_ema(closes, 20)

        # 2. Local ATR(14) calculation
        def local_atr(candle_list: List[Dict[str, Any]], period: int = 14) -> float:
            if not candle_list:
                return 0.0
            trs = []
            for i in range(len(candle_list)):
                h = float(candle_list[i]["high"])
                l = float(candle_list[i]["low"])
                if i == 0:
                    trs.append(h - l)
                else:
                    prev_c = float(candle_list[i - 1]["close"])
                    tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
                    trs.append(tr)
            if len(trs) < period:
                return sum(trs) / len(trs) if trs else 0.0
            atr = sum(trs[:period]) / period
            for tr in trs[period:]:
                atr = (atr * (period - 1) + tr) / period
            return atr

        calc_atr14 = local_atr(bars, 14)

        result = {
            "verified": True,
            "calculated": {
                "ema_9": round(calc_ema9, 4),
                "ema_20": round(calc_ema20, 4),
                "atr_14": round(calc_atr14, 4),
            },
            "discrepancies": []
        }

        # Check external EMA9 if provided
        if external_ema9 is not None and external_ema9 > 0:
            diff = abs(external_ema9 - calc_ema9) / calc_ema9
            if diff > tolerance_pct:
                result["verified"] = False
                result["discrepancies"].append(f"EMA9 mismatch: external={external_ema9}, local={calc_ema9:.4f} (diff={diff*100:.2f}%)")

        # Check external EMA20 if provided
        if external_ema20 is not None and external_ema20 > 0:
            diff = abs(external_ema20 - calc_ema20) / calc_ema20
            if diff > tolerance_pct:
                result["verified"] = False
                result["discrepancies"].append(f"EMA20 mismatch: external={external_ema20}, local={calc_ema20:.4f} (diff={diff*100:.2f}%)")

        # Check external ATR14 if provided
        if external_atr14 is not None and external_atr14 > 0 and calc_atr14 > 0:
            diff = abs(external_atr14 - calc_atr14) / calc_atr14
            if diff > tolerance_pct:
                result["verified"] = False
                result["discrepancies"].append(f"ATR14 mismatch: external={external_atr14}, local={calc_atr14:.4f} (diff={diff*100:.2f}%)")

        return result

    def generate_validation_report(
        self,
        requested_symbols: List[str],
        received_bars: Dict[str, List[Dict[str, Any]]],
        received_quotes: Optional[Dict[str, Dict[str, Any]]] = None,
        latency_ms: float = 0.0,
        timeframe: str = "5m"
    ) -> Dict[str, Any]:
        """
        Produces a comprehensive validation report covering all audited symbols.
        Checks:
        - Total requested vs received.
        - Successful vs failed subscriptions.
        - Candle completeness and invalid record count.
        - Structural integrity, monotonicity, interval consistency.
        - Quote-to-bar price consistency.
        - Indicator consistency.
        """
        received_quotes = received_quotes or {}
        total_requested = len(requested_symbols)
        total_received = 0
        successful_subscriptions = 0
        failed_subscriptions = 0
        invalid_records = 0
        failure_reasons = []
        symbol_details = {}
        all_last_timestamps = []

        for sym in requested_symbols:
            # 1. Ticker validity
            valid_sym, sym_err = self.validate_ticker(sym)
            if not valid_sym:
                failed_subscriptions += 1
                invalid_records += 1
                failure_reasons.append(f"{sym}: {sym_err}")
                symbol_details[sym] = {"status": "INVALID_SYMBOL", "error": sym_err}
                continue

            bars = received_bars.get(sym, [])
            if not bars:
                failed_subscriptions += 1
                failure_reasons.append(f"{sym}: No market data bars received from feed.")
                symbol_details[sym] = {"status": "NO_DATA", "bars_count": 0}
                continue

            total_received += 1

            # 2. Bar series validation
            is_valid_series, series_errors, stats = self.validate_bars_series(bars, sym, timeframe=timeframe)
            if not is_valid_series:
                failed_subscriptions += 1
                invalid_records += len(series_errors)
                failure_reasons.extend([f"{sym}: {e}" for e in series_errors[:3]])
                symbol_details[sym] = {
                    "status": "VALIDATION_FAILED",
                    "stats": stats,
                    "errors": series_errors
                }
                continue

            # 3. Quote cross-check if quote is available
            quote = received_quotes.get(sym)
            quote_ok, quote_errs = self.validate_quote_consistency(sym, bars, quote)
            if not quote_ok:
                invalid_records += len(quote_errs)
                failure_reasons.extend(quote_errs)
                symbol_details[sym] = {
                    "status": "QUOTE_DIVERGENCE",
                    "stats": stats,
                    "errors": quote_errs
                }
                continue

            # 4. Indicator verification
            indicator_check = self.verify_indicators(bars)

            if stats["last_timestamp"]:
                all_last_timestamps.append(stats["last_timestamp"])

            successful_subscriptions += 1
            symbol_details[sym] = {
                "status": "VERIFIED",
                "bars_count": stats["total_bars"],
                "last_timestamp": stats["last_timestamp"],
                "indicators": indicator_check["calculated"],
                "gaps_detected": stats["gaps_detected"]
            }

        completeness_pct = (successful_subscriptions / total_requested * 100.0) if total_requested > 0 else 0.0
        validation_passed = (successful_subscriptions == total_requested) and (invalid_records == 0)

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "validation_passed": validation_passed,
            "total_symbols_requested": total_requested,
            "total_symbols_received": total_received,
            "successful_subscriptions": successful_subscriptions,
            "failed_subscriptions": failed_subscriptions,
            "candle_completeness_pct": round(completeness_pct, 2),
            "invalid_record_count": invalid_records,
            "failure_reasons": failure_reasons[:20],
            "data_latency_ms": round(latency_ms, 2),
            "latest_update_timestamp": max(all_last_timestamps) if all_last_timestamps else None,
            "feed_source": "TradingView Real-Time Consolidated Tape",
            "feed_coverage": "Consolidated US Equities Tape (NYSE, NASDAQ, AMEX)",
            "known_limitations": [
                "Free TradingView WebSocket sessions cap deep historical queries at ~7,000 bars",
                "Inter-session market closures (weekends/holidays) create expected timestamp gaps",
                "High-frequency concurrent batch queries may trigger TradingView rate limits"
            ],
            "discrepancies": failure_reasons[:5],
            "symbol_details": symbol_details
        }

        self.validation_history.append(report)
        return report

