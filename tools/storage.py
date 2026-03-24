"""Persistent job & result storage using SQLite."""

import json, sqlite3, threading
from datetime import datetime
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parent / "tradegraph.db"
_local = threading.local()


def _conn() -> sqlite3.Connection:
    """Thread-local SQLite connection."""
    if not hasattr(_local, "conn"):
        _local.conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _init_tables(_local.conn)
    return _local.conn


def _init_tables(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            tickers TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            started_at TEXT,
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            decision TEXT,
            confidence REAL,
            risk_level TEXT,
            summary TEXT,
            details TEXT,
            created_at TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        );
    """)


def save_job(job_id: str, tickers: list[str]):
    c = _conn()
    c.execute("INSERT INTO jobs (id, tickers, status, started_at) VALUES (?, ?, 'running', ?)",
              (job_id, json.dumps(tickers), datetime.now().isoformat()))
    c.commit()


def complete_job(job_id: str):
    c = _conn()
    c.execute("UPDATE jobs SET status='completed', completed_at=? WHERE id=?",
              (datetime.now().isoformat(), job_id))
    c.commit()


def save_result(job_id: str, result: dict):
    c = _conn()
    c.execute(
        "INSERT INTO results (job_id, ticker, decision, confidence, risk_level, summary, details, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (job_id, result.get("ticker"), result.get("decision"), result.get("confidence"),
         result.get("risk_level"), result.get("summary"),
         json.dumps(result.get("details", {}), default=str),
         datetime.now().isoformat()))
    c.commit()


def get_history(limit: int = 50) -> list[dict]:
    """Return recent analysis results."""
    c = _conn()
    rows = c.execute(
        "SELECT r.ticker, r.decision, r.confidence, r.risk_level, r.summary, r.details, r.created_at, r.job_id "
        "FROM results r ORDER BY r.created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_job_results(job_id: str) -> list[dict]:
    c = _conn()
    rows = c.execute(
        "SELECT ticker, decision, confidence, risk_level, summary, details, created_at "
        "FROM results WHERE job_id=? ORDER BY created_at", (job_id,)).fetchall()
    return [dict(r) for r in rows]
