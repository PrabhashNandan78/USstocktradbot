from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from backend.scanner import StockScanner

router = APIRouter(prefix="/api/scanner", tags=["Scanner"])

# Global scanner instance
scanner_instance = StockScanner()

class ScannerConfigModel(BaseModel):
    min_price: float = 10.0
    min_avg_volume: float = 100000.0
    min_dollar_volume: float = 2000000.0
    max_stocks_to_analyze: int = 20
    scan_interval_seconds: int = 300
    custom_watchlist: List[str] = []
    exclusions: List[str] = ["SQQQ", "TQQQ", "SOXL", "SOXS"]

@router.get("/config")
def get_scanner_config():
    return scanner_instance.get_config()

@router.post("/config")
def update_scanner_config(cfg: ScannerConfigModel):
    scanner_instance.save_config(cfg.model_dump())
    return {"saved": True, "config": scanner_instance.get_config()}

@router.get("/status")
def get_scanner_status():
    return {
        "is_running": scanner_instance.is_running,
        "results": scanner_instance.latest_scan_results
    }

@router.post("/start")
async def start_scanner():
    """
    Starts the background scan loop using the FastAPI event loop.
    Uses async endpoint so asyncio.create_task() is called from a coroutine.
    """
    result = await scanner_instance.start()
    return result

@router.post("/stop")
async def stop_scanner():
    """
    Cancels and awaits the background scan task cleanly.
    """
    result = await scanner_instance.stop()
    return result

@router.post("/scan-now")
def run_immediate_scan():
    results = scanner_instance.scan_once()
    return {"status": "COMPLETED", "results": results}
