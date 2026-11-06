import statistics
from typing import List, Dict, Any, Optional

def detect_15m_demand_zones(candles_15m: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Detects 15M Demand Zones based on Bullish Displacement:
    1. Displacement candle must:
       - Be bullish (close > open)
       - Have a body >= 1.5 * median body size of the preceding 10 candles
       - Close above the previous 5-candle high
    2. Demand zone:
       - Last bearish candle (close < open) before displacement within the preceding 5 completed candles
       - Zone High = bearish candle open
       - Zone Low = bearish candle low
    3. Return & Invalidation:
       - Validates price return into demand zone (low <= zone_high)
       - Invalidates setup if any subsequent completed 15M candle closes below zone_low
    """
    if len(candles_15m) < 12:
        return {
            "valid_zone": False,
            "reason": "Insufficient 15M candles for displacement evaluation (need at least 12)",
            "zone": None,
            "displacements": []
        }

    valid_zones = []

    # Iterate through candles starting from index 10 to allow 10 preceding candles for median
    for i in range(10, len(candles_15m)):
        c = candles_15m[i]
        
        # Condition 1: Must be bullish
        body = c["close"] - c["open"]
        if body <= 0:
            continue

        # Preceding 10 candle bodies
        preceding_10 = candles_15m[i - 10:i]
        preceding_bodies = [abs(p["close"] - p["open"]) for p in preceding_10]
        median_body = statistics.median(preceding_bodies) if preceding_bodies else 0.0

        if median_body > 0 and body < (1.5 * median_body):
            continue

        # Condition 2: Close above previous 5-candle high
        preceding_5 = candles_15m[max(0, i - 5):i]
        if not preceding_5:
            continue
        prev_5_high = max(p["high"] for p in preceding_5)
        if c["close"] <= prev_5_high:
            continue

        # Condition 3: Find last bearish candle before displacement within preceding 5 completed candles
        bearish_candle = None
        bearish_idx = None
        for k in range(i - 1, max(-1, i - 6), -1):
            cand = candles_15m[k]
            if cand["close"] < cand["open"]:
                bearish_candle = cand
                bearish_idx = k
                break

        if not bearish_candle:
            continue

        zone_high = max(bearish_candle["open"], bearish_candle["close"])
        zone_low = bearish_candle["low"]

        # Now evaluate subsequent candles from i+1 to the end
        subsequent_candles = candles_15m[i + 1:]
        is_invalidated = False
        has_returned = False
        return_index = None

        for sub_idx, sub_c in enumerate(subsequent_candles):
            # Invalidation: candle closes below zone_low
            if sub_c["close"] < zone_low:
                is_invalidated = True
                break
            # Return: candle price enters zone (low <= zone_high and high >= zone_low)
            if sub_c["low"] <= zone_high and sub_c["high"] >= zone_low:
                has_returned = True
                return_index = i + 1 + sub_idx

        zone_data = {
            "displacement_index": i,
            "displacement_candle": c,
            "bearish_candle": bearish_candle,
            "zone_high": zone_high,
            "zone_low": zone_low,
            "zone_width": zone_high - zone_low,
            "is_invalidated": is_invalidated,
            "has_returned": has_returned,
            "return_index": return_index,
            "displacement_time": c["timestamp"],
            "median_10_body": median_body,
            "body_multiplier": (body / median_body) if median_body > 0 else 1.0
        }

        valid_zones.append(zone_data)

    if not valid_zones:
        return {
            "valid_zone": False,
            "reason": "No valid 15M displacement demand zone identified",
            "zone": None,
            "all_zones": []
        }

    # Find the most recent non-invalidated zone that has returned to the demand zone
    active_zones = [z for z in valid_zones if not z["is_invalidated"] and z["has_returned"]]
    
    # If no active returned zone, check if there's an active zone waiting for return
    if not active_zones:
        unreturned_zones = [z for z in valid_zones if not z["is_invalidated"]]
        if unreturned_zones:
            latest_unreturned = unreturned_zones[-1]
            return {
                "valid_zone": False,
                "reason": "Demand zone formed, but price has not yet returned to the zone",
                "zone": latest_unreturned,
                "all_zones": valid_zones
            }
        else:
            return {
                "valid_zone": False,
                "reason": "All detected demand zones were invalidated (closed below zone low)",
                "zone": None,
                "all_zones": valid_zones
            }

    latest_active = active_zones[-1]
    return {
        "valid_zone": True,
        "reason": "Active 15M Demand Zone detected with price return",
        "zone": latest_active,
        "all_zones": valid_zones
    }
