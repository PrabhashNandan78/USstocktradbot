import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from backend.strategy.pivots import evaluate_1h_market_structure, calculate_atr
from backend.strategy.demand_zone import detect_15m_demand_zones
from backend.strategy.scoring import score_5m_confirmation
from backend.database import get_config_val

logger = logging.getLogger(__name__)

class StrategyEngine:
    def __init__(self, min_score: float = 60.0, min_rr: float = 2.0, default_qty: float = 1.0):
        self.min_score = min_score
        self.min_rr = min_rr
        self.default_qty = default_qty

    def analyze_symbol(
        self,
        symbol: str,
        candles_1h: List[Dict[str, Any]],
        candles_15m: List[Dict[str, Any]],
        candles_5m: List[Dict[str, Any]],
        configured_qty: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Executes the full deterministic multi-timeframe strategy:
        1. 1H: Check Bullish BOS & Market Structure.
        2. 15M: Detect qualifying Demand Zone & price return.
        3. 5M: Score bullish entry confirmation (score >= 60, mandatory rules).
        4. SL, TP, RR calculation (RR >= 2.0).
        """
        analysis_result = {
            "symbol": symbol,
            "status": "REJECTED",
            "signal": None,
            "reasons": [],
            "score": 0.0,
            "risk_reward": 0.0,
            "h1_structure": None,
            "m15_zone": None,
            "m5_confirmation": None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # ---------------------------------------------------------
        # Step 1: 1H Market Structure & Bullish BOS
        # ---------------------------------------------------------
        h1_res = evaluate_1h_market_structure(candles_1h)
        analysis_result["h1_structure"] = h1_res

        if not h1_res["valid_bos"]:
            analysis_result["reasons"].append(f"1H Market Structure: {h1_res['reason']}")
            return analysis_result

        # ---------------------------------------------------------
        # Step 2: 15M Demand Zone & Price Return
        # ---------------------------------------------------------
        m15_res = detect_15m_demand_zones(candles_15m)
        analysis_result["m15_zone"] = m15_res

        if not m15_res["valid_zone"]:
            analysis_result["reasons"].append(f"15M Demand Zone: {m15_res['reason']}")
            return analysis_result

        active_zone = m15_res["zone"]

        # ---------------------------------------------------------
        # Step 3: 5M Bullish Entry Confirmation & Scoring
        # ---------------------------------------------------------
        m5_res = score_5m_confirmation(candles_5m, active_zone)
        analysis_result["m5_confirmation"] = m5_res
        analysis_result["score"] = m5_res["total_score"]

        if not m5_res["is_valid"]:
            for r in m5_res["reasons"]:
                analysis_result["reasons"].append(f"5M Confirmation: {r}")
            return analysis_result

        # ---------------------------------------------------------
        # Step 4: Entry, SL, TP, Risk/Reward Calculations
        # ---------------------------------------------------------
        # Entry price: next 5M open / current confirmation close
        entry_price = round(m5_res["confirmation_candle"]["close"], 2)

        # 5M ATR for SL buffer
        atr_5m_series = calculate_atr(candles_5m, period=14)
        atr_5m = atr_5m_series[-1] if atr_5m_series else (entry_price * 0.005)

        # Stop Loss: Demand Zone Low - (0.2 * 5M ATR(14))
        zone_low = active_zone["zone_low"]
        stop_loss = round(zone_low - (0.2 * atr_5m), 2)

        # Take Profit: Latest confirmed 1H swing high above entry
        swing_high_1h = h1_res["swing_high"]
        take_profit = round(swing_high_1h, 2)

        # Sanity Checks
        risk_per_share = entry_price - stop_loss
        reward_per_share = take_profit - entry_price

        if risk_per_share <= 0:
            analysis_result["reasons"].append(f"Invalid Risk: Entry ({entry_price}) <= Stop Loss ({stop_loss})")
            return analysis_result

        if reward_per_share <= 0:
            analysis_result["reasons"].append(f"Invalid Reward: Take Profit ({take_profit}) <= Entry ({entry_price})")
            return analysis_result

        rr = round(reward_per_share / risk_per_share, 2)
        analysis_result["risk_reward"] = rr

        # Reject trades below 2:1 RR
        min_rr_threshold = float(get_config_val("min_rr", self.min_rr))
        if rr < min_rr_threshold:
            analysis_result["reasons"].append(f"Risk/Reward {rr:.2f} is below minimum required {min_rr_threshold:.1f}:1")
            return analysis_result

        # ---------------------------------------------------------
        # Step 5: Generate Signal Object
        # ---------------------------------------------------------
        qty = configured_qty or float(get_config_val("trading_quantity", self.default_qty))
        signal_id = f"SIG-{symbol}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"

        signal_payload = {
            "signal_id": signal_id,
            "symbol": symbol,
            "direction": "BUY",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "quantity": qty,
            "signal_score": m5_res["total_score"],
            "risk_reward": rr,
            "demand_zone_low": round(zone_low, 2),
            "demand_zone_high": round(active_zone["zone_high"], 2),
            "timeframe": "5M",
            "status": "GENERATED",
            "score_breakdown": m5_res["category_scores"],
            "signals_detected": m5_res["signals_detected"],
            "details": {
                "h1_bos_price": h1_res["required_breakout"],
                "h1_swing_high": h1_res["swing_high"],
                "h1_swing_low": h1_res["swing_low"],
                "h1_eq": h1_res["eq"],
                "m15_zone_width": active_zone["zone_width"],
                "atr_5m": round(atr_5m, 4)
            }
        }

        analysis_result["status"] = "QUALIFIED"
        analysis_result["signal"] = signal_payload
        analysis_result["reasons"] = ["All deterministic multi-timeframe conditions passed successfully"]

        return analysis_result
