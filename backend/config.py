"""
Central configuration for the picker backend.
"""
import os
from pathlib import Path
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Tickers
# ---------------------------------------------------------------------------
TICKERS = ["SPY", "QQQ", "SPX", "AAPL", "GOOGL", "NVDA", "TSLA", "AMZN", "MSFT", "PLTR"]

# ---------------------------------------------------------------------------
# Market session hours (US Eastern)
# ---------------------------------------------------------------------------
ET = ZoneInfo("America/New_York")

SESSION_HOURS = {
    "pre":   ("04:00", "09:30"),
    "regular": ("09:30", "16:00"),
    "after": ("16:00", "20:00"),
}


def classify_session(dt_et) -> str:
    """Return 'pre', 'regular', 'after', or 'closed' for a datetime in ET."""
    t = dt_et.strftime("%H:%M")
    for session, (start, end) in SESSION_HOURS.items():
        if start <= t < end:
            return session
    return "closed"


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
DB_PATH: str = os.environ.get("DB_PATH", str(BASE_DIR / "picker.db"))

# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------
FETCH_INTERVAL_SECONDS: int = int(os.environ.get("FETCH_INTERVAL", "300"))  # 5 minutes
OHLCV_FETCH_LIMIT: int = 400  # bars per fetch — today (~190) + prev regular (~78)
ALERT_DEDUP_SECS: int = 900  # suppress same alert within 15 min

# ---------------------------------------------------------------------------
# AI evaluator
# ---------------------------------------------------------------------------
ML_MIN_SAMPLES: int = 500          # fall back to rule-only below this
ABSTAIN_CONFIDENCE_THRESHOLD: float = 0.40  # predictions below this become ABSTAIN
PREDICTION_HORIZON_BARS: int = 3   # evaluate outcome after N 5-min bars

# ---------------------------------------------------------------------------
# LLM Commentary  (optional — set LLM_PROVIDER="disabled" to turn off)
# ---------------------------------------------------------------------------
# Providers: "gemini" | "openai" | "anthropic" | "ollama" | "disabled"
# API keys are read from environment variables — never hard-code them here.
LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "disabled")
LLM_API_KEY: str  = os.environ.get("LLM_API_KEY", "")
# Model overrides (sensible free-tier defaults per provider)
LLM_MODEL: str = os.environ.get("LLM_MODEL", "")  # blank = provider default
# Per-provider defaults used when LLM_MODEL is blank:
LLM_MODEL_DEFAULTS: dict = {
    "gemini":    "gemini-2.0-flash-lite",  # free tier: 30 RPM / 1500 RPD
    "openai":    "gpt-4o-mini",            # cheapest OpenAI model
    "anthropic": "claude-haiku-4-5",       # cheapest Anthropic model
    "ollama":    "llama3.1",               # local, no key needed
}
OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
