import pytest
from datetime import datetime, timezone, timedelta
from backend.strategy.pivots import calculate_atr, identify_confirmed_pivots, evaluate_1h_market_structure
from backend.strategy.demand_zone import detect_15m_demand_zones
from backend.strategy.indicators import calculate_ema, calculate_rsi, calculate_macd, calculate_vwap
from backend.strategy.patterns import (
    is_bullish_engulfing, is_hammer, is_bullish_pin_bar, is_morning_star, is_three_white_soldiers
)
from backend.strategy.scoring import score_5m_confirmation
from backend.strategy.engine import StrategyEngine

def make_candle(o, h, l, c, v=1000, idx=0):
    t = (datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc) + timedelta(minutes=idx * 5)).isoformat()
    return {"timestamp": t, "open": float(o), "high": float(h), "low": float(l), "close": float(c), "volume": float(v)}

def test_pivots_and_no_future_leak():
    # Sequence with clear pivot high at index 2 (candles 0, 1, 2, 3, 4)
    # Candle 2 high = 150. Candle 0=120, 1=130, 3=140, 4=135
    candles = [
        make_candle(115, 120, 110, 118, idx=0),
        make_candle(118, 130, 115, 128, idx=1),
        make_candle(128, 150, 125, 145, idx=2), # PIVOT HIGH
        make_candle(145, 140, 130, 135, idx=3),
        make_candle(135, 135, 120, 122, idx=4),
        make_candle(122, 125, 105, 108, idx=5), # PIVOT LOW
        make_candle(108, 115, 110, 112, idx=6),
        make_candle(112, 118, 111, 116, idx=7)
    ]
    swing_highs, swing_lows = identify_confirmed_pivots(candles)
    assert len(swing_highs) >= 1
    assert swing_highs[0]["index"] == 2
    assert swing_highs[0]["price"] == 150.0
    assert swing_highs[0]["confirmed_at_index"] == 4  # Confirmed only after index 4 completes

    assert len(swing_lows) >= 1
    assert swing_lows[0]["index"] == 5
    assert swing_lows[0]["price"] == 105.0
    assert swing_lows[0]["confirmed_at_index"] == 7

def test_1h_market_structure_bos():
    # Build 1H candles with pivot high at 150, pivot low at 100, then BOS candle closing at 155
    candles = [
        make_candle(105, 110, 100, 105, idx=0), # low 100
        make_candle(105, 115, 103, 112, idx=1),
        make_candle(112, 120, 110, 118, idx=2),
        make_candle(118, 130, 115, 125, idx=3),
        make_candle(125, 150, 120, 145, idx=4), # Pivot High 150
        make_candle(145, 140, 135, 138, idx=5),
        make_candle(138, 135, 125, 128, idx=6),
        make_candle(128, 128, 100, 102, idx=7), # Pivot Low 100
        make_candle(102, 115, 105, 112, idx=8),
        make_candle(112, 125, 110, 122, idx=9),
        make_candle(122, 140, 120, 138, idx=10),
        make_candle(138, 160, 135, 155, idx=11) # BOS Breakout close 155 > 150 + 0.1 * ATR
    ]
    res = evaluate_1h_market_structure(candles)
    assert res["valid_bos"] is True
    assert res["swing_high"] == 150.0
    assert res["swing_low"] == 100.0
    assert res["eq"] == 125.0

def test_15m_displacement_and_demand_zone():
    candles = []
    # 10 preceding normal candles (median body ~ 2.0)
    for i in range(10):
        candles.append(make_candle(100 + i, 103 + i, 99 + i, 102 + i, idx=i))
    
    # Candle 10: Bearish candle before displacement (Open 115, High 116, Low 112, Close 113)
    candles.append(make_candle(115, 116, 112, 113, idx=10))
    
    # Candle 11: Strong Bullish Displacement (Body = 125 - 113 = 12 > 1.5 * 2.0, closes above previous 5 highs)
    candles.append(make_candle(113, 126, 113, 125, idx=11))
    
    # Candle 12: Price returns into demand zone (Zone High=115, Zone Low=112)
    candles.append(make_candle(124, 124, 114, 118, idx=12))

    res = detect_15m_demand_zones(candles)
    assert res["valid_zone"] is True
    assert res["zone"]["zone_high"] == 115.0
    assert res["zone"]["zone_low"] == 112.0
    assert res["zone"]["has_returned"] is True
    assert res["zone"]["is_invalidated"] is False

