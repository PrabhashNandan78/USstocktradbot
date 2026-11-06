from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from backend.alpaca_client import AlpacaClient
from backend.telegram_bot import TelegramNotifier
from backend.database import get_config_val, set_config_val

router = APIRouter(prefix="/api/settings", tags=["Settings"])

class AlpacaConfigRequest(BaseModel):
    api_key: str
    secret_key: str
    feed: str = "iex"

class TelegramConfigRequest(BaseModel):
    bot_token: str
    chat_id: str

class StrategyConfigRequest(BaseModel):
    min_score: float = 60.0
    min_rr: float = 2.0
    trading_quantity: float = 1.0

@router.get("/")
def get_all_settings():
    alpaca_key = get_config_val("alpaca_api_key", "")
    masked_key = (alpaca_key[:4] + "..." + alpaca_key[-4:]) if len(alpaca_key) > 8 else ("Set" if alpaca_key else "")
    has_alpaca_secret = bool(get_config_val("alpaca_secret_key", ""))
    
    tg_token = get_config_val("telegram_bot_token", "")
    masked_tg = (tg_token[:4] + "..." + tg_token[-4:]) if len(tg_token) > 8 else ("Set" if tg_token else "")
    
    return {
        "alpaca": {
            "api_key_masked": masked_key,
            "has_secret": has_alpaca_secret,
            "feed": get_config_val("alpaca_feed", "iex"),
            "status": get_config_val("alpaca_connection_status", {"status": "NOT_CONFIGURED"})
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

@router.post("/alpaca/test")
def test_alpaca(cfg: AlpacaConfigRequest):
    client = AlpacaClient(api_key=cfg.api_key, secret_key=cfg.secret_key, feed=cfg.feed)
    res = client.test_connection()
    return res

@router.post("/alpaca/save")
def save_alpaca(cfg: AlpacaConfigRequest):
    if not cfg.api_key.strip() or not cfg.secret_key.strip():
        raise HTTPException(status_code=400, detail="API Key and Secret Key cannot be empty")
    
    client = AlpacaClient(api_key=cfg.api_key, secret_key=cfg.secret_key, feed=cfg.feed)
    res = client.test_connection()
    
    # Save credentials locally on backend only
    set_config_val("alpaca_api_key", cfg.api_key.strip())
    set_config_val("alpaca_secret_key", cfg.secret_key.strip())
    set_config_val("alpaca_feed", cfg.feed.strip().lower())
    
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

@router.post("/strategy/save")
def save_strategy(cfg: StrategyConfigRequest):
    set_config_val("min_score", cfg.min_score)
    set_config_val("min_rr", cfg.min_rr)
    set_config_val("trading_quantity", cfg.trading_quantity)
    return {"saved": True, "config": cfg.model_dump()}
