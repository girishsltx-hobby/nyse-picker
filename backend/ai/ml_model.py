"""
Optional ML scaffold for the AI evaluator.

Uses scikit-learn GradientBoostingClassifier trained on stored
historical (indicator, outcome) rows from the predictions table.

Falls back silently if insufficient data (<ML_MIN_SAMPLES rows with outcomes).
"""
from __future__ import annotations

import json
import logging
import pickle
from pathlib import Path

import numpy as np

from config import ML_MIN_SAMPLES, BASE_DIR
from ai.schemas import EvidenceFields

logger = logging.getLogger(__name__)

_MODEL_PATH = BASE_DIR / "picker_ml_model.pkl"

_FEATURES = [
    "ema9", "ema21",
    "ema_state_enc",       # 1=BULLISH, -1=BEARISH, 0=unknown
    "vwap_distance_pct",
    "vwap_motion_enc",     # 1=AWAY_ABOVE, -1=AWAY_BELOW, 0=TOWARD/FLAT
    "price_vs_vwap_enc",   # 1=ABOVE, -1=BELOW
    "daily_trend_enc",     # 1=BULL, -1=BEAR, 0=NEUTRAL
    "price_vs_poc",        # price - poc
    "dist_to_support",     # price - nearest_support (None → 0)
    "dist_to_resistance",  # nearest_resistance - price (None → 0)
    "recent_return_5m",
    "recent_volatility",
]

_LABEL_MAP = {"UP": 1, "DOWN": -1, "FLAT": 0}
_LABEL_REVERSE = {1: "UP", -1: "DOWN", 0: "NEUTRAL"}


def _encode_evidence(ev: EvidenceFields) -> np.ndarray:
    def safe_float(val, default=0.0):
        """Convert value to float, handle None and NaN."""
        if val is None:
            return default
        try:
            f = float(val)
            return default if np.isnan(f) else f
        except (TypeError, ValueError):
            return default

    price = safe_float(ev.price, 0.0)
    vwap = safe_float(ev.vwap, price)

    ema_state_enc = 1 if ev.ema_state == "BULLISH" else (-1 if ev.ema_state == "BEARISH" else 0)
    price_vs_vwap_enc = 1 if ev.price_vs_vwap == "ABOVE" else -1 if ev.price_vs_vwap == "BELOW" else 0
    daily_trend_enc = 1 if ev.daily_trend == "BULL" else (-1 if ev.daily_trend == "BEAR" else 0)

    if ev.vwap_motion == "AWAY" and ev.price_vs_vwap == "ABOVE":
        vwap_motion_enc = 1.0
    elif ev.vwap_motion == "AWAY" and ev.price_vs_vwap == "BELOW":
        vwap_motion_enc = -1.0
    else:
        vwap_motion_enc = 0.0

    poc = safe_float(ev.poc, price)
    sup = safe_float(ev.nearest_support, price)
    res = safe_float(ev.nearest_resistance, price)

    return np.array([
        safe_float(ev.ema9, price),
        safe_float(ev.ema21, price),
        ema_state_enc,
        safe_float(ev.vwap_distance_pct, 0.0),
        vwap_motion_enc,
        price_vs_vwap_enc,
        daily_trend_enc,
        price - poc,
        price - sup,
        res - price,
        safe_float(ev.recent_return_5m, 0.0),
        safe_float(ev.recent_volatility, 0.0),
    ], dtype=float).reshape(1, -1)


class MLEvaluator:
    def __init__(self) -> None:
        self._model = None
        self._trained = False
        self._load()

    def _load(self) -> None:
        if _MODEL_PATH.exists():
            try:
                with open(_MODEL_PATH, "rb") as f:
                    self._model = pickle.load(f)
                self._trained = True
                logger.info("ML model loaded from %s", _MODEL_PATH)
            except Exception as exc:
                logger.warning("Failed to load ML model: %s", exc)

    def _save(self) -> None:
        with open(_MODEL_PATH, "wb") as f:
            pickle.dump(self._model, f)

    def train(self, rows: list[dict]) -> None:
        """
        rows: list of dicts with keys: evidence (JSON str), outcome ('UP'|'DOWN'|'FLAT')
        """
        from sklearn.ensemble import GradientBoostingClassifier

        if len(rows) < ML_MIN_SAMPLES:
            logger.info("Skipping ML training: only %d samples (need %d)", len(rows), ML_MIN_SAMPLES)
            return

        X, y = [], []
        for row in rows:
            outcome = row.get("outcome")
            if outcome not in _LABEL_MAP:
                continue
            try:
                ev_dict = json.loads(row["evidence"]) if isinstance(row["evidence"], str) else row["evidence"]
                ev = EvidenceFields(**ev_dict)
                X_row = _encode_evidence(ev).flatten()
                # Skip rows with any remaining NaN values
                if np.any(np.isnan(X_row)):
                    logger.debug("Skipping training row with NaN values")
                    continue
                X.append(X_row)
                y.append(_LABEL_MAP[outcome])
            except Exception as exc:
                logger.debug("Skipping training row: %s", exc)
                continue

        if len(X) < ML_MIN_SAMPLES:
            logger.info("Insufficient training samples after cleaning: %d (need %d)", len(X), ML_MIN_SAMPLES)
            return

        self._model = GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=42)
        self._model.fit(np.array(X), np.array(y))
        self._trained = True
        self._save()
        logger.info("ML model trained on %d samples", len(X))

    def predict(self, evidence: EvidenceFields) -> tuple[str, float] | None:
        """
        Returns (direction, confidence) or None if model not trained.
        """
        if not self._trained or self._model is None:
            return None
        try:
            X = _encode_evidence(evidence)
            # Final safeguard: replace any remaining NaN with 0.0
            X = np.nan_to_num(X, nan=0.0)
            label = int(self._model.predict(X)[0])
            proba = self._model.predict_proba(X)[0]
            confidence = float(max(proba))
            direction = _LABEL_REVERSE.get(label, "NEUTRAL")
            return direction, round(confidence, 4)
        except Exception as exc:
            logger.warning("ML prediction failed: %s", exc)
            return None


# Module-level singleton
ml_evaluator = MLEvaluator()
