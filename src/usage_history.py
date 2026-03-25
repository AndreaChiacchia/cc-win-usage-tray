"""Historical usage snapshot storage for Claude Usage Tray.

Persists every refresh snapshot to SQLite so the Stats Panel can render
hourly/daily/monthly trend charts.
"""

import re
from datetime import datetime, date

import db


def record_snapshot(email: str, sections: list) -> None:
    """Append a timestamped snapshot for *email* to the DB.

    *sections* is a list of ``UsageSection`` dataclass instances as returned
    by ``usage_parser.parse_usage()``.
    """
    ts = datetime.now().replace(microsecond=0).isoformat()
    rows = [
        (email, ts, s.label, s.percentage, s.spent_info)
        for s in sections
    ]
    if not rows:
        return
    conn = db.get_connection()
    conn.executemany(
        "INSERT INTO usage_snapshots(email, ts, label, pct, spent) VALUES (?,?,?,?,?)",
        rows,
    )
    conn.commit()


def get_history(email: str) -> list:
    """Return the full snapshot list for *email* (oldest first) in legacy dict format."""
    conn = db.get_connection()
    rows = conn.execute(
        "SELECT ts, label, pct, spent FROM usage_snapshots WHERE email=? ORDER BY ts",
        (email,),
    ).fetchall()
    return _rows_to_snapshots(rows)


def get_history_range(email: str, start: datetime, end: datetime) -> list:
    """Return snapshots for *email* whose timestamp falls within [start, end]."""
    conn = db.get_connection()
    rows = conn.execute(
        """SELECT ts, label, pct, spent FROM usage_snapshots
           WHERE email=? AND ts >= ? AND ts <= ? ORDER BY ts""",
        (email, start.isoformat(), end.isoformat()),
    ).fetchall()
    return _rows_to_snapshots(rows)


# ---------------------------------------------------------------------------
# SQL-backed aggregation functions (used by stats_panel)
# ---------------------------------------------------------------------------

def get_hourly_avg(email: str, for_date: date) -> list[int]:
    """24-element list: avg max-pct per clock hour for *for_date*."""
    conn = db.get_connection()
    rows = conn.execute(
        """
        SELECT CAST(strftime('%H', ts) AS INTEGER) AS hour,
               CAST(AVG(max_pct) AS INTEGER)       AS avg_pct
        FROM (
            SELECT ts, MAX(pct) AS max_pct
            FROM usage_snapshots
            WHERE email=? AND DATE(ts)=?
            GROUP BY ts
        )
        GROUP BY hour
        """,
        (email, for_date.isoformat()),
    ).fetchall()
    result = [0] * 24
    for hour, avg_pct in rows:
        if 0 <= hour < 24:
            result[hour] = avg_pct or 0
    return result


def get_daily_avg(email: str, start_date: date, days: int) -> list[int]:
    """*days*-element list: avg max-pct per calendar day starting at *start_date*."""
    from datetime import timedelta
    end_date = start_date + timedelta(days=days - 1)
    conn = db.get_connection()
    rows = conn.execute(
        """
        SELECT DATE(ts) AS day,
               CAST(AVG(max_pct) AS INTEGER) AS avg_pct
        FROM (
            SELECT ts, MAX(pct) AS max_pct
            FROM usage_snapshots
            WHERE email=? AND DATE(ts) >= ? AND DATE(ts) <= ?
            GROUP BY ts
        )
        GROUP BY day
        """,
        (email, start_date.isoformat(), end_date.isoformat()),
    ).fetchall()
    result = [0] * days
    for day_str, avg_pct in rows:
        try:
            day = date.fromisoformat(day_str)
        except Exception:
            continue
        idx = (day - start_date).days
        if 0 <= idx < days:
            result[idx] = avg_pct or 0
    return result


def get_max_extra_spend(email: str, start: datetime, end: datetime) -> str | None:
    """Return the max observed Extra usage spent string in [start, end], e.g. '$3.50 / $5.00'."""
    conn = db.get_connection()
    rows = conn.execute(
        """SELECT spent FROM usage_snapshots
           WHERE email=? AND label='Extra usage'
             AND ts >= ? AND ts <= ? AND spent IS NOT NULL""",
        (email, start.isoformat(), end.isoformat()),
    ).fetchall()
    _dollar_re = re.compile(r'\$([\d.]+)\s*/\s*\$([\d.]+)')
    max_val: float | None = None
    cap_val: float | None = None
    for (spent_str,) in rows:
        m = _dollar_re.search(spent_str)
        if m:
            v, c = float(m.group(1)), float(m.group(2))
            if max_val is None or v > max_val:
                max_val, cap_val = v, c
    if max_val is not None and cap_val is not None:
        return f"${max_val:.2f} / ${cap_val:.2f}"
    return None


def get_peak_hour(email: str) -> int | None:
    """Return the hour (0–23) with the highest average usage across all history."""
    conn = db.get_connection()
    rows = conn.execute(
        """
        SELECT CAST(strftime('%H', ts) AS INTEGER) AS hour,
               AVG(max_pct)                        AS avg_pct
        FROM (
            SELECT ts, MAX(pct) AS max_pct
            FROM usage_snapshots
            WHERE email=?
            GROUP BY ts
        )
        GROUP BY hour
        """,
        (email,),
    ).fetchall()
    if not rows:
        return None
    best_hour, best_avg = max(rows, key=lambda r: r[1] or 0)
    return best_hour if (best_avg or 0) > 0 else None


def get_avg_daily_max(email: str) -> float | None:
    """Return the average of per-day peak usage percentages across all history."""
    conn = db.get_connection()
    rows = conn.execute(
        """
        SELECT AVG(daily_max) FROM (
            SELECT DATE(ts) AS day, MAX(pct) AS daily_max
            FROM usage_snapshots
            WHERE email=?
            GROUP BY day
        )
        """,
        (email,),
    ).fetchone()
    if rows and rows[0] is not None:
        return float(rows[0])
    return None


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _rows_to_snapshots(rows) -> list:
    """Convert flat DB rows → legacy list-of-dicts snapshot format."""
    snapshots: dict[str, dict] = {}
    order: list[str] = []
    for ts, label, pct, spent in rows:
        if ts not in snapshots:
            snapshots[ts] = {"ts": ts, "sections": {}}
            order.append(ts)
        snapshots[ts]["sections"][label] = {"pct": pct, "spent": spent}
    return [snapshots[ts] for ts in order]
