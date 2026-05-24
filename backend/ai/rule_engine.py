"""
Deterministic rule-based AI engine.

All rules use ONLY the computed indicator feature set — no external data,
no news, no free-form inference. Each rule appends a named trigger string.
Confidence = (agreeing_signals / total_checked_signals).
Mixed or low-confidence results return ABSTAIN.
"""
from __future__ import annotations

from config import ABSTAIN_CONFIDENCE_THRESHOLD
from ai.schemas import EvidenceFields, PredictionOutput


# ---------------------------------------------------------------------------
# Individual rule functions — return (vote, trigger_name) or None
# ---------------------------------------------------------------------------

# ── Existing rules ──────────────────────────────────────────────────────────

def _rule_ema(ev: EvidenceFields) -> tuple[str, str] | None:
    if ev.ema_state is None:
        return None
    if ev.ema_state == "BULLISH":
        return ("UP", "ema_bullish")
    return ("DOWN", "ema_bearish")


def _rule_vwap_position(ev: EvidenceFields) -> tuple[str, str] | None:
    if ev.price_vs_vwap is None:
        return None
    if ev.price_vs_vwap == "ABOVE":
        return ("UP", "price_above_vwap")
    return ("DOWN", "price_below_vwap")


def _rule_vwap_motion(ev: EvidenceFields) -> tuple[str, str] | None:
    if ev.vwap_motion is None or ev.price_vs_vwap is None:
        return None
    if ev.vwap_motion == "AWAY" and ev.price_vs_vwap == "ABOVE":
        return ("UP", "vwap_moving_away_above")
    if ev.vwap_motion == "AWAY" and ev.price_vs_vwap == "BELOW":
        return ("DOWN", "vwap_moving_away_below")
    if ev.vwap_motion == "TOWARD":
        if ev.price_vs_vwap == "ABOVE":
            return ("DOWN", "vwap_converging_from_above")
        return ("UP", "vwap_converging_from_below")
    return None


def _rule_daily_trend(ev: EvidenceFields) -> tuple[str, str] | None:
    if ev.daily_trend is None or ev.daily_trend == "NEUTRAL":
        return None
    if ev.daily_trend == "BULL":
        return ("UP", "daily_trend_bull")
    return ("DOWN", "daily_trend_bear")


def _rule_price_vs_poc(ev: EvidenceFields) -> tuple[str, str] | None:
    if ev.poc is None or ev.price is None:
        return None
    if ev.price > ev.poc:
        return ("UP", "price_above_poc")
    return ("DOWN", "price_below_poc")


def _rule_price_vs_support(ev: EvidenceFields) -> tuple[str, str] | None:
    if ev.nearest_support is None or ev.price is None:
        return None
    gap_pct = (ev.price - ev.nearest_support) / ev.nearest_support
    if 0 < gap_pct < 0.003:
        return ("UP", "price_near_support")
    return None


def _rule_price_vs_resistance(ev: EvidenceFields) -> tuple[str, str] | None:
    if ev.nearest_resistance is None or ev.price is None:
        return None
    gap_pct = (ev.nearest_resistance - ev.price) / ev.price
    if 0 < gap_pct < 0.003:
        return ("DOWN", "price_near_resistance")
    return None


def _rule_momentum(ev: EvidenceFields) -> tuple[str, str] | None:
    if ev.recent_return_5m is None:
        return None
    if ev.recent_return_5m > 0.003:
        return ("UP", "positive_momentum")
    if ev.recent_return_5m < -0.003:
        return ("DOWN", "negative_momentum")
    return None


# ── New rules ────────────────────────────────────────────────────────────────

def _rule_ema_stack(ev: EvidenceFields) -> tuple[str, str] | None:
    """EMA stack: ema9 > ema21 > ema50 (bullish) or ema9 < ema21 < ema50 (bearish)."""
    if ev.ema9 is None or ev.ema21 is None or ev.ema50 is None:
        return None
    if ev.ema9 > ev.ema21 > ev.ema50:
        return ("UP", "ema_stack_bullish")
    if ev.ema9 < ev.ema21 < ev.ema50:
        return ("DOWN", "ema_stack_bearish")
    return None


