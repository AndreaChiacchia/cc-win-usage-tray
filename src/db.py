"""SQLite connection manager for Claude Usage Tray.

Single WAL-mode connection shared across threads (sqlite3 serialized mode).
Handles schema creation and one-time migration from legacy JSON files.
"""

import json
import os
import sqlite3
from datetime import datetime

from paths import DB_FILE, HISTORY_FILE, STORAGE_FILE

_conn: sqlite3.Connection | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_snapshots (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT    NOT NULL,
    ts    TEXT    NOT NULL,
    label TEXT    NOT NULL,
    pct   INTEGER NOT NULL,
    spent TEXT
);
CREATE INDEX IF NOT EXISTS idx_snapshots_email_ts ON usage_snapshots(email, ts);

CREATE TABLE IF NOT EXISTS accounts (
    email        TEXT PRIMARY KEY,
    last_updated TEXT NOT NULL,
    is_active    INTEGER NOT NULL DEFAULT 0,
    raw_text     TEXT,
    error        TEXT
);

CREATE TABLE IF NOT EXISTS account_sections (
    email      TEXT    NOT NULL,
    label      TEXT    NOT NULL,
    percentage INTEGER NOT NULL,
    reset_info TEXT    NOT NULL DEFAULT '',
    spent_info TEXT,
    PRIMARY KEY (email, label),
    FOREIGN KEY (email) REFERENCES accounts(email) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def get_connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _open()
    return _conn


def _open() -> sqlite3.Connection:
    is_new = not os.path.exists(DB_FILE)
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    for statement in _SCHEMA.strip().split(";"):
        s = statement.strip()
        if s:
            conn.execute(s)
    conn.commit()

    if is_new:
        _migrate_from_json(conn)

    return conn


def _migrate_from_json(conn: sqlite3.Connection) -> None:
    """Bulk-import existing JSON history and accounts into SQLite on first run."""
    _migrate_history(conn)
    _migrate_accounts(conn)

    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', '1')")
    conn.commit()

    # Rename JSON files to .bak as a safety net
    for path in (HISTORY_FILE, STORAGE_FILE):
        if os.path.exists(path):
            try:
                os.rename(path, path + ".bak")
            except Exception:
                pass


def _migrate_history(conn: sqlite3.Connection) -> None:
    if not os.path.exists(HISTORY_FILE):
        return
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data: dict = json.load(f)
    except Exception as e:
        print(f"[db] history migration load error: {e}")
        return

    rows = []
    for email, snapshots in data.items():
        for snap in snapshots:
            ts = snap.get("ts", "")
            for label, sec in snap.get("sections", {}).items():
                rows.append((
                    email,
                    ts,
                    label,
                    sec.get("pct", 0),
                    sec.get("spent"),
                ))

    if rows:
        conn.executemany(
            "INSERT INTO usage_snapshots(email, ts, label, pct, spent) VALUES (?,?,?,?,?)",
            rows,
        )
        conn.commit()
        print(f"[db] migrated {len(rows)} snapshot rows from JSON")


def _migrate_accounts(conn: sqlite3.Connection) -> None:
    if not os.path.exists(STORAGE_FILE):
        return
    try:
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            data: dict = json.load(f)
    except Exception as e:
        print(f"[db] accounts migration load error: {e}")
        return

    for email, acc in data.items():
        usage = acc.get("usage", {})
        conn.execute(
            """INSERT OR REPLACE INTO accounts(email, last_updated, is_active, raw_text, error)
               VALUES (?,?,?,?,?)""",
            (
                email,
                acc.get("last_updated", datetime.now().isoformat()),
                1 if acc.get("is_active") else 0,
                usage.get("raw_text", ""),
                usage.get("error"),
            ),
        )
        for sec in usage.get("sections", []):
            conn.execute(
                """INSERT OR REPLACE INTO account_sections(email, label, percentage, reset_info, spent_info)
                   VALUES (?,?,?,?,?)""",
                (
                    email,
                    sec.get("label", ""),
                    sec.get("percentage", 0),
                    sec.get("reset_info", ""),
                    sec.get("spent_info"),
                ),
            )
    conn.commit()
    print(f"[db] migrated {len(data)} accounts from JSON")
