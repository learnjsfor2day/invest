"""SQLite schema + CRUD. Numeric fields are real numbers (USD millions for $).

Schema design choices:
- earnings table: one row per (ticker, fiscal_period). UNIQUE constraint.
- INSERT OR REPLACE on earnings only when explicitly re-importing; otherwise
  use insert_or_update_earnings() which preserves history via runs/last_updated.
- All money columns are floats in the report's native currency, with currency col.
- Percentages stored as decimals (0.22 = +22%).
"""
from __future__ import annotations
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from .config import DB_PATH, DATA_DIR

SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS companies (
    ticker TEXT PRIMARY KEY,
    name_en TEXT,
    name_zh TEXT,
    country TEXT,
    exchange TEXT,
    listed INTEGER NOT NULL DEFAULT 1,
    us_tradable INTEGER NOT NULL DEFAULT 0,
    cik TEXT,
    alt_tickers_json TEXT DEFAULT '[]',
    tags_json TEXT DEFAULT '[]',
    chains_json TEXT DEFAULT '[]',
    notes TEXT,
    added_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS earnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL REFERENCES companies(ticker) ON UPDATE CASCADE,
    fiscal_period TEXT NOT NULL,
    report_date TEXT,
    currency TEXT DEFAULT 'USD',
    -- core financials (millions in `currency`)
    revenue REAL,
    revenue_yoy REAL,
    revenue_qoq REAL,
    gross_margin REAL,
    operating_margin REAL,
    operating_income REAL,
    net_income REAL,
    eps REAL,
    -- AI-specific (numeric where disclosed; NULL otherwise)
    cloud_revenue REAL,
    cloud_revenue_yoy REAL,
    ai_arr REAL,
    ai_arr_yoy REAL,
    backlog_rpo REAL,
    backlog_rpo_qoq REAL,
    capex_quarter REAL,
    capex_full_year_low REAL,
    capex_full_year_high REAL,
    -- text / meta
    guidance_text TEXT,
    source_url TEXT,
    transcript_url TEXT,
    notes TEXT,
    last_updated TEXT DEFAULT (datetime('now')),
    UNIQUE(ticker, fiscal_period)
);

CREATE INDEX IF NOT EXISTS idx_earnings_ticker_date ON earnings(ticker, report_date DESC);

CREATE TABLE IF NOT EXISTS quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    fiscal_period TEXT NOT NULL,
    quote TEXT NOT NULL,
    speaker TEXT,
    topic TEXT,  -- ai_demand|capex|capacity|model|supply|guidance|other
    source_url TEXT,
    extracted_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_quotes_ticker_period ON quotes(ticker, fiscal_period);

