import math
from typing import List, Dict, Any, Tuple

def calculate_ema(values: List[float], period: int) -> List[float]:
    """
    Calculates Exponential Moving Average (EMA) for a sequence of numbers.
    Multiplier = 2 / (period + 1)
    """
    if not values:
        return []
    if len(values) < period:
        # Return simple rolling averages
        out = []
        running_sum = 0.0
        for i, v in enumerate(values):
            running_sum += v
            out.append(running_sum / (i + 1))
        return out

    out = [0.0] * len(values)
    k = 2.0 / (period + 1.0)
    
    # Initialize with SMA
    sma = sum(values[:period]) / period
    out[period - 1] = sma
    
    # Fill earlier values with SMA for continuity
    for i in range(period - 1):
        out[i] = sum(values[:i + 1]) / (i + 1)

    prev_ema = sma
    for i in range(period, len(values)):
        curr_ema = (values[i] * k) + (prev_ema * (1.0 - k))
        out[i] = curr_ema
        prev_ema = curr_ema

    return out

def calculate_rsi(candles: List[Dict[str, Any]], period: int = 14) -> List[float]:
    """
    Calculates RSI(14) using Wilder's smoothed moving average of gains/losses.
    """
    n = len(candles)
    if n < 2:
        return [50.0] * n

    gains = [0.0] * n
    losses = [0.0] * n

    for i in range(1, n):
        change = candles[i]["close"] - candles[i - 1]["close"]
        if change > 0:
            gains[i] = change
        else:
            losses[i] = abs(change)

    rsi = [50.0] * n
    if n <= period:
        return rsi

    # First average gain and loss
    avg_gain = sum(gains[1:period + 1]) / period
    avg_loss = sum(losses[1:period + 1]) / period

    if avg_loss == 0:
        rsi[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi[period] = 100.0 - (100.0 / (1.0 + rs))

    # Wilder's smoothing
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))

    # Backfill earlier values
    for i in range(period):
        rsi[i] = rsi[period]

    return rsi

def calculate_macd(candles: List[Dict[str, Any]], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, List[float]]:
    """
    Calculates MACD Line, Signal Line, and MACD Histogram.
    """
    closes = [c["close"] for c in candles]
    ema_fast = calculate_ema(closes, fast)
    ema_slow = calculate_ema(closes, slow)

    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = calculate_ema(macd_line, signal)
    histogram = [m - s for m, s in zip(macd_line, signal_line)]

    return {
        "macd": macd_line,
        "signal": signal_line,
        "hist": histogram
    }

def calculate_vwap(candles: List[Dict[str, Any]]) -> List[float]:
    """
    Calculates Volume Weighted Average Price (VWAP) across the candle sequence.
    Typical Price = (High + Low + Close) / 3
    VWAP = Cumulative(Typical Price * Volume) / Cumulative(Volume)
    """
    vwap_values = []
    cum_pv = 0.0
    cum_vol = 0.0

    for c in candles:
        typical_price = (c["high"] + c["low"] + c["close"]) / 3.0
        vol = max(1.0, c.get("volume", 1.0))
        cum_pv += typical_price * vol
        cum_vol += vol
        vwap_values.append(cum_pv / cum_vol)

    return vwap_values

def calculate_volume_metrics(candles: List[Dict[str, Any]], period: int = 20) -> Tuple[List[float], List[bool]]:
    """
    Calculates:
    - 20-candle average volume
    - Whether current candle has volume expansion (> 1.5 * 20-candle average)
    """
    volumes = [max(0.0, c.get("volume", 0.0)) for c in candles]
    avg_volumes = []
    expansion_flags = []

    for i in range(len(candles)):
        start_idx = max(0, i - period)
        window = volumes[start_idx:i] if i > 0 else [volumes[0]]
        avg_vol = (sum(window) / len(window)) if window else volumes[i]
        avg_volumes.append(avg_vol)
        
        is_expansion = (volumes[i] > (1.5 * avg_vol)) if avg_vol > 0 else False
        expansion_flags.append(is_expansion)

    return avg_volumes, expansion_flags
