"""
Vercel Cron endpoint — triggers the full scheduler fetch cycle.
Called every 5 minutes by Vercel Cron (configured in vercel.json).
Protected by CRON_SECRET env var.
"""
import os
import logging
from fastapi import APIRouter, HTTPException, Request
from scheduler import _run_cycle

logger = logging.getLogger(__name__)
router = APIRouter()

CRON_SECRET = os.getenv("CRON_SECRET", "")


@router.get("/api/cron/fetch-data")
async def cron_fetch_data(request: Request):
    # ── Auth check ───────────────────────────────────────────────────────────
    auth = request.headers.get("authorization", "")
    if CRON_SECRET and auth != f"Bearer {CRON_SECRET}":
        logger.warning("Cron called with invalid auth header")
        raise HTTPException(status_code=401, detail="Unauthorized")

    # ── Run full cycle (all tickers) ─────────────────────────────────────────
    try:
        logger.info("Vercel cron triggered — starting fetch cycle")
        await _run_cycle()
        logger.info("Vercel cron — fetch cycle complete")
        return {"status": "ok", "message": "Fetch cycle completed"}
    except Exception as exc:
        logger.error("Cron fetch cycle failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))