CREATE TABLE IF NOT EXISTS tiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    fiscal_period TEXT,
    tier INTEGER NOT NULL,  -- 1|2|3|4
    rule_matches_json TEXT DEFAULT '[]',
    reason TEXT,
    classified_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tiers_ticker ON tiers(ticker, classified_at DESC);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT,
    cik TEXT,
    form_type TEXT,
    filing_date TEXT,
    accession TEXT UNIQUE,
    title TEXT,
    url TEXT,
    seen_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT DEFAULT (datetime('now')),
    finished_at TEXT,
    tickers_checked_json TEXT,
    earnings_added INTEGER DEFAULT 0,
    alerts_seen INTEGER DEFAULT 0,
    quotes_extracted INTEGER DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    signal_type TEXT NOT NULL,   -- vol_spike|rs_top|squeeze_break|high_52w|iv_anomaly
    trade_date TEXT NOT NULL,    -- YYYY-MM-DD
    score REAL,                  -- normalized strength (higher = stronger)
    raw_json TEXT,               -- raw values for debugging / future backtest
    detected_at TEXT DEFAULT (datetime('now')),
    UNIQUE(ticker, signal_type, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(trade_date DESC, ticker);
CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker, trade_date DESC);
"""


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------- companies ----------
def upsert_company(row: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO companies (ticker, name_en, name_zh, country, exchange,
                listed, us_tradable, cik, alt_tickers_json, tags_json, chains_json, notes)
            VALUES (:ticker, :name_en, :name_zh, :country, :exchange,
                :listed, :us_tradable, :cik, :alt_tickers_json, :tags_json, :chains_json, :notes)
            ON CONFLICT(ticker) DO UPDATE SET
                name_en=excluded.name_en, name_zh=excluded.name_zh,
                country=excluded.country, exchange=excluded.exchange,
                listed=excluded.listed, us_tradable=excluded.us_tradable,
                cik=COALESCE(excluded.cik, companies.cik),
                alt_tickers_json=excluded.alt_tickers_json,
                tags_json=excluded.tags_json, chains_json=excluded.chains_json,
                notes=excluded.notes
            """,
            {
                "ticker": row["ticker"],
                "name_en": row.get("name_en"),
                "name_zh": row.get("name_zh"),
                "country": row.get("country"),
                "exchange": row.get("exchange"),
                "listed": int(bool(row.get("listed", True))),
                "us_tradable": int(bool(row.get("us_tradable", False))),
                "cik": row.get("cik"),
                "alt_tickers_json": json.dumps(row.get("alt_tickers", [])),
                "tags_json": json.dumps(row.get("tags", [])),
                "chains_json": json.dumps(row.get("chains", [])),
                "notes": row.get("notes"),
            },
        )


def list_companies(us_tradable_only: bool = False, limit: Optional[int] = None) -> list[sqlite3.Row]:
    sql = "SELECT * FROM companies"
    params: list = []
    if us_tradable_only:
        sql += " WHERE us_tradable = 1"
    sql += " ORDER BY ticker"
    if limit:
        sql += f" LIMIT {int(limit)}"
    with connect() as conn:
        return list(conn.execute(sql, params))


# ---------- earnings ----------
EARNINGS_FIELDS = (
    "ticker fiscal_period report_date currency revenue revenue_yoy revenue_qoq "
    "gross_margin operating_margin operating_income net_income eps "
    "cloud_revenue cloud_revenue_yoy ai_arr ai_arr_yoy "
    "backlog_rpo backlog_rpo_qoq capex_quarter capex_full_year_low capex_full_year_high "
    "guidance_text source_url transcript_url notes"
).split()


def upsert_earnings(row: dict[str, Any]) -> int:
    """Insert or update earnings row. Returns 1 if inserted, 0 if updated."""
    cols = ",".join(EARNINGS_FIELDS)
    placeholders = ",".join(f":{f}" for f in EARNINGS_FIELDS)
    update_set = ",".join(f"{f}=excluded.{f}" for f in EARNINGS_FIELDS if f not in ("ticker", "fiscal_period"))
    sql = f"""
        INSERT INTO earnings ({cols}, last_updated)
        VALUES ({placeholders}, datetime('now'))
        ON CONFLICT(ticker, fiscal_period) DO UPDATE SET
            {update_set}, last_updated=datetime('now')
        RETURNING (SELECT COUNT(*) FROM earnings WHERE ticker=:ticker AND fiscal_period=:fiscal_period) AS existed
    """
    payload = {f: row.get(f) for f in EARNINGS_FIELDS}
    with connect() as conn:
        before = conn.execute(
            "SELECT 1 FROM earnings WHERE ticker=? AND fiscal_period=?",
            (payload["ticker"], payload["fiscal_period"]),
        ).fetchone()
        conn.execute(
            f"INSERT INTO earnings ({cols}, last_updated) VALUES ({placeholders}, datetime('now'))"
            f" ON CONFLICT(ticker, fiscal_period) DO UPDATE SET {update_set}, last_updated=datetime('now')",
            payload,
        )
        return 0 if before else 1


def latest_earnings(ticker: str) -> Optional[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM earnings WHERE ticker=? ORDER BY report_date DESC, id DESC LIMIT 1",
            (ticker,),
        ).fetchone()


