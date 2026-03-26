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

CREATE TABLE IF NOT EXISTS token_entries (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                  TEXT    NOT NULL,
    input_tokens        INTEGER DEFAULT 0,
    output_tokens       INTEGER DEFAULT 0,
    cache_read_tokens   INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    source_file         TEXT    NOT NULL,
    email               TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_token_entries_ts ON token_entries(ts);

CREATE TABLE IF NOT EXISTS jsonl_processed (
    path        TEXT PRIMARY KEY,
    mtime       REAL NOT NULL,
    file_size   INTEGER NOT NULL,
    last_offset INTEGER NOT NULL DEFAULT 0,
    email       TEXT NOT NULL DEFAULT ''
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

    _apply_migrations(conn)

    return conn


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply incremental schema migrations. Safe to call on every open."""
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    version = int(row[0]) if row else 0

    if version < 2:
        # v1→v2: token_entries and jsonl_processed tables (created by _SCHEMA above via IF NOT EXISTS)
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', '2')")
        conn.commit()

    if version < 3:
        # v2→v3: add last_offset column to jsonl_processed for append-only seek
        try:
            conn.execute("ALTER TABLE jsonl_processed ADD COLUMN last_offset INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass  # column already exists (new DB created from updated _SCHEMA)
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', '3')")
        conn.commit()

    if version < 4:
        # v3→v4: add email column to token_entries for per-account filtering;
        # clear all existing untagged rows and reset scan state so files are re-processed
        # with the correct email at next startup scan.
        try:
            conn.execute("ALTER TABLE token_entries ADD COLUMN email TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass  # column already exists on newly-created DBs
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_token_entries_email ON token_entries(email)")
        except Exception:
            pass
        conn.execute("DELETE FROM token_entries")
        conn.execute("DELETE FROM jsonl_processed")
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', '4')")
        conn.commit()

    if version < 5:
        try:
            conn.execute("ALTER TABLE jsonl_processed ADD COLUMN email TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass  # column already exists on newly-created DBs
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', '5')")
        conn.commit()

    # One-time fix: clear token_entries stored with UTC timestamps (pre-timezone-fix).
    # jsonl_processed is kept intact so old files are not re-scanned (they have no account
    # identifier and would be attributed to the current account incorrectly).
    if not conn.execute("SELECT 1 FROM meta WHERE key='token_tz_migrated'").fetchone():
        conn.execute("DELETE FROM token_entries")
        conn.execute("INSERT INTO meta(key, value) VALUES('token_tz_migrated', '1')")
        conn.commit()


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
