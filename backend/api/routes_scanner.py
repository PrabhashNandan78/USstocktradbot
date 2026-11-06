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
def start_scanner():
    scanner_instance.start()
    return {"status": "RUNNING", "message": "Scanner background loop initiated."}

@router.post("/stop")
def stop_scanner():
    scanner_instance.stop()
    return {"status": "STOPPED", "message": "Scanner background loop paused."}

@router.post("/scan-now")
def run_immediate_scan():
    results = scanner_instance.scan_once()
    return {"status": "COMPLETED", "results": results}
