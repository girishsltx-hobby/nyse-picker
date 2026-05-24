"""
Database initialisation and async helper utilities (aiosqlite).
"""
import aiosqlite
from config import DB_PATH

CREATE_TABLES_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS candles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL,   -- ISO-8601 UTC
    timeframe   TEXT    NOT NULL DEFAULT '5m',
    session     TEXT    NOT NULL DEFAULT 'regular',
    open        REAL    NOT NULL,
    high        REAL    NOT NULL,
    low         REAL    NOT NULL,
    close       REAL    NOT NULL,
    volume      REAL    NOT NULL DEFAULT 0,
    UNIQUE(ticker, timestamp, timeframe)
);

CREATE TABLE IF NOT EXISTS indicators (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT    NOT NULL,
    timestamp           TEXT    NOT NULL,
    ema9                REAL,
    ema21               REAL,
    ema50               REAL,
    ema_state           TEXT,   -- BULLISH | BEARISH
    ema_cross_ts        TEXT,   -- ISO-8601 of last crossover
    vwap                REAL,
    vwap_distance_pct   REAL,
    vwap_motion         TEXT,   -- TOWARD | AWAY | FLAT
    vwap_slope          REAL,
    price_vs_vwap       TEXT,   -- ABOVE | BELOW
    daily_trend         TEXT,   -- BULL | BEAR | NEUTRAL
    poc                 REAL,
    nearest_support     REAL,
    nearest_resistance  REAL,
    swing_high          REAL,
    swing_high_ts       TEXT,
    swing_low           REAL,
    swing_low_ts        TEXT,
    recent_return_5m    REAL,
    recent_volatility   REAL,
    -- Session levels (added v2)
    pm_high             REAL,   -- premarket high
    pm_low              REAL,   -- premarket low
    orb_high            REAL,   -- 15-min ORB high
    orb_low             REAL,   -- 15-min ORB low
    prev_day_high       REAL,   -- previous regular session high
    prev_day_low        REAL,   -- previous regular session low
    poc_pre             REAL,   -- premarket session POC
    poc_regular         REAL,   -- regular session POC
    poc_after           REAL,   -- after-hours session POC
    -- Momentum / RSI (added v3)
    rsi_14              REAL,   -- RSI-14 (Wilder smoothing)
    rsi_state           TEXT,   -- OVERBOUGHT | OVERSOLD | NEUTRAL
    -- Volume confirmation (added v3)
    rvol                REAL,   -- current bar volume / 20-bar avg
    volume_state        TEXT,   -- HIGH | LOW | NORMAL
    -- EMA spread (added v3)
    ema_spread_pct      REAL,   -- (ema9 - ema21) / ema21 * 100
    -- Confluence scoring (added v3)
    bull_score          INTEGER,
    bear_score          INTEGER,
    confluence_bias     TEXT,   -- BULL | BEAR | MIXED
    UNIQUE(ticker, timestamp)
);

CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL,
    signal_type TEXT    NOT NULL,   -- ema_cross | vwap_reclaim | vwap_breakdown | sr_break | new_swing
    direction   TEXT    NOT NULL,   -- UP | DOWN
    details     TEXT                -- JSON blob
);

CREATE TABLE IF NOT EXISTS predictions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT    NOT NULL,
    timestamp           TEXT    NOT NULL,
    prediction          TEXT    NOT NULL,   -- UP | DOWN | NEUTRAL | ABSTAIN
    confidence          REAL    NOT NULL,
    evidence            TEXT    NOT NULL,   -- JSON blob
    rules_triggered     TEXT    NOT NULL,   -- JSON array
    notes               TEXT,
    outcome             TEXT,               -- UP | DOWN | FLAT (filled in later)
    outcome_timestamp   TEXT
);

