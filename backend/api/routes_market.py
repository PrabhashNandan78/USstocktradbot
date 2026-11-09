"""
Market Status & Trading Hours API Routes.
Exposes real-time US exchange session status, official trading calendar awareness,
and market data diagnostics.
"""

from fastapi import APIRouter
from typing import Dict, Any

from backend.market_calendar import NYSECalendar
from backend.tradingview_client import TradingViewClient

router = APIRouter(prefix="/api/market", tags=["Market Status"])


@router.get("/status")
def get_market_status() -> Dict[str, Any]:
    """
    Returns the authoritative US equities market status calculated in the
    America/New_York timezone using the NYSE exchange calendar.
    """
    return NYSECalendar.get_market_status()


@router.get("/diagnostics")
def get_market_diagnostics() -> Dict[str, Any]:
    """
    Returns unified market data health and diagnostic telemetry:
    - TradingView bridge connection health
    - Current market session & NY time
    - Quote and candle endpoint accessibility
    - Freshness configurations and thresholds
    """
    status = NYSECalendar.get_market_status()
    client = TradingViewClient()
    diagnostics = client.get_diagnostics()

    return {
        "market_status": status,
        "market_data_diagnostics": diagnostics
    }

