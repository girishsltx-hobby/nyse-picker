"""REST endpoints for indicator data."""
from __future__ import annotations

import asyncio
import logging
from fastapi import APIRouter, HTTPException, Query

import db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/indicators/{ticker}")
async def get_latest_indicators(ticker: str):
    ticker = ticker.upper()
    conn = await db.get_db()
    try:
        rows = await conn.execute_fetchall(
            "SELECT * FROM indicators WHERE ticker=? ORDER BY timestamp DESC LIMIT 1",
            (ticker,),
        )
    finally:
        await conn.close()
    if not rows:
        return {"ticker": ticker, "snapshot": None}
    return {"ticker": ticker, "snapshot": dict(rows[0])}


@router.get("/indicators/{ticker}/history")
async def get_indicator_history(
    ticker: str,
    limit: int = Query(200, ge=1, le=1000),
):
    ticker = ticker.upper()
    conn = await db.get_db()
    try:
        rows = await conn.execute_fetchall(
            "SELECT * FROM indicators WHERE ticker=? ORDER BY timestamp DESC LIMIT ?",
            (ticker, limit),
        )
    finally:
        await conn.close()
    history = [dict(r) for r in reversed(rows)]
    return {"ticker": ticker, "history": history, "count": len(history)}


@router.get("/dashboard")
async def get_dashboard(tickers: str = Query(default="")):
    """Return the latest indicator snapshot + prediction for the requested tickers.
    Pass ?tickers=SPY,QQQ,META (comma-separated). Falls back to config TICKERS if omitted.
    """
    from config import TICKERS as DEFAULT_TICKERS
    if tickers.strip():
        ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    else:
        ticker_list = list(DEFAULT_TICKERS)
    conn = await db.get_db()
    try:
        result = {}
        for ticker in ticker_list:
            ind_rows = await conn.execute_fetchall(
                "SELECT * FROM indicators WHERE ticker=? ORDER BY timestamp DESC LIMIT 1",
                (ticker,),
            )
            pred_rows = await conn.execute_fetchall(
                "SELECT * FROM predictions WHERE ticker=? ORDER BY timestamp DESC LIMIT 1",
                (ticker,),
            )
            candle_rows = await conn.execute_fetchall(
                "SELECT close, session FROM candles WHERE ticker=? ORDER BY timestamp DESC LIMIT 1",
                (ticker,),
            )
            result[ticker] = {
                "indicators": dict(ind_rows[0]) if ind_rows else None,
                "prediction": dict(pred_rows[0]) if pred_rows else None,
                "price": float(candle_rows[0]["close"]) if candle_rows else None,
                "session": candle_rows[0]["session"] if candle_rows else "closed",
            }
    finally:
        await conn.close()
    return {"dashboard": result}


@router.post("/ticker/{ticker}/refresh")
async def refresh_ticker(ticker: str):
    """Fetch live data for any ticker on-demand (used when user adds a new ticker)."""
    from scheduler import process_ticker_once
    ticker = ticker.upper()
    logger.info(f"Refresh requested for ticker: {ticker}")
    
    try:
        await process_ticker_once(ticker)
        logger.info(f"Data fetch completed for {ticker}")
    except Exception as exc:
        logger.error(f"refresh_ticker [{ticker}] fetch failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch data for {ticker}: {str(exc)[:200]}")
    
    conn = await db.get_db()
    try:
        ind_rows = await conn.execute_fetchall(
            "SELECT * FROM indicators WHERE ticker=? ORDER BY timestamp DESC LIMIT 1",
            (ticker,),
        )
        candle_rows = await conn.execute_fetchall(
            "SELECT close, session FROM candles WHERE ticker=? ORDER BY timestamp DESC LIMIT 1",
            (ticker,),
        )
        pred_rows = await conn.execute_fetchall(
            "SELECT * FROM predictions WHERE ticker=? ORDER BY timestamp DESC LIMIT 1",
            (ticker,),
        )
    finally:
        await conn.close()
    
    # If no candle data was stored, the fetch didn't return data
    if not candle_rows:
        logger.warning(f"No candle data found for {ticker} after fetch attempt")
        raise HTTPException(status_code=404, detail=f"No data available for ticker '{ticker}'. It may not be a valid NYSE ticker or data fetch failed.")
    
    logger.info(f"Successfully refreshed {ticker}: price={float(candle_rows[0]['close'])}")
    return {
        "ticker": ticker,
        "indicators": dict(ind_rows[0]) if ind_rows else None,
        "prediction": dict(pred_rows[0]) if pred_rows else None,
        "price": float(candle_rows[0]["close"]) if candle_rows else None,
        "session": candle_rows[0]["session"] if candle_rows else "closed",
    }


@router.post("/refresh-all")
async def refresh_all_tickers():
    """Trigger an immediate fetch cycle for all tickers."""
    from config import TICKERS
    from scheduler import process_ticker_once

    async def _safe(t: str) -> None:
        try:
            await process_ticker_once(t)
        except Exception as exc:
            logger.error("refresh_all [%s]: %s", t, exc)

    await asyncio.gather(*[_safe(t) for t in TICKERS])
    return {"status": "ok", "tickers": list(TICKERS)}
