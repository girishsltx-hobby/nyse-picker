"""
Confluence scoring module.

Synthesises indicator snapshot fields into bull/bear alignment scores.
Each aligned signal adds 1 point to the matching side.
Maximum possible score depends on how many signals are available.

Scored signals (up to 9 points per side):
  1. EMA state (BULLISH / BEARISH)
  2. EMA stack (ema9 > ema21 > ema50  or  ema9 < ema21 < ema50)
  3. VWAP position (ABOVE / BELOW)
  4. VWAP motion (AWAY on respective side)
  5. Daily trend (BULL / BEAR)
  6. RSI vs 50 midline (> 50 bullish  / < 50 bearish)
  7. Price vs POC (above / below)
  8. Price vs ORB high (above = bullish)
  9. Volume state (HIGH volume on trend bar = conviction)
"""
from __future__ import annotations


def compute_confluence(snapshot: dict, current_price: float) -> dict:
    """
    Args:
        snapshot      – indicator snapshot dict (same keys stored in DB)
        current_price – latest close price

    Returns:
        bull_score      int            – 0–9 bullish signals aligned
        bear_score      int            – 0–9 bearish signals aligned
        confluence_bias str            – BULL | BEAR | MIXED
    """
    bull = 0
    bear = 0

    # 1. EMA state
    ema_state = snapshot.get("ema_state")
    if ema_state == "BULLISH":
        bull += 1
    elif ema_state == "BEARISH":
        bear += 1

    # 2. EMA stack (all three EMAs aligned)
    e9  = snapshot.get("ema9")
    e21 = snapshot.get("ema21")
    e50 = snapshot.get("ema50")
    if e9 is not None and e21 is not None and e50 is not None:
        if e9 > e21 > e50:
            bull += 1
        elif e9 < e21 < e50:
            bear += 1

    # 3. VWAP position
    pvwap = snapshot.get("price_vs_vwap")
    if pvwap == "ABOVE":
        bull += 1
    elif pvwap == "BELOW":
        bear += 1

    # 4. VWAP motion — AWAY in same direction as position
    motion = snapshot.get("vwap_motion")
    if motion == "AWAY":
        if pvwap == "ABOVE":
            bull += 1
        elif pvwap == "BELOW":
            bear += 1

    # 5. Daily trend
    daily = snapshot.get("daily_trend")
    if daily == "BULL":
        bull += 1
    elif daily == "BEAR":
        bear += 1

    # 6. RSI vs 50 midline
    rsi = snapshot.get("rsi_14")
    if rsi is not None:
        if rsi > 50:
            bull += 1
        elif rsi < 50:
            bear += 1

    # 7. Price vs POC
    poc = snapshot.get("poc")
    if poc and current_price:
        if current_price > poc:
            bull += 1
        elif current_price < poc:
            bear += 1

    # 8. Price vs ORB high (above ORB = breakout bullish)
    orb_high = snapshot.get("orb_high")
    if orb_high and current_price:
        if current_price > orb_high:
            bull += 1
        else:
            bear += 1

    # 9. RVOL conviction (high volume on trend bar)
    rvol         = snapshot.get("rvol")
    recent_ret   = snapshot.get("recent_return_5m")
    if rvol is not None and recent_ret is not None and rvol > 1.5:
        if recent_ret > 0:
            bull += 1
        elif recent_ret < 0:
            bear += 1

    if bull > bear:
        bias = "BULL"
    elif bear > bull:
        bias = "BEAR"
    else:
        bias = "MIXED"

    return {
        "bull_score":      bull,
        "bear_score":      bear,
        "confluence_bias": bias,
    }