def previous_earnings(ticker: str, before_period: str) -> Optional[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM earnings WHERE ticker=? AND fiscal_period<? ORDER BY fiscal_period DESC LIMIT 1",
            (ticker, before_period),
        ).fetchone()


# ---------- quotes ----------
def add_quote(ticker: str, fiscal_period: str, quote: str,
              speaker: str = "", topic: str = "other", source_url: str = "") -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO quotes (ticker, fiscal_period, quote, speaker, topic, source_url)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (ticker, fiscal_period, quote, speaker, topic, source_url),
        )


def get_quotes(ticker: str, fiscal_period: Optional[str] = None) -> list[sqlite3.Row]:
    sql = "SELECT * FROM quotes WHERE ticker=?"
    params: list = [ticker]
    if fiscal_period:
        sql += " AND fiscal_period=?"
        params.append(fiscal_period)
    sql += " ORDER BY id DESC"
    with connect() as conn:
        return list(conn.execute(sql, params))


# ---------- tiers ----------
def record_tier(ticker: str, fiscal_period: str, tier: int,
                rule_matches: list[str], reason: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO tiers (ticker, fiscal_period, tier, rule_matches_json, reason)"
            " VALUES (?, ?, ?, ?, ?)",
            (ticker, fiscal_period, tier, json.dumps(rule_matches), reason),
        )


def latest_tiers() -> list[sqlite3.Row]:
    with connect() as conn:
        return list(conn.execute("""
            SELECT t.* FROM tiers t
            JOIN (
                SELECT ticker, MAX(classified_at) AS mx FROM tiers GROUP BY ticker
            ) m ON m.ticker=t.ticker AND m.mx=t.classified_at
            ORDER BY t.tier, t.ticker
        """))


# ---------- alerts ----------
def record_alert(*, ticker: Optional[str], cik: Optional[str], form_type: str,
                 filing_date: str, accession: str, title: str, url: str) -> bool:
    """Returns True if a new alert was inserted (False if already seen)."""
    with connect() as conn:
        try:
            conn.execute(
                "INSERT INTO alerts (ticker, cik, form_type, filing_date, accession, title, url)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ticker, cik, form_type, filing_date, accession, title, url),
            )
            return True
        except sqlite3.IntegrityError:
            return False


# ---------- runs ----------
def start_run() -> int:
    with connect() as conn:
        cur = conn.execute("INSERT INTO runs DEFAULT VALUES")
        return cur.lastrowid


def finish_run(run_id: int, *, tickers: Iterable[str], earnings_added: int,
               alerts_seen: int, quotes_extracted: int, notes: str = "") -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE runs SET finished_at=datetime('now'), tickers_checked_json=?,"
            " earnings_added=?, alerts_seen=?, quotes_extracted=?, notes=? WHERE id=?",
            (json.dumps(list(tickers)), earnings_added, alerts_seen, quotes_extracted, notes, run_id),
        )


# ---------- signals (price/volume anomalies) ----------
def record_signal(ticker: str, signal_type: str, trade_date: str,
                  score: float, raw: dict[str, Any]) -> bool:
    """Insert a signal hit. Returns True if newly inserted, False if dup."""
    with connect() as conn:
        try:
            conn.execute(
                "INSERT INTO signals (ticker, signal_type, trade_date, score, raw_json)"
                " VALUES (?, ?, ?, ?, ?)",
                (ticker, signal_type, trade_date, float(score), json.dumps(raw)),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def signals_on(trade_date: str) -> list[sqlite3.Row]:
    with connect() as conn:
        return list(conn.execute(
            "SELECT * FROM signals WHERE trade_date=? ORDER BY score DESC, ticker",
            (trade_date,),
        ))


def signals_for_ticker(ticker: str, days: int = 30) -> list[sqlite3.Row]:
    with connect() as conn:
        return list(conn.execute(
            "SELECT * FROM signals WHERE ticker=?"
            " AND trade_date >= date('now', ?) ORDER BY trade_date DESC",
            (ticker, f"-{int(days)} days"),
        ))
