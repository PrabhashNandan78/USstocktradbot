import math
from typing import List, Dict, Any, Optional, Tuple

def calculate_atr(candles: List[Dict[str, Any]], period: int = 14) -> List[float]:
    """
    Calculates Wilder's ATR(14) for a series of OHLCV candles.
    Returns a list of ATR values corresponding to each candle index.
    """
    if len(candles) < 2:
        return [0.0] * len(candles)

    tr_list = [candles[0]["high"] - candles[0]["low"]]
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        pc = candles[i - 1]["close"]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        tr_list.append(tr)

    atr_values = [0.0] * len(candles)
    if len(candles) < period:
        # Simple rolling average if fewer candles than period
        curr_sum = 0.0
        for i, tr in enumerate(tr_list):
            curr_sum += tr
            atr_values[i] = curr_sum / (i + 1)
        return atr_values

    # Initial SMA for ATR
    first_atr = sum(tr_list[:period]) / period
    atr_values[period - 1] = first_atr

    # Wilder's smoothing
    prev_atr = first_atr
    for i in range(period, len(candles)):
        curr_atr = (prev_atr * (period - 1) + tr_list[i]) / period
        atr_values[i] = curr_atr
        prev_atr = curr_atr

    # Backfill earlier values
    for i in range(period - 1):
        atr_values[i] = first_atr

    return atr_values

def identify_confirmed_pivots(candles: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Identifies confirmed 5-candle pivot highs and pivot lows:
    2 candles to the left, 2 candles to the right.
    Pivot at index i is confirmed when candle i+2 completes.
    Never uses future candle information.
    
    Returns:
    (confirmed_swing_highs, confirmed_swing_lows)
    Each entry is a dict: {'index': i, 'price': float, 'candle': dict, 'confirmed_at_index': i+2}
    """
    swing_highs = []
    swing_lows = []
    n = len(candles)

    if n < 5:
        return swing_highs, swing_lows

    # An index i can be a pivot if:
    # 2 <= i <= n - 3 (meaning i-2, i-1, i, i+1, i+2 are completed candles)
    for i in range(2, n - 2):
        curr_high = candles[i]["high"]
        curr_low = candles[i]["low"]

        # Check pivot high: higher than 2 left and 2 right
        is_pivot_high = (
            curr_high > candles[i - 1]["high"] and
            curr_high > candles[i - 2]["high"] and
            curr_high > candles[i + 1]["high"] and
            curr_high > candles[i + 2]["high"]
        )
        if is_pivot_high:
            swing_highs.append({
                "index": i,
                "price": curr_high,
                "timestamp": candles[i]["timestamp"],
                "candle": candles[i],
                "confirmed_at_index": i + 2
            })

        # Check pivot low: lower than 2 left and 2 right
        is_pivot_low = (
            curr_low < candles[i - 1]["low"] and
            curr_low < candles[i - 2]["low"] and
            curr_low < candles[i + 1]["low"] and
            curr_low < candles[i + 2]["low"]
        )
        if is_pivot_low:
            swing_lows.append({
                "index": i,
                "price": curr_low,
                "timestamp": candles[i]["timestamp"],
                "candle": candles[i],
                "confirmed_at_index": i + 2
            })

    return swing_highs, swing_lows

def evaluate_1h_market_structure(candles_1h: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Evaluates 1H Market Structure for Bullish BOS:
    - Identifies confirmed swing highs & lows (5-candle pivot: 2 left, 2 right).
    - Checks if latest completed 1H candle closed above latest confirmed swing high
      by at least 0.1 * ATR(14).
    - Calculates Equilibrium (EQ) = (Swing High + Swing Low) / 2.
    - Determines if market is in discount or premium.
    """
    if len(candles_1h) < 10:
        return {
            "valid_bos": False,
            "reason": "Insufficient 1H candles (need at least 10)",
            "swing_high": None,
            "swing_low": None,
            "eq": None,
            "atr": 0.0,
            "breakout_candle": None
        }

    atr_series = calculate_atr(candles_1h, period=14)
    swing_highs, swing_lows = identify_confirmed_pivots(candles_1h)

    if not swing_highs or not swing_lows:
        return {
            "valid_bos": False,
            "reason": "No confirmed swing highs or lows detected on 1H",
            "swing_high": None,
            "swing_low": None,
            "eq": None,
            "atr": atr_series[-1] if atr_series else 0.0,
            "breakout_candle": None
        }

    # Latest confirmed swing high and swing low
    latest_swing_high = swing_highs[-1]
    latest_swing_low = swing_lows[-1]

    # Calculate Equilibrium (EQ)
    sh_price = latest_swing_high["price"]
    sl_price = latest_swing_low["price"]
    eq = (sh_price + sl_price) / 2.0

    # The breakout candidate is evaluated on candles that formed AFTER the swing high was confirmed
    # Confirmation of swing high at idx happened at idx+2.
    confirmed_idx = latest_swing_high["confirmed_at_index"]
    latest_candle = candles_1h[-1]
    latest_atr = atr_series[-1]
    required_breakout = sh_price + (0.1 * latest_atr)

    # Check if a completed candle after confirmation broke structure
    valid_bos = False
    bos_candle = None

    for idx in range(confirmed_idx, len(candles_1h)):
        c = candles_1h[idx]
        if c["close"] >= required_breakout:
            valid_bos = True
            bos_candle = c
            break

    # Also verify if the current market is still holding above the swing low (trend integrity)
    if valid_bos and latest_candle["close"] < sl_price:
        valid_bos = False
        return {
            "valid_bos": False,
            "reason": "Market broke below 1H swing low after BOS, structure invalidated",
            "swing_high": sh_price,
            "swing_low": sl_price,
            "eq": eq,
            "atr": latest_atr,
            "breakout_candle": None
        }

    return {
        "valid_bos": valid_bos,
        "reason": "Bullish 1H BOS confirmed" if valid_bos else "No 1H candle closed above swing high + 0.1 ATR",
        "swing_high": sh_price,
        "swing_low": sl_price,
        "eq": eq,
        "atr": latest_atr,
        "required_breakout": required_breakout,
        "breakout_candle": bos_candle,
        "is_discount_zone": latest_candle["close"] <= eq,
        "latest_swing_high_info": latest_swing_high,
        "latest_swing_low_info": latest_swing_low
    }

