from typing import List, Dict, Any, Tuple
from backend.strategy.indicators import (
    calculate_ema, calculate_rsi, calculate_macd, calculate_vwap, calculate_volume_metrics
)
from backend.strategy.patterns import detect_candlestick_patterns

def score_5m_confirmation(
    candles_5m: List[Dict[str, Any]], 
    demand_zone: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Evaluates 5M candles for Bullish Entry Confirmation and calculates
    deterministic signal score across 5 categories (Total 100).
    
    Category Weights:
    - Candlestick:  25
    - Momentum:     20
    - Trend:        20
    - Volume:       15
    - Price Action: 20
    
    Mandatory Rules:
    - Score >= 60
    - At least one bullish candlestick OR price-action confirmation
    - 5M confirmation candle MUST close bullish (close > open)
    """
    if len(candles_5m) < 30:
        return {
            "is_valid": False,
            "total_score": 0,
            "reasons": ["Insufficient 5M candles (need at least 30)"],
            "breakdown": {}
        }

    curr = candles_5m[-1]
    prev = candles_5m[-2]

    # Rule Check: Confirmation candle MUST close bullish
    is_bullish_close = curr["close"] > curr["open"]
    if not is_bullish_close:
        return {
            "is_valid": False,
            "total_score": 0,
            "reasons": ["5M confirmation candle did not close bullish (close <= open)"],
            "breakdown": {}
        }

    reasons = []
    category_scores = {
        "candlestick": 0.0,
        "momentum": 0.0,
        "trend": 0.0,
        "volume": 0.0,
        "price_action": 0.0
    }
    signals_detected = []

    # 1. Candlestick Category (Max 25)
    pattern_res = detect_candlestick_patterns(candles_5m)
    if pattern_res["detected"]:
        category_scores["candlestick"] = 25.0
        for p in pattern_res["patterns"]:
            signals_detected.append(f"Candlestick: {p}")

    # 2. Momentum Category (Max 20)
    rsi_series = calculate_rsi(candles_5m, period=14)
    macd_res = calculate_macd(candles_5m, fast=12, slow=26, signal=9)
    
    mom_score = 0.0
    # RSI crossing above 50 or holding above 50
    curr_rsi = rsi_series[-1]
    prev_rsi = rsi_series[-2]
    if prev_rsi <= 50.0 and curr_rsi > 50.0:
        mom_score += 10.0
        signals_detected.append(f"Momentum: RSI crossed above 50 ({curr_rsi:.1f})")
    elif curr_rsi > 50.0:
        mom_score += 5.0
        signals_detected.append(f"Momentum: RSI above 50 ({curr_rsi:.1f})")

    # MACD Bullish Crossover
    curr_macd = macd_res["macd"][-1]
    curr_sig = macd_res["signal"][-1]
    prev_macd = macd_res["macd"][-2]
    prev_sig = macd_res["signal"][-2]
    
    if prev_macd <= prev_sig and curr_macd > curr_sig:
        mom_score += 10.0
        signals_detected.append("Momentum: MACD bullish crossover")
    elif curr_macd > curr_sig:
        mom_score += 5.0
        signals_detected.append("Momentum: MACD line above Signal")

    # Increasing MACD Histogram
    curr_hist = macd_res["hist"][-1]
    prev_hist = macd_res["hist"][-2]
    if curr_hist > prev_hist and curr_hist > 0:
        mom_score += 5.0
        signals_detected.append("Momentum: Increasing positive MACD histogram")

    category_scores["momentum"] = min(20.0, mom_score)

    # 3. Trend Category (Max 20)
    closes = [c["close"] for c in candles_5m]
    ema9_series = calculate_ema(closes, 9)
    ema21_series = calculate_ema(closes, 21)
    vwap_series = calculate_vwap(candles_5m)

    trend_score = 0.0
    curr_ema9 = ema9_series[-1]
    curr_ema21 = ema21_series[-1]
    prev_ema9 = ema9_series[-2]
    curr_vwap = vwap_series[-1]

    # EMA 9 above EMA 21
    if curr_ema9 > curr_ema21:
        trend_score += 10.0
        signals_detected.append("Trend: EMA 9 > EMA 21")

    # Price above VWAP
    if curr["close"] > curr_vwap:
        trend_score += 10.0
        signals_detected.append(f"Trend: Price ({curr['close']:.2f}) > VWAP ({curr_vwap:.2f})")

    # Positive EMA slope
    if curr_ema9 > prev_ema9:
        trend_score += 5.0
        signals_detected.append("Trend: Positive EMA 9 slope")

    category_scores["trend"] = min(20.0, trend_score)

    # 4. Volume Category (Max 15)
    avg_volumes, expansion_flags = calculate_volume_metrics(candles_5m, period=20)
    vol_score = 0.0
    curr_vol = curr.get("volume", 0.0)
    prev_vol = prev.get("volume", 0.0)
    avg_vol = avg_volumes[-1]

    if expansion_flags[-1]:
        vol_score += 10.0
        signals_detected.append(f"Volume: Volume expansion > 1.5x 20-MA ({curr_vol:.0f} vs {avg_vol:.0f})")

    if curr_vol > prev_vol and curr["close"] > curr["open"]:
        vol_score += 10.0
        signals_detected.append("Volume: Bullish volume expansion")

    category_scores["volume"] = min(15.0, vol_score)

    # 5. Price Action Category (Max 20)
    pa_score = 0.0
    zone_high = demand_zone.get("zone_high", 0.0)
    zone_low = demand_zone.get("zone_low", 0.0)

    # Higher low: current low > previous low
    if curr["low"] > prev["low"]:
        pa_score += 7.0
        signals_detected.append("Price Action: 5M Higher Low")

    # Bullish demand zone rejection:
    # Candle tested demand zone (low <= zone_high) and closed firmly above it
    if curr["low"] <= zone_high and curr["close"] > zone_high:
        pa_score += 10.0
        signals_detected.append("Price Action: Bullish Demand Zone Rejection")
    elif curr["low"] >= zone_low and curr["close"] > curr["open"]:
        pa_score += 5.0
        signals_detected.append("Price Action: Demand zone support holding")

    # Break of minor swing high on 5M (close > highest high of prior 3 candles)
    prior_3_high = max(c["high"] for c in candles_5m[-4:-1])
    if curr["close"] > prior_3_high:
        pa_score += 10.0
        signals_detected.append(f"Price Action: Break of minor 5M swing high ({prior_3_high:.2f})")

    category_scores["price_action"] = min(20.0, pa_score)

    total_score = sum(category_scores.values())

    # Validation Checks
    has_candlestick_or_pa = (category_scores["candlestick"] > 0) or (category_scores["price_action"] >= 10.0)
    if not has_candlestick_or_pa:
        reasons.append("Missing mandatory bullish candlestick or strong price-action confirmation")

    if total_score < 60.0:
        reasons.append(f"Score {total_score:.1f}/100 is below minimum threshold of 60")

    is_valid = (total_score >= 60.0) and has_candlestick_or_pa and is_bullish_close

    return {
        "is_valid": is_valid,
        "total_score": round(total_score, 1),
        "category_scores": category_scores,
        "signals_detected": signals_detected,
        "reasons": reasons if not is_valid else ["All mandatory confirmation conditions passed"],
        "confirmation_candle": curr
    }

