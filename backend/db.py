"""
Database initialisation and async helper utilities.
Dual-mode: uses Turso (libSQL) in production, aiosqlite locally.
"""
import os
import json as _json
import aiosqlite
from config import DB_PATH

# ── Turso detection ──────────────────────────────────────────────────────────
TURSO_URL   = os.getenv("TURSO_DATABASE_URL", "")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")
USE_TURSO   = bool(TURSO_URL and TURSO_TOKEN)

if USE_TURSO:
    import libsql_experimental as libsql   # pip install libsql-experimental

# ── DDL ──────────────────────────────────────────────────────────────────────
CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS candles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL,
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
    timeframe           TEXT    DEFAULT '5m',
    ema9                REAL,
    ema21               REAL,
    ema50               REAL,
    ema_state           TEXT,
    ema_cross_ts        TEXT,
    vwap                REAL,
    vwap_distance_pct   REAL,
    vwap_motion         TEXT,
    vwap_slope          REAL,
    price_vs_vwap       TEXT,
    daily_trend         TEXT,
    poc                 REAL,
    nearest_support     REAL,
    nearest_resistance  REAL,
    swing_high          REAL,
    swing_high_ts       TEXT,
    swing_low           REAL,
    swing_low_ts        TEXT,
    recent_return_5m    REAL,
    recent_volatility   REAL,
    pm_high             REAL,
    pm_low              REAL,
    orb_high            REAL,
    orb_low             REAL,
    prev_day_high       REAL,
    prev_day_low        REAL,
    poc_pre             REAL,
    poc_regular         REAL,
    poc_after           REAL,
    rsi_14              REAL,
    rsi_state           TEXT,
    rvol                REAL,
    volume_state        TEXT,
    ema_spread_pct      REAL,
    bull_score          INTEGER,
    bear_score          INTEGER,
    confluence_bias     TEXT,
    UNIQUE(ticker, timestamp)
);

CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL,
    signal_type TEXT    NOT NULL,
    direction   TEXT    NOT NULL,
    details     TEXT
);

CREATE TABLE IF NOT EXISTS predictions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT    NOT NULL,
    timestamp           TEXT    NOT NULL,
    prediction          TEXT    NOT NULL,
    confidence          REAL    NOT NULL,
    evidence            TEXT    NOT NULL,
    rules_triggered     TEXT    NOT NULL,
    notes               TEXT,
    outcome             TEXT,
    outcome_timestamp   TEXT
);

CREATE TABLE IF NOT EXISTS composite_alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT    NOT NULL,
    timestamp       TEXT    NOT NULL,
    signal          TEXT    NOT NULL,
    direction       TEXT    NOT NULL,
    tier            INTEGER NOT NULL,
    ai_confidence   REAL    NOT NULL,
    components      TEXT    NOT NULL,
    suppressed_by   TEXT,
    timeframe       TEXT    NOT NULL DEFAULT '5m',
    extra           TEXT
);