CREATE INDEX IF NOT EXISTS idx_candles_ticker_ts ON candles(ticker, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_indicators_ticker_ts ON indicators(ticker, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signals_ticker_ts ON signals(ticker, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_ticker_ts ON predictions(ticker, timestamp DESC);

CREATE TABLE IF NOT EXISTS composite_alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT    NOT NULL,
    timestamp       TEXT    NOT NULL,
    signal          TEXT    NOT NULL,   -- POWER_TREND_BULL | STRUCTURE_BREAK_UP | ...
    direction       TEXT    NOT NULL,   -- UP | DOWN | WARNING
    tier            INTEGER NOT NULL,   -- 1 | 2 | 3
    ai_confidence   REAL    NOT NULL,
    components      TEXT    NOT NULL,   -- JSON array
    suppressed_by   TEXT,               -- null or reason string
    timeframe       TEXT    NOT NULL DEFAULT '5m',
    extra           TEXT                -- JSON blob for level_price, level_name, etc.
);

CREATE INDEX IF NOT EXISTS idx_composite_alerts_ticker_ts ON composite_alerts(ticker, timestamp DESC);
"""


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLES_SQL)
        # Migration: add v2 session-level columns if they don't exist yet
        _new_cols = [
            "pm_high", "pm_low", "orb_high", "orb_low",
            "prev_day_high", "prev_day_low",
            "poc_pre", "poc_regular", "poc_after",
            "ema50",
            # v3
            ("rsi_14",         "REAL"),
            ("rsi_state",      "TEXT"),
            ("rvol",           "REAL"),
            ("volume_state",   "TEXT"),
            ("ema_spread_pct", "REAL"),
            ("bull_score",     "INTEGER"),
            ("bear_score",     "INTEGER"),
            ("confluence_bias","TEXT"),
        ]
        for col in _new_cols:
            if isinstance(col, tuple):
                name, ctype = col
                stmt = f"ALTER TABLE indicators ADD COLUMN {name} {ctype}"
            else:
                stmt = f"ALTER TABLE indicators ADD COLUMN {col} REAL"
            try:
                await db.execute(stmt)
            except Exception:
                pass  # column already exists
        # Add timeframe column to indicators if missing
        for stmt in [
            "ALTER TABLE indicators ADD COLUMN timeframe TEXT DEFAULT '5m'",
            "ALTER TABLE composite_alerts ADD COLUMN timeframe TEXT DEFAULT '5m'",
        ]:
            try:
                await db.execute(stmt)
            except Exception:
                pass
        await db.commit()


async def get_db() -> aiosqlite.Connection:
    """Return a new connection. Caller is responsible for closing it."""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def upsert_candles(ticker: str, bars: list[dict]) -> None:
    """Insert-or-replace a list of OHLCV bar dicts for a ticker."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            """
            INSERT INTO candles (ticker, timestamp, timeframe, session, open, high, low, close, volume)
            VALUES (:ticker, :timestamp, :timeframe, :session, :open, :high, :low, :close, :volume)
            ON CONFLICT(ticker, timestamp, timeframe) DO UPDATE SET
                open    = excluded.open,
                high    = excluded.high,
                low     = excluded.low,
                close   = excluded.close,
                volume  = excluded.volume,
                session = excluded.session
            """,
            [{"ticker": ticker, **bar} for bar in bars],
        )
        await db.commit()


async def upsert_indicator_snapshot(ticker: str, snapshot: dict, timeframe: str = "5m") -> None:
    """Insert-or-replace a full indicator snapshot for a ticker + timestamp + timeframe."""
    snap = {**snapshot, "timeframe": timeframe}
    fields = list(snap.keys())
    placeholders = ", ".join(["?"] * (len(fields) + 1))
    vals = [ticker] + [snap[f] for f in fields]
    sql = (
        f"INSERT INTO indicators (ticker, {', '.join(fields)}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT(ticker, timestamp) DO UPDATE SET "
        + ", ".join(f"{f} = excluded.{f}" for f in fields if f != "timestamp")
    )
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(sql, vals)
        await db.commit()


async def insert_signal(ticker: str, signal: dict) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO signals (ticker, timestamp, signal_type, direction, details) "
            "VALUES (:ticker, :timestamp, :signal_type, :direction, :details)",
            {"ticker": ticker, **signal},
        )
        await db.commit()


async def insert_prediction(prediction: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO predictions (ticker, timestamp, prediction, confidence, evidence, rules_triggered, notes) "
            "VALUES (:ticker, :timestamp, :prediction, :confidence, :evidence, :rules_triggered, :notes)",
            prediction,
        )
        await db.commit()
        return cur.lastrowid


async def update_prediction_outcome(prediction_id: int, outcome: str, outcome_ts: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE predictions SET outcome = ?, outcome_timestamp = ? WHERE id = ?",
            (outcome, outcome_ts, prediction_id),
        )
        await db.commit()


async def composite_alert_exists(
    ticker: str, signal: str, timeframe: str, within_seconds: int
) -> bool:
    """Return True if the same (ticker, signal, timeframe) alert was inserted recently."""
    from datetime import datetime, timezone, timedelta
    since = (datetime.now(timezone.utc) - timedelta(seconds=within_seconds)).isoformat()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await conn.execute_fetchall(
            "SELECT id FROM composite_alerts "
            "WHERE ticker=? AND signal=? AND timeframe=? AND timestamp >= ? LIMIT 1",
            (ticker, signal, timeframe, since),
        )
    return len(rows) > 0


async def insert_composite_alert(alert: dict) -> None:
    import json as _json
    extra_keys = {"level_name", "level_price", "poc_level"}
    extra = {k: alert[k] for k in extra_keys if k in alert}
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO composite_alerts "
            "(ticker, timestamp, signal, direction, tier, ai_confidence, components, suppressed_by, timeframe, extra) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                alert["ticker"],
                alert["timestamp"],
                alert["signal"],
                alert["direction"],
                alert["tier"],
                alert["ai_confidence"],
                _json.dumps(alert.get("components", [])),
                alert.get("suppressed_by"),
                alert.get("timeframe", "5m"),
                _json.dumps(extra) if extra else None,
            ),
        )
        await db.commit()


async def get_composite_alerts(
    ticker: str | None = None,
    timeframe: str | None = None,
    limit: int = 100,
) -> list[dict]:
    import json as _json
    conditions = []
    params: list = []
    if ticker:
        conditions.append("ticker = ?")
        params.append(ticker.upper())
    if timeframe:
        conditions.append("timeframe = ?")
        params.append(timeframe)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await conn.execute_fetchall(
            f"SELECT * FROM composite_alerts {where} ORDER BY timestamp DESC LIMIT ?",
            params,
        )
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["components"] = _json.loads(d["components"] or "[]")
        except Exception:
            d["components"] = []
        try:
            extra = _json.loads(d.get("extra") or "{}")
            d.update(extra)
        except Exception:
            pass
        d.pop("extra", None)
        result.append(d)
    return result
