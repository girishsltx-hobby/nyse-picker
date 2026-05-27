"""
Scheduler: runs every FETCH_INTERVAL_SECONDS, cycles through all 9 tickers,
fetches OHLCV via MCP, computes indicators, emits signals, runs AI evaluation,
and broadcasts via WebSocket.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import pandas as pd

from config import FETCH_INTERVAL_SECONDS, OHLCV_FETCH_LIMIT, ALERT_DEDUP_SECS
from mcp_client import tv_mcp
from indicators.ema import compute_crossover
from indicators.vwap import compute_vwap
from indicators.trend import compute_daily_trend
from indicators.volume_profile import compute_volume_profile
from indicators.session_levels import compute_session_levels
from indicators.support_resistance import compute_support_resistance
from indicators.swings import compute_swings
from indicators.rsi import compute_rsi
from indicators.confluence import compute_confluence
from signals.crossover import detect_crossover
from signals.vwap_motion import detect_vwap_cross
from signals.sr_breaks import detect_sr_breaks
from signals.composite import evaluate_composite
from ai.evaluator import run_evaluation, resolve_outcomes, retrain_ml
from api.ws import broadcast
import db

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None

# Per-ticker state cache for cross-cycle signal comparison
_prev_state:    dict[str, dict] = {}
_prev_snapshot: dict[str, dict] = {}
_session_fired: dict[str, set]  = {}
_session_date:  str = ""


async def start_scheduler() -> None:
    global _task
    _task = asyncio.create_task(_loop())
    logger.info("Scheduler started (interval=%ds)", FETCH_INTERVAL_SECONDS)


async def stop_scheduler() -> None:
    global _task
    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    logger.info("Scheduler stopped")


async def _loop() -> None:
    await _run_cycle()
    while True:
        await asyncio.sleep(FETCH_INTERVAL_SECONDS)
        await _run_cycle()


async def _run_cycle() -> None:
    global _session_date, _session_fired
    from config import TICKERS  # Import here to get updated config
    
    logger.info("--- Fetch cycle start ---")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if today != _session_date:
        _session_date = today
        _session_fired.clear()
        logger.info("Session reset — composite alert deduplication cleared")

    for ticker in TICKERS:
        try:
            await _process_ticker(ticker)
        except Exception as exc:
            logger.error("[%s] cycle error: %s", ticker, exc, exc_info=True)

    await resolve_outcomes()
    await retrain_ml()
    logger.info("--- Fetch cycle complete ---")


async def process_ticker_once(ticker: str) -> None:
    """Public wrapper — used by the on-demand /api/ticker/{ticker}/refresh endpoint."""
    await _process_ticker(ticker)


async def _process_ticker(ticker: str) -> None:
    df, current_price = await tv_mcp.fetch_ticker(ticker, limit=OHLCV_FETCH_LIMIT)

    if df.empty:
        logger.warning("[%s] no bars returned", ticker)
        return
    now_ts = datetime.now(timezone.utc).isoformat()

    # --- Persist candles ---
    await db.upsert_candles(ticker, df.to_dict(orient="records"))

    # --- Compute indicators ---
    ema_data = compute_crossover(df)
    vwap_data = compute_vwap(df, current_price)
    trend_data = compute_daily_trend(df)
    poc_data = compute_volume_profile(df)
    session_lvl = compute_session_levels(df)
    swings_data = compute_swings(df)
    sr_data = compute_support_resistance(df, current_price)
    rsi_data = compute_rsi(df)

    closes = df["close"].astype(float)
    recent_return = float((closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2]) if len(closes) >= 2 else 0.0
    volatility = float(closes.pct_change().dropna().tail(20).std()) if len(closes) >= 5 else 0.0

    # RVOL: current bar vs 20-bar average of prior bars
    vols = df["volume"].astype(float) if "volume" in df.columns else None
    rvol: float | None = None
    if vols is not None and len(vols) >= 2:
        avg_vol = float(vols.iloc[:-1].tail(20).mean())
        if avg_vol > 0:
            rvol = round(float(vols.iloc[-1]) / avg_vol, 3)
    volume_state: str | None = None
    if rvol is not None:
        volume_state = "HIGH" if rvol > 1.5 else ("LOW" if rvol < 0.5 else "NORMAL")

    snapshot = {
        "timestamp": now_ts,
        **ema_data,
        **vwap_data,
        **trend_data,
        **poc_data,
        "swing_high": swings_data.get("swing_high"),
        "swing_high_ts": swings_data.get("swing_high_ts"),
        "swing_low": swings_data.get("swing_low"),
        "swing_low_ts": swings_data.get("swing_low_ts"),
        "nearest_support": sr_data.get("nearest_support"),
        "nearest_resistance": sr_data.get("nearest_resistance"),
        "recent_return_5m": round(recent_return, 6),
        "recent_volatility": round(volatility, 6),
        # Volume confirmation (v3)
        "rvol":         rvol,
        "volume_state": volume_state,
        # RSI (v3)
        **rsi_data,
        # Session levels (v2)
        "pm_high":        session_lvl.get("pm_high"),
        "pm_low":         session_lvl.get("pm_low"),
        "orb_high":       session_lvl.get("orb_high"),
        "orb_low":        session_lvl.get("orb_low"),
        "prev_day_high":  session_lvl.get("prev_day_high"),
        "prev_day_low":   session_lvl.get("prev_day_low"),
        "poc_pre":        session_lvl.get("poc_pre"),
        "poc_regular":    session_lvl.get("poc_regular"),
        "poc_after":      session_lvl.get("poc_after"),
    }

    # Confluence (v3) — depends on full snapshot + current price
    confluence_data = compute_confluence(snapshot, current_price)
    snapshot.update(confluence_data)
    await db.upsert_indicator_snapshot(ticker, snapshot)

    # --- Detect signals ---
    prev = _prev_state.get(ticker, {})
    signals: list[dict] = []

    cross_sig = detect_crossover(ticker, prev.get("ema_state"), ema_data)
    if cross_sig:
        signals.append(cross_sig)

    vwap_sig = detect_vwap_cross(ticker, prev.get("price_vs_vwap"), vwap_data, timestamp=now_ts)
    if vwap_sig:
        signals.append(vwap_sig)

    sr_sigs = detect_sr_breaks(
        ticker, current_price,
        prev.get("nearest_support"), prev.get("nearest_resistance"),
        sr_data, timestamp=now_ts,
    )
    signals.extend(sr_sigs)

    for sig in signals:
        await db.insert_signal(ticker, sig)
        await broadcast({"type": "signal", "data": sig})

    # --- AI evaluation ---
    prediction = await run_evaluation(ticker, df, current_price, snapshot)
    await broadcast({
        "type": "prediction",
        "data": {
            "ticker": ticker,
            "timestamp": prediction.timestamp,
            "prediction": prediction.prediction,
            "confidence": prediction.confidence,
            "rules_triggered": json.dumps(prediction.rules_triggered),
            "notes": prediction.notes,
        },
    })

    # --- Price update broadcast ---
    await broadcast({
        "type": "price_update",
        "data": {
            "ticker": ticker,
            "price": current_price,
            "timestamp": now_ts,
            "session": df["session"].iloc[-1],
            **{k: snapshot.get(k) for k in (
                "ema_state", "ema_cross_ts", "price_vs_vwap", "vwap_distance_pct",
                "vwap_motion", "daily_trend", "poc", "nearest_support",
                "nearest_resistance", "swing_high", "swing_low",
            )},
        },
    })

    # Cache state for next cycle
    _prev_state[ticker] = {
        "ema_state":          ema_data.get("ema_state"),
        "price_vs_vwap":      vwap_data.get("price_vs_vwap"),
        "nearest_support":    sr_data.get("nearest_support"),
        "nearest_resistance": sr_data.get("nearest_resistance"),
        "vwap_motion":        vwap_data.get("vwap_motion"),
        "rvol":               snapshot.get("rvol"),
    }

    prev_snap = _prev_snapshot.get(ticker)
    if ticker not in _session_fired:
        _session_fired[ticker] = set()
    composite_alerts = evaluate_composite(
        ticker=ticker,
        snapshot=snapshot,
        prev_snapshot=prev_snap,
        confidence=prediction.confidence,
        current_price=current_price,
        session_fired=_session_fired[ticker],
    )
    for alert in composite_alerts:
        alert["timeframe"] = "5m"
        if await db.composite_alert_exists(ticker, alert["signal"], "5m", ALERT_DEDUP_SECS):
            logger.debug("[%s] DEDUP suppressed %s", ticker, alert["signal"])
            continue
        await db.insert_composite_alert(alert)
        if alert["signal"].startswith("POWER_TREND"):
            _session_fired[ticker].add(alert["signal"])
        await broadcast({"type": "composite_alert", "data": alert})
        logger.info("[%s] COMPOSITE %s tier=%d conf=%.2f suppressed=%s",
                    ticker, alert["signal"], alert["tier"],
                    alert["ai_confidence"], alert.get("suppressed_by"))

    _prev_snapshot[ticker] = {**snapshot, "price": current_price, "rvol": snapshot.get("rvol")}

    logger.info("[%s] price=%.2f ema=%s vwap=%s trend=%s pred=%s(%.2f)",
                ticker, current_price,
                ema_data.get("ema_state", "?"),
                vwap_data.get("price_vs_vwap", "?"),
                trend_data.get("daily_trend", "?"),
                prediction.prediction, prediction.confidence)
