from fastapi import APIRouter, HTTPException
from typing import Optional, List, Dict, Any
from backend.signals import SignalManager
from backend.execution_bridge import bridge

router = APIRouter(prefix="/api/signals", tags=["Signals"])

@router.get("/")
def list_signals(limit: int = 50):
    return SignalManager.list_signals(limit=limit)

@router.get("/{signal_id}")
def get_signal(signal_id: str):
    sig = SignalManager.get_signal(signal_id)
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    return sig

@router.post("/{signal_id}/dispatch")
async def dispatch_signal(signal_id: str):
    sig = SignalManager.get_signal(signal_id)
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    
    res = await bridge.dispatch_signal_to_extension(sig)
    return res
