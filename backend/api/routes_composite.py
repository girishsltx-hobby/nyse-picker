"""REST endpoints for composite alert data."""
from __future__ import annotations

from fastapi import APIRouter, Query

import db

router = APIRouter()


@router.get("/composite-alerts")
async def get_composite_alerts(
    ticker: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    alerts = await db.get_composite_alerts(ticker=ticker, limit=limit)
    return {"alerts": alerts, "count": len(alerts)}
