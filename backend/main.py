import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.database import init_db, log_system_event
from backend.api import (
    routes_settings,
    routes_scanner,
    routes_signals,
    routes_trades,
    routes_extension,
    routes_tests,
    routes_market
)

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log_system_event("SYSTEM", "Trading Bot backend started successfully")
    yield

app = FastAPI(
    title="Antigravity Multi-Stock Bullish Trading Bot",
    description="Multi-Stock US Market Trading System with TradingView Market Data, TradingView Paper Trading Extension, and Telegram Alerts",
    version="3.0.0",
    lifespan=lifespan
)

# CORS setup for Chrome Extension & local dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(routes_settings.router)
app.include_router(routes_scanner.router)
app.include_router(routes_signals.router)
app.include_router(routes_trades.router)
app.include_router(routes_extension.router)
app.include_router(routes_tests.router)
app.include_router(routes_market.router)

# Mount Static Files for frontend
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def serve_dashboard():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"status": "ONLINE", "message": "Backend online. Frontend not yet installed."}

@app.get("/api/health")
def health_check():
    return {
        "status": "HEALTHY",
        "service": "Antigravity Trading Bot Backend",
        "version": "3.0.0"
    }