def _rule_vwap_cross(ev: EvidenceFields) -> tuple[str, str] | None:
    """VWAP reclaim (prev below, curr above) or lose (prev above, curr below)."""
    if ev.vwap_cross_dir is None:
        return None
    if ev.vwap_cross_dir == "RECLAIM":
        return ("UP", "vwap_reclaim_bullish")
    return ("DOWN", "vwap_lose_bearish")


def _rule_sr_support_bounce(ev: EvidenceFields) -> tuple[str, str] | None:
    """Price within 0.2% above nearest_support with upward momentum."""
    if ev.nearest_support is None or ev.price is None or ev.recent_return_5m is None:
        return None
    gap_pct = (ev.price - ev.nearest_support) / ev.nearest_support
    if 0 <= gap_pct < 0.002 and ev.recent_return_5m > 0:
        return ("UP", "sr_support_bounce")
    return None


def _rule_volume_surge(ev: EvidenceFields) -> tuple[str, str] | None:
    """Volume > 1.5× avg with directional price move."""
    if ev.volume_ratio is None or ev.recent_return_5m is None:
        return None
    if ev.volume_ratio > 1.5:
        if ev.recent_return_5m > 0:
            return ("UP", "volume_surge_up")
        if ev.recent_return_5m < 0:
            return ("DOWN", "volume_surge_down")
    return None


def _rule_volume_dry_up(ev: EvidenceFields) -> tuple[str, str] | None:
    """Volume < 0.5× avg on a counter-trend bar — trend likely to resume."""
    if ev.volume_ratio is None or ev.recent_return_5m is None or ev.daily_trend is None:
        return None
    if ev.volume_ratio < 0.5:
        if ev.daily_trend == "BULL" and ev.recent_return_5m < 0:
            return ("UP", "volume_dry_up")
        if ev.daily_trend == "BEAR" and ev.recent_return_5m > 0:
            return ("DOWN", "volume_dry_up")
    return None


def _rule_higher_low(ev: EvidenceFields) -> tuple[str, str] | None:
    """Current bar's low > previous bar's low on a pullback bar."""
    if ev.candle_higher_low:
        return ("UP", "higher_low_formed")
    return None


def _rule_lower_high(ev: EvidenceFields) -> tuple[str, str] | None:
    """Current bar's high < previous bar's high on a bounce bar."""
    if ev.candle_lower_high:
        return ("DOWN", "lower_high_formed")
    return None


def _rule_orb_hold(ev: EvidenceFields) -> tuple[str, str] | None:
    """Price pulls back to ORB high and holds (closes within 0.2% above it)."""
    if ev.orb_high is None or ev.price is None:
        return None
    gap_pct = (ev.price - ev.orb_high) / ev.orb_high
    if 0 <= gap_pct < 0.002:
        return ("UP", "opening_range_hold")
    return None


# ── v3 rules: RSI, EMA spread, confluence ────────────────────────────────────

def _rule_rsi_overbought(ev: EvidenceFields) -> tuple[str, str] | None:
    """RSI > 70 — extended, mean-reversion risk to the downside."""
    if ev.rsi_14 is None:
        return None
    if ev.rsi_14 > 70:
        return ("DOWN", "rsi_overbought")
    return None


def _rule_rsi_oversold(ev: EvidenceFields) -> tuple[str, str] | None:
    """RSI < 30 — deeply oversold, bounce risk to the upside."""
    if ev.rsi_14 is None:
        return None
    if ev.rsi_14 < 30:
        return ("UP", "rsi_oversold")
    return None


def _rule_ema_cross_imminent_bull(ev: EvidenceFields) -> tuple[str, str] | None:
    """EMA9 below EMA21 but spread < 0.08% — bullish crossover imminent."""
    if ev.ema_spread_pct is None or ev.ema_state != "BEARISH":
        return None
    if abs(ev.ema_spread_pct) < 0.08:
        return ("UP", "ema_cross_imminent_bull")
    return None


def _rule_ema_cross_imminent_bear(ev: EvidenceFields) -> tuple[str, str] | None:
    """EMA9 above EMA21 but spread < 0.08% — bearish crossover imminent."""
    if ev.ema_spread_pct is None or ev.ema_state != "BULLISH":
        return None
    if abs(ev.ema_spread_pct) < 0.08:
        return ("DOWN", "ema_cross_imminent_bear")
    return None