def test_candlestick_patterns():
    # Test Bullish Engulfing
    engulf_c1 = make_candle(100, 101, 95, 96) # Bearish
    engulf_c2 = make_candle(95, 103, 94, 102) # Bullish engulfing
    assert is_bullish_engulfing([engulf_c1, engulf_c2]) is True

    # Test Hammer
    hammer = make_candle(100, 101, 88, 100.5) # Lower wick = 12, body = 0.5, upper wick = 0.5
    assert is_hammer([hammer]) is True

    # Test Pin Bar
    pinbar = make_candle(100, 101, 80, 100) # Lower wick = 20, total range = 21 (95%)
    assert is_bullish_pin_bar([pinbar]) is True

def test_scoring_matrix_and_caps():
    candles = [make_candle(100 + (i*0.2), 101 + (i*0.2), 99 + (i*0.2), 100.5 + (i*0.2), v=1000, idx=i) for i in range(35)]
    # Make confirmation candle bullish with engulfing & volume expansion
    candles[-2] = make_candle(110, 111, 105, 106, v=1000, idx=33) # Bearish
    candles[-1] = make_candle(105, 115, 104, 114, v=5000, idx=34) # Strong bullish engulfing + volume

    demand_zone = {"zone_high": 108.0, "zone_low": 104.0}
    res = score_5m_confirmation(candles, demand_zone)
    assert res["confirmation_candle"]["close"] > res["confirmation_candle"]["open"]
    # Candlestick score capped at 25
    assert res["category_scores"]["candlestick"] <= 25.0
    # Momentum capped at 20
    assert res["category_scores"]["momentum"] <= 20.0
    # Trend capped at 20
    assert res["category_scores"]["trend"] <= 20.0
    # Volume capped at 15
    assert res["category_scores"]["volume"] <= 15.0
    # Price action capped at 20
    assert res["category_scores"]["price_action"] <= 20.0
    assert res["total_score"] >= 60.0

def test_full_strategy_engine_execution():
    engine = StrategyEngine(min_score=60.0, min_rr=2.0)
    
    # 1H candles with confirmed swing high at 150, swing low at 100, BOS at 155
    candles_1h = [
        make_candle(105, 110, 100, 105, idx=0),
        make_candle(105, 115, 103, 112, idx=1),
        make_candle(112, 120, 110, 118, idx=2),
        make_candle(118, 130, 115, 125, idx=3),
        make_candle(125, 150, 120, 145, idx=4), # Swing High 150
        make_candle(145, 140, 135, 138, idx=5),
        make_candle(138, 135, 125, 128, idx=6),
        make_candle(128, 128, 100, 102, idx=7), # Swing Low 100
        make_candle(102, 115, 105, 112, idx=8),
        make_candle(112, 125, 110, 122, idx=9),
        make_candle(122, 140, 120, 138, idx=10),
        make_candle(138, 160, 135, 155, idx=11) # BOS
    ]

    # 15M candles with displacement and demand zone (Zone High 115, Zone Low 112)
    candles_15m = [make_candle(100, 103, 99, 102, idx=i) for i in range(10)]
    candles_15m.append(make_candle(115, 116, 112, 113, idx=10)) # Bearish
    candles_15m.append(make_candle(113, 126, 113, 125, idx=11)) # Displacement
    candles_15m.append(make_candle(124, 124, 114, 118, idx=12)) # Return to zone

    # 5M candles with bullish confirmation at 116
    candles_5m = [make_candle(110 + (i*0.1), 111 + (i*0.1), 109 + (i*0.1), 110.5 + (i*0.1), idx=i) for i in range(35)]
    candles_5m[-2] = make_candle(116, 117, 112, 113, idx=33) # Bearish
    candles_5m[-1] = make_candle(113, 120, 112.5, 118, v=6000, idx=34) # Bullish rejection from zone

    res = engine.analyze_symbol("AAPL", candles_1h, candles_15m, candles_5m, configured_qty=1.0)
    assert res["status"] == "QUALIFIED"
    assert res["signal"] is not None
    sig = res["signal"]
    assert sig["symbol"] == "AAPL"
    assert sig["direction"] == "BUY"
    assert sig["entry_price"] == 118.0
    assert sig["stop_loss"] < 112.0 # Zone low - 0.2*ATR
    assert sig["take_profit"] == 150.0 # 1H swing high
    assert sig["risk_reward"] >= 2.0
