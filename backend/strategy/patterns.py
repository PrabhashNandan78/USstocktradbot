from typing import List, Dict, Any

def is_bullish_engulfing(candles: List[Dict[str, Any]], idx: int = -1) -> bool:
    """
    Bullish Engulfing Pattern:
    1. Previous candle is bearish (close < open).
    2. Current candle is bullish (close > open).
    3. Current candle body engulfs previous candle body.
    """
    if len(candles) < 2:
        return False
    curr = candles[idx]
    prev = candles[idx - 1]

    prev_body = prev["open"] - prev["close"]
    curr_body = curr["close"] - curr["open"]

    if prev_body <= 0 or curr_body <= 0:
        return False

    # Current body must engulf previous body
    engulfs_open = curr["close"] >= prev["open"]
    engulfs_close = curr["open"] <= prev["close"] or (curr["open"] <= prev["close"] + (prev_body * 0.05))
    
    return engulfs_open and engulfs_close and (curr_body >= prev_body)

def is_hammer(candles: List[Dict[str, Any]], idx: int = -1) -> bool:
    """
    Hammer Pattern:
    - Lower shadow >= 2 * body
    - Upper shadow <= 0.25 * body
    - Close is in upper third of total range
    """
    curr = candles[idx]
    total_range = curr["high"] - curr["low"]
    if total_range <= 0:
        return False

    body = abs(curr["close"] - curr["open"])
    upper_wick = curr["high"] - max(curr["open"], curr["close"])
    lower_wick = min(curr["open"], curr["close"]) - curr["low"]

    if body == 0:
        body = total_range * 0.05  # Handle doji hammer edge case

    lower_shadow_cond = lower_wick >= (2.0 * body)
    upper_shadow_cond = upper_wick <= (0.25 * body) or upper_wick <= (0.1 * total_range)
    upper_third_cond = curr["close"] >= (curr["low"] + (0.66 * total_range))

    return lower_shadow_cond and upper_shadow_cond and upper_third_cond

def is_bullish_pin_bar(candles: List[Dict[str, Any]], idx: int = -1) -> bool:
    """
    Bullish Pin Bar:
    - Long lower wick >= 60% of total candle range
    - Candle body in upper 30% of total range
    - Upper wick <= 20% of total range
    """
    curr = candles[idx]
    total_range = curr["high"] - curr["low"]
    if total_range <= 0:
        return False

    upper_wick = curr["high"] - max(curr["open"], curr["close"])
    lower_wick = min(curr["open"], curr["close"]) - curr["low"]

    long_lower_wick = (lower_wick / total_range) >= 0.60
    small_upper_wick = (upper_wick / total_range) <= 0.20
    body_in_upper_tier = min(curr["open"], curr["close"]) >= (curr["low"] + 0.60 * total_range)

    return long_lower_wick and small_upper_wick and body_in_upper_tier

def is_morning_star(candles: List[Dict[str, Any]], idx: int = -1) -> bool:
    """
    Morning Star: 3-candle reversal pattern
    - Candle 1: Significant bearish candle
    - Candle 2: Small body candle (star) gapping or dipping below candle 1
    - Candle 3: Strong bullish candle closing above the 50% midpoint of Candle 1 body
    """
    if len(candles) < 3:
        return False
    c1 = candles[idx - 2]
    c2 = candles[idx - 1]
    c3 = candles[idx]

    c1_range = c1["high"] - c1["low"]
    c1_body = c1["open"] - c1["close"]
    if c1_body <= 0 or c1_range <= 0 or (c1_body / c1_range) < 0.4:
        return False

    c2_body = abs(c2["close"] - c2["open"])
    if c2_body > (0.4 * c1_body):
        return False

    c3_body = c3["close"] - c3["open"]
    if c3_body <= 0:
        return False

    # Candle 3 closes above the midpoint of Candle 1 body
    c1_midpoint = c1["close"] + (0.5 * c1_body)
    closes_above_midpoint = c3["close"] >= c1_midpoint

    return closes_above_midpoint

def is_three_white_soldiers(candles: List[Dict[str, Any]], idx: int = -1) -> bool:
    """
    Three White Soldiers:
    - 3 consecutive bullish candles
    - Progressively higher closes
    - Opens within previous candle's body
    - Moderate/small upper shadows
    """
    if len(candles) < 3:
        return False
    c1 = candles[idx - 2]
    c2 = candles[idx - 1]
    c3 = candles[idx]

    # All three must be bullish
    if not (c1["close"] > c1["open"] and c2["close"] > c2["open"] and c3["close"] > c3["open"]):
        return False

    # Progressively higher closes
    if not (c3["close"] > c2["close"] > c1["close"]):
        return False

    # Opens within previous candle's body
    if not (c2["open"] >= c1["open"] and c3["open"] >= c2["open"]):
        return False

    # Small upper shadows on latest candle (upper wick <= 0.3 * body)
    c3_body = c3["close"] - c3["open"]
    c3_upper_wick = c3["high"] - c3["close"]
    if c3_upper_wick > (0.35 * c3_body):
        return False

    return True

def detect_candlestick_patterns(candles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Scans the latest completed candles for any bullish candlestick patterns.
    Returns detected pattern name, boolean status, and details.
    """
    if len(candles) < 3:
        return {"detected": False, "patterns": []}

    patterns = []
    if is_bullish_engulfing(candles):
        patterns.append("Bullish Engulfing")
    if is_hammer(candles):
        patterns.append("Hammer")
    if is_bullish_pin_bar(candles):
        patterns.append("Bullish Pin Bar")
    if is_morning_star(candles):
        patterns.append("Morning Star")
    if is_three_white_soldiers(candles):
        patterns.append("Three White Soldiers")

    return {
        "detected": len(patterns) > 0,
        "patterns": patterns,
        "primary_pattern": patterns[0] if patterns else None
    }
