from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from backend.tradingview_client import TradingViewClient
from backend.telegram_bot import TelegramNotifier
from backend.database import get_config_val, set_config_val

router = APIRouter(prefix="/api/settings", tags=["Settings"])

class TradingViewConfigRequest(BaseModel):
    service_url: str = "http://127.0.0.1:8002"
    session_id: Optional[str] = None

class AlpacaConfigRequest(BaseModel):
    api_key: Optional[str] = ""
    secret_key: Optional[str] = ""
    feed: Optional[str] = "consolidated"

class TelegramConfigRequest(BaseModel):
    bot_token: str
    chat_id: str

class StrategyConfigRequest(BaseModel):
    min_score: float = 60.0
    min_rr: float = 2.0
    trading_quantity: float = 1.0

@router.get("/")
def get_all_settings():
    tv_service_url = get_config_val("tradingview_service_url", "http://127.0.0.1:8002")
    tv_status = get_config_val("tradingview_connection_status", {"status": "NOT_CONFIGURED"})
    
    tg_token = get_config_val("telegram_bot_token", "")
    masked_tg = (tg_token[:4] + "..." + tg_token[-4:]) if len(tg_token) > 8 else ("Set" if tg_token else "")
    
    # Alpaca status preserved for schema backwards-compatibility
    alpaca_key = get_config_val("alpaca_api_key", "")
    masked_key = (alpaca_key[:4] + "..." + alpaca_key[-4:]) if len(alpaca_key) > 8 else ("Set" if alpaca_key else "")
    has_alpaca_secret = bool(get_config_val("alpaca_secret_key", ""))

    return {
        "tradingview": {
            "service_url": tv_service_url,
            "feed": "TradingView Consolidated US Equities Tape",
            "coverage": "NYSE + NASDAQ + AMEX",
            "status": tv_status
        },
        "alpaca": {
            "api_key_masked": masked_key,
            "has_secret": has_alpaca_secret,
            "feed": "TradingView Consolidated",
            "status": tv_status
        },
        "telegram": {
            "bot_token_masked": masked_tg,
            "chat_id": get_config_val("telegram_chat_id", ""),
            "status": get_config_val("telegram_connection_status", {"status": "NOT_CONFIGURED"}),
            "last_notification": get_config_val("telegram_last_notification_time", None)
        },
        "strategy": {
            "min_score": float(get_config_val("min_score", 60.0)),
            "min_rr": float(get_config_val("min_rr", 2.0)),
            "trading_quantity": float(get_config_val("trading_quantity", 1.0))
        }
    }

@router.post("/tradingview/test")
def test_tradingview(cfg: Optional[TradingViewConfigRequest] = None):
    url = cfg.service_url if cfg and cfg.service_url else None
    client = TradingViewClient(service_url=url)
    res = client.test_connection()
    return res

@router.post("/tradingview/save")
def save_tradingview(cfg: TradingViewConfigRequest):
    client = TradingViewClient(service_url=cfg.service_url)
    res = client.test_connection()
    set_config_val("tradingview_service_url", cfg.service_url.strip())
    return {
        "saved": True,
        "connection_test": res
    }

@router.get("/tradingview/validation-report")
def get_validation_report(timeframe: str = "5"):
    client = TradingViewClient()
    report = client.get_validation_report(timeframe=timeframe)
    return report

# Legacy Alpaca routes redirected to TradingView for zero-breakage backwards compatibility
@router.post("/alpaca/test")
def test_alpaca(cfg: AlpacaConfigRequest):
    client = TradingViewClient()
    return client.test_connection()

@router.post("/alpaca/save")
def save_alpaca(cfg: AlpacaConfigRequest):
    client = TradingViewClient()
    res = client.test_connection()
    return {
        "saved": True,
        "connection_test": res
    }

@router.post("/telegram/test")
def test_telegram(cfg: TelegramConfigRequest):
    notifier = TelegramNotifier()
    res = notifier.test_connection(token=cfg.bot_token, chat=cfg.chat_id)
    return res

@router.post("/telegram/save")
def save_telegram(cfg: TelegramConfigRequest):
    if not cfg.bot_token.strip() or not cfg.chat_id.strip():
        raise HTTPException(status_code=400, detail="Bot Token and Chat ID cannot be empty")
    
    notifier = TelegramNotifier()
    res = notifier.test_connection(token=cfg.bot_token, chat=cfg.chat_id)
    
    set_config_val("telegram_bot_token", cfg.bot_token.strip())
    set_config_val("telegram_chat_id", cfg.chat_id.strip())
    
    return {
        "saved": True,
        "connection_test": res
    }

class TelegramBroadcastRequest(BaseModel):
    message: Optional[str] = None

class TelegramToggleSubscriberRequest(BaseModel):
    chat_id: str
    is_active: bool

@router.get("/telegram/subscribers")
def get_telegram_subscribers():
    notifier = TelegramNotifier()
    all_subs = notifier.get_subscribers(active_only=False)
    active_subs = [s for s in all_subs if s.get("is_active") == 1]
    return {
        "subscribers": all_subs,
        "total_count": len(all_subs),
        "active_count": len(active_subs)
    }

@router.post("/telegram/broadcast")
def broadcast_telegram(req: TelegramBroadcastRequest):
    notifier = TelegramNotifier()
    msg = req.message or "📢 Trading Bot Broadcast Test: Multi-subscriber notification verified."
    res = notifier.broadcast_message(msg, notification_type="BROADCAST_TEST")
    return res

@router.post("/telegram/toggle-subscriber")
def toggle_telegram_subscriber(req: TelegramToggleSubscriberRequest):
    notifier = TelegramNotifier()
    if req.is_active:
        res = notifier.register_subscriber(req.chat_id)
    else:
        res = notifier.unsubscribe(req.chat_id)
    return {"success": res, "chat_id": req.chat_id, "is_active": req.is_active}

@router.post("/telegram/poll")
def poll_telegram():
    notifier = TelegramNotifier()
    res = notifier.poll_telegram_updates()
    return res

@router.post("/strategy/save")
def save_strategy(cfg: StrategyConfigRequest):
    set_config_val("min_score", cfg.min_score)
    set_config_val("min_rr", cfg.min_rr)
    set_config_val("trading_quantity", cfg.trading_quantity)
    return {"saved": True, "config": cfg.model_dump()}
