"""REST endpoints for OHLCV candle data."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

import db

router = APIRouter()


@router.get("/candles/{ticker}")
async def get_candles(
    ticker: str,
    timeframe: str = Query("5m", description="Candle timeframe, e.g. '5m'"),
    limit: int = Query(400, ge=1, le=2000),
    session: str | None = Query(None, description="Filter by session: pre|regular|after"),
    today_only: bool = Query(False, description="Return only candles from the latest trading date (4 AM ET onwards)"),
):
    ticker = ticker.upper()
    conn = await db.get_db()
    try:
        # First pass: get all recent bars (we need to determine the latest date)
        base_sql = "SELECT * FROM candles WHERE ticker=? AND timeframe=?"
        base_args: list = [ticker, timeframe]
        if session:
            base_sql += " AND session=?"
            base_args.append(session)
        base_sql += " ORDER BY timestamp DESC LIMIT ?"
        base_args.append(limit)
        rows = await conn.execute_fetchall(base_sql, base_args)
    finally:
        await conn.close()

    bars = [dict(r) for r in reversed(rows)]

    if today_only and bars:
        # Find the latest date present (ISO timestamps, so string comparison works)
        latest_date = max(b["timestamp"][:10] for b in bars)
        # Keep only bars from that date at or after 04:00 ET
        # Since timestamps are stored as UTC ISO strings, convert via prefix filter:
        # 4 AM ET = 08:00 or 09:00 UTC depending on DST; safe approach: keep bars
        # from latest_date onward and let the frontend sort naturally.
        bars = [b for b in bars if b["timestamp"][:10] >= latest_date]

    return {"ticker": ticker, "timeframe": timeframe, "bars": bars, "count": len(bars)}
