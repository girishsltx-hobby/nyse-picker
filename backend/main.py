"""
FastAPI application entry point.
"""
import logging
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import init_db
from mcp_client import tv_mcp
from scheduler import start_scheduler, stop_scheduler
from api.routes_candles import router as candles_router
from api.routes_indicators import router as indicators_router
from api.routes_signals import router as signals_router
from api.routes_predictions import router as predictions_router
from api.routes_composite import router as composite_router
from api.ws import router as ws_router
from api.cron import router as cron_router          # ← ADD THIS



@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await tv_mcp.connect()
    await start_scheduler()
    yield
    # Shutdown
    await stop_scheduler()
    await tv_mcp.disconnect()


app = FastAPI(title="Picker — NYSE Ticker Dashboard", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173",
        "https://nyse-picker-007.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(candles_router, prefix="/api")
app.include_router(indicators_router, prefix="/api")
app.include_router(signals_router, prefix="/api")
app.include_router(predictions_router, prefix="/api")
app.include_router(composite_router, prefix="/api")
app.include_router(ws_router)
app.include_router(cron_router)                     # ← ADD THIS


@app.get("/api/health")
async def health():
    return {"status": "ok", "data_source": "yfinance"}
