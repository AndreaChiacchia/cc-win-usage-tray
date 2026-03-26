"""Token history — scans Claude JSONL session files and stores per-message token data.

Scans ~/.claude/projects/**/*.jsonl for assistant messages, extracts token usage,
and stores results in the token_entries table. Uses jsonl_processed to skip
files that haven't changed since the last scan.
"""

import json
import os
import threading
from datetime import date, datetime, timedelta, timezone

import db
from config import CLAUDE_DATA_DIR

# Concurrency guard — prevents overlapping scan threads
_scan_lock = threading.Lock()


def scan_incremental(email: str) -> None:
    """Start an incremental background scan. Returns immediately (non-blocking).

    If a scan is already running, this call is a no-op.
    If email is empty, the scan is skipped (data cannot be attributed).
    """
    if not email:
        return
    if not _scan_lock.acquire(blocking=False):
        return  # scan already in progress — skip
    threading.Thread(target=_guarded_scan, args=(email,), daemon=True, name="token-history-scan").start()


def scan_blocking(email: str) -> None:
    """Run an incremental scan synchronously, blocking until complete. Thread-safe.

    If email is empty, the scan is skipped.
    """
    if not email:
        return
    with _scan_lock:
        _do_scan(email)


def _guarded_scan(email: str) -> None:
    try:
        _do_scan(email)
    finally:
        _scan_lock.release()


def _do_scan(email: str) -> None:
    try:
        conn = db.get_connection()
        base = os.path.expanduser(CLAUDE_DATA_DIR)
        projects_dir = os.path.join(base, "projects")
        if not os.path.isdir(projects_dir):
            return

        for root, _dirs, files in os.walk(projects_dir):
            for fname in files:
                if fname.endswith(".jsonl"):
                    _process_file(conn, os.path.join(root, fname), email)
    except Exception as e:
        print(f"[token_history] scan error: {e}")


def _process_file(conn, fpath: str, email: str) -> None:
    try:
        stat = os.stat(fpath)
        mtime = stat.st_mtime
        size = stat.st_size

        row = conn.execute(
            "SELECT mtime, file_size, last_offset, email FROM jsonl_processed WHERE path=?", (fpath,)
        ).fetchone()

        if row:
            prev_mtime, prev_size, prev_offset, prev_email = row[0], row[1], row[2] or 0, row[3] or ""
            if prev_mtime == mtime and prev_size == size and prev_offset >= size:
                return  # unchanged and fully processed — skip
        else:
            prev_size = 0
            prev_offset = 0
            prev_email = ""

        if size >= prev_size:
            # File grew or is new — seek to last good offset and parse only new lines
            start_offset = prev_offset
        else:
            # File was truncated/rewritten — skip if owned by a different account
            if prev_email and prev_email != email:
                return  # file belongs to a different account — skip
            conn.execute("DELETE FROM token_entries WHERE source_file=?", (fpath,))
            start_offset = 0

        rows = []
        new_offset = start_offset

        with open(fpath, "rb") as f:
            f.seek(start_offset)
            while True:
                line_bytes = f.readline()
                if not line_bytes:
                    break
                # Incomplete line at end of file — stop; pick it up next scan
                if not line_bytes.endswith(b"\n"):
                    break
                new_offset = f.tell()
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "assistant":
                    continue
                ts = obj.get("timestamp", "")
                if not ts:
                    continue
                if ts.endswith("Z"):
                    try:
                        utc_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        ts = utc_dt.astimezone().replace(tzinfo=None).isoformat(timespec="milliseconds")
                    except ValueError:
                        pass
                usage = obj.get("message", {}).get("usage") or {}
                if not usage:
                    continue
                rows.append((
                    ts,
                    int(usage.get("input_tokens") or 0),
                    int(usage.get("output_tokens") or 0),
                    int(usage.get("cache_read_input_tokens") or 0),
                    int(usage.get("cache_creation_input_tokens") or 0),
                    fpath,
                    email,
                ))

        if rows:
            conn.executemany(
                """INSERT INTO token_entries
                   (ts, input_tokens, output_tokens, cache_read_tokens,
                    cache_creation_tokens, source_file, email)
                   VALUES (?,?,?,?,?,?,?)""",
                rows,
            )

        conn.execute(
            """INSERT OR REPLACE INTO jsonl_processed(path, mtime, file_size, last_offset, email)
               VALUES (?,?,?,?,?)""",
            (fpath, mtime, size, new_offset, email),
        )
        conn.commit()
    except Exception as e:
        print(f"[token_history] error processing {fpath}: {e}")


def get_hourly_tokens(target_date: date, email: str) -> list[dict]:
    """Return a list of 24 dicts (one per hour) with summed token counts.

    Each dict: {input, output, cache_read, cache_creation}
    """
    conn = db.get_connection()
    date_str = target_date.strftime("%Y-%m-%d")
    rows = conn.execute(
        """SELECT
               CAST(strftime('%H', ts) AS INTEGER) AS hour,
               SUM(input_tokens),
               SUM(output_tokens),
               SUM(cache_read_tokens),
               SUM(cache_creation_tokens)
           FROM token_entries
           WHERE ts >= ? AND ts < ? AND email = ?
           GROUP BY hour""",
        (f"{date_str}T00:00:00", f"{date_str}T23:59:59.999", email),
    ).fetchall()

    result = [_empty() for _ in range(24)]
    for hour, inp, out, cr, cc in rows:
        if 0 <= hour < 24:
            result[hour] = {
                "input": inp or 0,
                "output": out or 0,
                "cache_read": cr or 0,
                "cache_creation": cc or 0,
            }
    return result


def get_daily_tokens(start_date: date, days: int, email: str) -> list[dict]:
    """Return a list of `days` dicts (one per day from start_date) with summed token counts."""
    conn = db.get_connection()
    end_date = start_date + timedelta(days=days)
    rows = conn.execute(
        """SELECT
               strftime('%Y-%m-%d', ts) AS day,
               SUM(input_tokens),
               SUM(output_tokens),
               SUM(cache_read_tokens),
               SUM(cache_creation_tokens)
           FROM token_entries
           WHERE ts >= ? AND ts < ? AND email = ?
           GROUP BY day""",
        (start_date.isoformat(), end_date.isoformat(), email),
    ).fetchall()

    day_map: dict[str, dict] = {}
    for day, inp, out, cr, cc in rows:
        day_map[day] = {
            "input": inp or 0,
            "output": out or 0,
            "cache_read": cr or 0,
            "cache_creation": cc or 0,
        }

    return [
        day_map.get((start_date + timedelta(days=i)).isoformat(), _empty())
        for i in range(days)
    ]


def _empty() -> dict:
    return {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
