"""
store.py — WhaleWatch SQLite scan store

Stores pre-computed sector scans so the app reads instant pre-computed results
instead of crunching on demand. Self-overwriting: each sector's scan replaces
the previous one for that sector (delete-on-refresh design).

Pure stdlib (sqlite3) — no install, no running service, ~3MB total footprint.
Graduate to Postgres later when flow-history retention / backtester volume needs it.
"""
import sqlite3
import json
import os
from datetime import datetime, timezone

DB_PATH = os.environ.get("WHALEWATCH_DB", "/opt/whalewatch/app/whalewatch.db")


def _conn():
    # check_same_thread=False so the scan job and the API can both touch it.
    # WAL mode lets a reader (the app) and a writer (the scan job) coexist.
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    c.execute("PRAGMA journal_mode=WAL;")
    c.row_factory = sqlite3.Row
    return c


def init_db():
    """Create the table if it doesn't exist. Safe to call on every startup."""
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS scan_results (
                sector       TEXT NOT NULL,
                batch_index  INTEGER NOT NULL,
                scanned_at   TEXT NOT NULL,
                payload      TEXT NOT NULL,
                PRIMARY KEY (sector)
            )
        """)
        c.commit()


def save_sector(sector, batch_index, results):
    """
    Store (or overwrite) the scan for one sector.
    `results` is the list of analysed ticker dicts. Self-overwriting via REPLACE
    on the sector primary key — yesterday's scan for this sector is gone.
    """
    scanned_at = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(results)
    with _conn() as c:
        c.execute(
            "REPLACE INTO scan_results (sector, batch_index, scanned_at, payload) "
            "VALUES (?, ?, ?, ?)",
            (sector, batch_index, scanned_at, payload),
        )
        c.commit()
    return scanned_at


def get_sector(sector):
    """Return the latest stored scan for one sector, or None if never scanned."""
    with _conn() as c:
        row = c.execute(
            "SELECT sector, batch_index, scanned_at, payload "
            "FROM scan_results WHERE sector = ?",
            (sector,),
        ).fetchone()
    if not row:
        return None
    return {
        "sector": row["sector"],
        "batch_index": row["batch_index"],
        "scanned_at": row["scanned_at"],
        "results": json.loads(row["payload"]),
    }


def get_all_meta():
    """
    Lightweight overview: which sectors are stored and when each was last scanned.
    Does NOT load the full payloads — just timestamps. For a freshness dashboard.
    """
    with _conn() as c:
        rows = c.execute(
            "SELECT sector, batch_index, scanned_at FROM scan_results "
            "ORDER BY batch_index"
        ).fetchall()
    return [
        {"sector": r["sector"], "batch_index": r["batch_index"], "scanned_at": r["scanned_at"]}
        for r in rows
    ]


def clear_all():
    """Wipe everything. For a manual full reset."""
    with _conn() as c:
        c.execute("DELETE FROM scan_results")
        c.commit()
