import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

from backend.execution_bridge import bridge
from backend.monitor import monitor

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Extension"])

class HeartbeatModel(BaseModel):
    tv_tab_detected: bool = False
    tv_login_detected: bool = False
    paper_trading_connected: bool = False
    paper_trading_account_verified: bool = False
    current_symbol: Optional[str] = None
    broker_name: Optional[str] = None
    account_state: Optional[str] = None
    account_balance: Optional[float] = None
    last_verified_at: Optional[str] = None
    error_message: Optional[str] = None
    indicators: Optional[Dict[str, Any]] = None
    raw_tv_symbol: Optional[str] = None
    exchange: Optional[str] = None
    username: Optional[str] = None

class ExecutionConfirmationModel(BaseModel):
    signal_id: str
    symbol: str
    success: bool
    executed_price: Optional[float] = None
    tv_order_id: Optional[str] = None
    error_message: Optional[str] = None

class PositionSyncModel(BaseModel):
    positions: List[Dict[str, Any]]

class ClosureReportModel(BaseModel):
    symbol: str
    trade_id: Optional[str] = None
    exit_price: float
    exit_reason: str = "MANUAL"
    gross_pnl: float = 0.0
    trading_fees: float = 0.0
    quantity: float = 1.0
    closed_at: Optional[str] = None

@router.websocket("/ws/extension")
async def websocket_extension_endpoint(websocket: WebSocket):
    await bridge.connect_websocket(websocket)
    try:
        while True:
            text = await websocket.receive_text()
            try:
                msg = json.loads(text)
                msg_type = msg.get("type")

                if msg_type == "HEARTBEAT" or msg_type == "STATUS":
                    bridge.update_status_from_extension(msg.get("data", {}))
                
                elif msg_type == "EXECUTION_CONFIRMATION":
                    bridge.handle_execution_confirmation(msg.get("data", {}))

                elif msg_type == "POSITIONS_SYNC":
                    positions = msg.get("data", {}).get("positions", [])
                    monitor.process_tv_positions_sync(positions)

                elif msg_type == "TRADE_CLOSED":
                    monitor.process_trade_closure_report(msg.get("data", {}))

            except json.JSONDecodeError:
                logger.error("Failed to decode message from extension websocket")
    except WebSocketDisconnect:
        bridge.disconnect_websocket(websocket)

@router.get("/api/extension/status")
def get_extension_status():
    return bridge.extension_state

@router.post("/api/extension/heartbeat")
def post_heartbeat(data: HeartbeatModel):
    bridge.update_status_from_extension(data.model_dump())
    return {"received": True, "state": bridge.extension_state}

@router.post("/api/extension/confirm-execution")
def confirm_execution(data: ExecutionConfirmationModel):
    bridge.handle_execution_confirmation(data.model_dump())
    return {"status": "RECORDED"}

@router.post("/api/extension/sync-positions")
def sync_positions(data: PositionSyncModel):
    monitor.process_tv_positions_sync(data.positions)
    return {"status": "SYNCED", "count": len(data.positions)}

@router.post("/api/extension/report-closure")
def report_closure(data: ClosureReportModel):
    monitor.process_trade_closure_report(data.model_dump())
    return {"status": "CLOSED_RECORDED"}
