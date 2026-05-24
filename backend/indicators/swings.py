"""
Swing High / Low detection using a pivot window.

A bar is a swing high if its high is strictly greater than the N bars
to its left AND right. Same logic for swing lows.
"""
from __future__ import annotations

import pandas as pd

_LEFT = 3
_RIGHT = 3


def compute_swings(df: pd.DataFrame, left: int = _LEFT, right: int = _RIGHT) -> dict:
    """
    df must have columns: timestamp, high, low (sorted oldest → newest).
    Returns the most recent confirmed swing high and swing low with timestamps.
    """
    if len(df) < left + right + 1:
        return {"swing_high": None, "swing_high_ts": None, "swing_low": None, "swing_low_ts": None}

    highs = df["high"].values
    lows = df["low"].values
    timestamps = df["timestamp"].values

    swing_highs: list[tuple[float, str]] = []
    swing_lows: list[tuple[float, str]] = []

    # Only check bars where a full left+right window exists
    for i in range(left, len(df) - right):
        h = highs[i]
        l = lows[i]

        if h > max(highs[i - left: i]) and h > max(highs[i + 1: i + right + 1]):
            swing_highs.append((h, str(timestamps[i])))

        if l < min(lows[i - left: i]) and l < min(lows[i + 1: i + right + 1]):
            swing_lows.append((l, str(timestamps[i])))

    sh_price, sh_ts = swing_highs[-1] if swing_highs else (None, None)
    sl_price, sl_ts = swing_lows[-1] if swing_lows else (None, None)

    return {
        "swing_high": round(sh_price, 4) if sh_price is not None else None,
        "swing_high_ts": sh_ts,
        "swing_low": round(sl_price, 4) if sl_price is not None else None,
        "swing_low_ts": sl_ts,
        "all_swing_highs": [(round(p, 4), t) for p, t in swing_highs],
        "all_swing_lows": [(round(p, 4), t) for p, t in swing_lows],
    }
