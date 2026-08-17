"""SQLite store for rns-alerts: subscriptions + a sent-ledger so a poller restart
never re-blasts an alert already delivered. Self-contained (no external DB)."""
import os
import sqlite3
import threading
import time
from contextlib import contextmanager

DB_PATH = os.environ.get("ALERTS_DB", "/config/app/alerts.db")
_lock = threading.Lock()


@contextmanager
def _db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        with _lock:
            yield conn
            conn.commit()
    finally:
        conn.close()


def init():
    with _db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS subs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lxmf_hex TEXT NOT NULL, lat REAL, lon REAL, place TEXT,
            min_severity TEXT NOT NULL DEFAULT 'Severe', created REAL,
            UNIQUE(lxmf_hex, lat, lon))""")
        c.execute("""CREATE TABLE IF NOT EXISTS sent (
            lxmf_hex TEXT, alert_id TEXT, msg_type TEXT, sent_at REAL,
            PRIMARY KEY (lxmf_hex, alert_id, msg_type))""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sent_ts ON sent(sent_at)")


def add_sub(lxmf_hex, lat, lon, place, min_severity="Severe"):
    with _db() as c:
        c.execute("INSERT OR REPLACE INTO subs (lxmf_hex, lat, lon, place, min_severity, created) "
                  "VALUES (?,?,?,?,?,?)",
                  (lxmf_hex, round(lat, 4), round(lon, 4), place, min_severity, time.time()))


def remove_subs(lxmf_hex):
    with _db() as c:
        cur = c.execute("DELETE FROM subs WHERE lxmf_hex=?", (lxmf_hex,))
        return cur.rowcount


def list_subs(lxmf_hex):
    with _db() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM subs WHERE lxmf_hex=? ORDER BY created", (lxmf_hex,)).fetchall()]


def all_subs():
    with _db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM subs").fetchall()]


def distinct_points():
    """Unique (lat, lon) across all subs -- the poller's work list, so we hit NWS
    once per location no matter how many subscribers share it."""
    with _db() as c:
        return [(r["lat"], r["lon"]) for r in c.execute(
            "SELECT DISTINCT lat, lon FROM subs").fetchall()]


def subs_at(lat, lon):
    with _db() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM subs WHERE lat=? AND lon=?", (round(lat, 4), round(lon, 4))).fetchall()]


def already_sent(lxmf_hex, alert_id, msg_type):
    with _db() as c:
        return c.execute("SELECT 1 FROM sent WHERE lxmf_hex=? AND alert_id=? AND msg_type=?",
                         (lxmf_hex, alert_id, msg_type)).fetchone() is not None


def mark_sent(lxmf_hex, alert_id, msg_type):
    with _db() as c:
        c.execute("INSERT OR IGNORE INTO sent (lxmf_hex, alert_id, msg_type, sent_at) VALUES (?,?,?,?)",
                  (lxmf_hex, alert_id, msg_type, time.time()))


def prune_ledger(max_age_days=14):
    """Drop ledger rows older than max_age_days -- expired alerts won't reappear,
    so their sent-markers are dead weight."""
    with _db() as c:
        c.execute("DELETE FROM sent WHERE sent_at < ?", (time.time() - max_age_days * 86400,))