def _rule_confluence_strong_bull(ev: EvidenceFields) -> tuple[str, str] | None:
    """bull_score >= 6 — strong multi-indicator alignment to the upside."""
    if ev.bull_score is None:
        return None
    if ev.bull_score >= 6:
        return ("UP", "confluence_strong_bull")
    return None


def _rule_confluence_strong_bear(ev: EvidenceFields) -> tuple[str, str] | None:
    """bear_score >= 6 — strong multi-indicator alignment to the downside."""
    if ev.bear_score is None:
        return None
    if ev.bear_score >= 6:
        return ("DOWN", "confluence_strong_bear")
    return None


_RULES = [
    # Existing
    _rule_ema,
    _rule_vwap_position,
    _rule_vwap_motion,
    _rule_daily_trend,
    _rule_price_vs_poc,
    _rule_price_vs_support,
    _rule_price_vs_resistance,
    _rule_momentum,
    # New
    _rule_ema_stack,
    _rule_vwap_cross,
    _rule_sr_support_bounce,
    _rule_volume_surge,
    _rule_volume_dry_up,
    _rule_higher_low,
    _rule_lower_high,
    _rule_orb_hold,
    # v3
    _rule_rsi_overbought,
    _rule_rsi_oversold,
    _rule_ema_cross_imminent_bull,
    _rule_ema_cross_imminent_bear,
    _rule_confluence_strong_bull,
    _rule_confluence_strong_bear,
]

# Weight for each rule (rules not in this map default to 1.0)
_RULE_WEIGHTS: dict[str, float] = {
    # Existing
    "ema_bullish": 1.5,
    "ema_bearish": 1.5,
    "daily_trend_bull": 1.2,
    "daily_trend_bear": 1.2,
    "price_above_vwap": 1.0,
    "price_below_vwap": 1.0,
    # New
    "ema_stack_bullish": 1.2,
    "ema_stack_bearish": 1.2,
    "vwap_reclaim_bullish": 1.3,
    "vwap_lose_bearish": 1.3,
    "sr_support_bounce": 0.8,
    "volume_surge_up": 1.1,
    "volume_surge_down": 1.1,
    "volume_dry_up": 0.6,
    "higher_low_formed": 0.9,
    "lower_high_formed": 0.9,
    "opening_range_hold": 0.7,
    # v3
    "rsi_overbought":          0.9,
    "rsi_oversold":            0.9,
    "ema_cross_imminent_bull": 0.8,
    "ema_cross_imminent_bear": 0.8,
    "confluence_strong_bull":  1.8,
    "confluence_strong_bear":  1.8,
}


def evaluate(ticker: str, evidence: EvidenceFields) -> PredictionOutput:
    """
    Run all rules against the evidence and produce a PredictionOutput.
    Uses ONLY the fields in evidence — no external data.
    """
    votes_up: float = 0.0
    votes_down: float = 0.0
    rules_triggered: list[str] = []

    for rule_fn in _RULES:
        result = rule_fn(evidence)
        if result is None:
            continue
        direction, trigger = result
        weight = _RULE_WEIGHTS.get(trigger, 1.0)
        rules_triggered.append(trigger)
        if direction == "UP":
            votes_up += weight
        else:
            votes_down += weight

    total = votes_up + votes_down
    if total == 0:
        return PredictionOutput(
            ticker=ticker,
            prediction="ABSTAIN",
            confidence=0.0,
            evidence=evidence,
            rules_triggered=[],
            notes="no_rules_fired",
        )

    if votes_up > votes_down:
        raw_conf = votes_up / total
        prediction = "UP" if raw_conf >= ABSTAIN_CONFIDENCE_THRESHOLD else "NEUTRAL"
    elif votes_down > votes_up:
        raw_conf = votes_down / total
        prediction = "DOWN" if raw_conf >= ABSTAIN_CONFIDENCE_THRESHOLD else "NEUTRAL"
    else:
        raw_conf = 0.5
        prediction = "NEUTRAL"

    # If confidence is too low, abstain
    if raw_conf < ABSTAIN_CONFIDENCE_THRESHOLD:
        prediction = "ABSTAIN"

    return PredictionOutput(
        ticker=ticker,
        prediction=prediction,
        confidence=raw_conf,
        evidence=evidence,
        rules_triggered=rules_triggered,
    )