CREATE INDEX IF NOT EXISTS idx_candles_ticker_ts         ON candles(ticker, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_indicators_ticker_ts      ON indicators(ticker, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signals_ticker_ts         ON signals(ticker, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_ticker_ts     ON predictions(ticker, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_composite_alerts_ticker_ts ON composite_alerts(ticker, timestamp DESC);
"""

# ── Connection helpers ────────────────────────────────────────────────────────

class TursoConnection:
    """Thin async-compatible wrapper around libsql_experimental.Connection."""

    def __init__(self, conn):
        self._conn = conn

    # --- query helpers -------------------------------------------------------

    async def execute(self, sql: str, params=()) -> "TursoCursor":
        cur = self._conn.execute(sql, params)
        return TursoCursor(cur)

    async def executemany(self, sql: str, seq):
        for params in seq:
            if isinstance(params, dict):
                self._conn.execute(sql, list(params.values()))
            else:
                self._conn.execute(sql, list(params))
        self._conn.commit()

    async def executescript(self, script: str):
        # libsql doesn't support executescript; run statement-by-statement
        for stmt in [s.strip() for s in script.split(";") if s.strip()]:
            self._conn.execute(stmt)
        self._conn.commit()

    async def execute_fetchall(self, sql: str, params=()):
        cur = self._conn.execute(sql, params)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, row)) for row in rows]

    async def commit(self):
        self._conn.commit()

    async def close(self):
        self._conn.close()

    # --- context manager -----------------------------------------------------

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self._conn.commit()
        self._conn.close()


class TursoCursor:
    def __init__(self, cur):
        self._cur = cur
        cols = [d[0] for d in cur.description] if cur.description else []
        self._rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        self._idx = 0

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._rows):
            raise StopAsyncIteration
        row = self._rows[self._idx]
        self._idx += 1
        return row


def _turso_conn() -> TursoConnection:
    conn = libsql.connect(TURSO_URL, auth_token=TURSO_TOKEN)
    return TursoConnection(conn)


async def _sqlite_conn() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def get_db():
    """Return a new connection. Caller is responsible for closing it."""
    if USE_TURSO:
        return _turso_conn()
    return await _sqlite_conn()


# ── Init ─────────────────────────────────────────────────────────────────────

async def init_db() -> None:
    if USE_TURSO:
        async with _turso_conn() as db:
            await db.executescript(CREATE_TABLES_SQL)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.executescript("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;")
            await db.executescript(CREATE_TABLES_SQL)
            # Legacy migration: add columns that may be missing in older DBs
            _migrations = [
                ("indicators", "pm_high",          "REAL"),
                ("indicators", "pm_low",            "REAL"),
                ("indicators", "orb_high",          "REAL"),
                ("indicators", "orb_low",           "REAL"),
                ("indicators", "prev_day_high",     "REAL"),
                ("indicators", "prev_day_low",      "REAL"),
                ("indicators", "poc_pre",           "REAL"),
                ("indicators", "poc_regular",       "REAL"),
                ("indicators", "poc_after",         "REAL"),
                ("indicators", "ema50",             "REAL"),
                ("indicators", "rsi_14",            "REAL"),
                ("indicators", "rsi_state",         "TEXT"),
                ("indicators", "rvol",              "REAL"),
                ("indicators", "volume_state",      "TEXT"),
                ("indicators", "ema_spread_pct",    "REAL"),
                ("indicators", "bull_score",        "INTEGER"),
                ("indicators", "bear_score",        "INTEGER"),
                ("indicators", "confluence_bias",   "TEXT"),
                ("indicators", "timeframe",         "TEXT DEFAULT '5m'"),
                ("composite_alerts", "timeframe",   "TEXT DEFAULT '5m'"),
            ]
            for table, col, ctype in _migrations:
                try:
                    await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ctype}")
                except Exception:
                    pass  # column already exists
            await db.commit()


# ── Write helpers ─────────────────────────────────────────────────────────────

async def upsert_candles(ticker: str, bars: list[dict]) -> None:
    sql = """
        INSERT INTO candles (ticker, timestamp, timeframe, session, open, high, low, close, volume)
        VALUES (:ticker, :timestamp, :timeframe, :session, :open, :high, :low, :close, :volume)
        ON CONFLICT(ticker, timestamp, timeframe) DO UPDATE SET
            open    = excluded.open,
            high    = excluded.high,
            low     = excluded.low,
            close   = excluded.close,
            volume  = excluded.volume,
            session = excluded.session
    """
    rows = [{"ticker": ticker, **bar} for bar in bars]
    if USE_TURSO:
        async with _turso_conn() as db:
            await db.executemany(sql, rows)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.executemany(sql, rows)
            await db.commit()


async def upsert_indicator_snapshot(ticker: str, snapshot: dict, timeframe: str = "5m") -> None:
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
    if USE_TURSO:
        async with _turso_conn() as db:
            await db.execute(sql, vals)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(sql, vals)
            await db.commit()


async def insert_signal(ticker: str, signal: dict) -> None:
    sql = (
        "INSERT INTO signals (ticker, timestamp, signal_type, direction, details) "
        "VALUES (?, ?, ?, ?, ?)"
    )
    vals = (ticker, signal["timestamp"], signal["signal_type"], signal["direction"], signal.get("details"))
    if USE_TURSO:
        async with _turso_conn() as db:
            await db.execute(sql, vals)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(sql, vals)
            await db.commit()


async def insert_prediction(prediction: dict) -> int:
    sql = (
        "INSERT INTO predictions (ticker, timestamp, prediction, confidence, evidence, rules_triggered, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
    vals = (
        prediction["ticker"], prediction["timestamp"], prediction["prediction"],
        prediction["confidence"], prediction["evidence"],
        prediction["rules_triggered"], prediction.get("notes"),
    )
    if USE_TURSO:
        async with _turso_conn() as db:
            cur = await db.execute(sql, vals)
            return cur.lastrowid
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(sql, vals)
            await db.commit()
            return cur.lastrowid


async def update_prediction_outcome(prediction_id: int, outcome: str, outcome_ts: str) -> None:
    sql = "UPDATE predictions SET outcome = ?, outcome_timestamp = ? WHERE id = ?"
    vals = (outcome, outcome_ts, prediction_id)
    if USE_TURSO:
        async with _turso_conn() as db:
            await db.execute(sql, vals)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(sql, vals)
            await db.commit()


async def composite_alert_exists(
    ticker: str, signal: str, timeframe: str, within_seconds: int
) -> bool:
    from datetime import datetime, timezone, timedelta
    since = (datetime.now(timezone.utc) - timedelta(seconds=within_seconds)).isoformat()
    sql = (
        "SELECT id FROM composite_alerts "
        "WHERE ticker=? AND signal=? AND timeframe=? AND timestamp >= ? LIMIT 1"
    )
    vals = (ticker, signal, timeframe, since)
    if USE_TURSO:
        async with _turso_conn() as db:
            rows = await db.execute_fetchall(sql, vals)
    else:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            rows = await conn.execute_fetchall(sql, vals)
    return len(rows) > 0


async def insert_composite_alert(alert: dict) -> None:
    extra_keys = {"level_name", "level_price", "poc_level"}
    extra = {k: alert[k] for k in extra_keys if k in alert}
    sql = (
        "INSERT INTO composite_alerts "
        "(ticker, timestamp, signal, direction, tier, ai_confidence, components, suppressed_by, timeframe, extra) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    vals = (
        alert["ticker"], alert["timestamp"], alert["signal"], alert["direction"],
        alert["tier"], alert["ai_confidence"],
        _json.dumps(alert.get("components", [])),
        alert.get("suppressed_by"),
        alert.get("timeframe", "5m"),
        _json.dumps(extra) if extra else None,
    )
    if USE_TURSO:
        async with _turso_conn() as db:
            await db.execute(sql, vals)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(sql, vals)
            await db.commit()


# ── Read helpers ──────────────────────────────────────────────────────────────

async def get_composite_alerts(
    ticker: str | None = None,
    timeframe: str | None = None,
    limit: int = 100,
) -> list[dict]:
    conditions, params = [], []
    if ticker:
        conditions.append("ticker = ?")
        params.append(ticker.upper())
    if timeframe:
        conditions.append("timeframe = ?")
        params.append(timeframe)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)
    sql = f"SELECT * FROM composite_alerts {where} ORDER BY timestamp DESC LIMIT ?"

    if USE_TURSO:
        async with _turso_conn() as db:
            rows = await db.execute_fetchall(sql, params)
    else:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            rows = await conn.execute_fetchall(sql, params)
            rows = [dict(r) for r in rows]

    result = []
    for d in rows:
        try:
            d["components"] = _json.loads(d.get("components") or "[]")
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