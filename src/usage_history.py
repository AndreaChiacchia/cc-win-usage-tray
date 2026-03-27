"""Historical usage snapshot storage for Claude Usage Tray.

Persists every refresh snapshot to SQLite so the Stats Panel can render
hourly/daily/monthly trend charts.
"""

import re
from datetime import datetime, date

import db

_DOLLAR_RE = re.compile(r'\$([\d.]+)\s*/\s*\$([\d.]+)')


def _parse_spend(s: str) -> tuple[float, float] | None:
    m = _DOLLAR_RE.search(s)
    return (float(m.group(1)), float(m.group(2))) if m else None


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
        [email, for_date.isoformat()],
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
        [email, start_date.isoformat(), end_date.isoformat()],
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


def get_hourly_delta(email: str, for_date: date, label: str) -> list[int]:
    """24-element list: pct delta per clock hour for *for_date* and *label*.

    Per hour: delta = last_pct - first_pct. If negative (counter reset), use last_pct.
    """
    conn = db.get_connection()
    rows = conn.execute(
        """
        SELECT CAST(strftime('%H', ts) AS INTEGER) AS hour, pct
        FROM usage_snapshots
        WHERE email=? AND DATE(ts)=? AND label=?
        ORDER BY ts
        """,
        [email, for_date.isoformat(), label],
    ).fetchall()
    buckets: dict[int, list[int]] = {}
    for hour, pct in rows:
        if 0 <= hour < 24:
            buckets.setdefault(hour, []).append(pct)
    result = [0] * 24
    for hour, values in buckets.items():
        delta = values[-1] - values[0]
        result[hour] = values[-1] if delta < 0 else delta
    return result


def get_daily_delta(email: str, start_date: date, days: int, label: str) -> list[int]:
    """*days*-element list: pct delta per calendar day starting at *start_date* for *label*.

    Per day: delta = last_pct - first_pct. If negative (counter reset), use last_pct.
    """
    from datetime import timedelta
    end_date = start_date + timedelta(days=days - 1)
    conn = db.get_connection()
    rows = conn.execute(
        """
        SELECT DATE(ts) AS day, pct
        FROM usage_snapshots
        WHERE email=? AND DATE(ts) >= ? AND DATE(ts) <= ? AND label=?
        ORDER BY ts
        """,
        [email, start_date.isoformat(), end_date.isoformat(), label],
    ).fetchall()
    buckets: dict[str, list[int]] = {}
    for day_str, pct in rows:
        buckets.setdefault(day_str, []).append(pct)
    result = [0] * days
    for day_str, values in buckets.items():
        try:
            day = date.fromisoformat(day_str)
        except Exception:
            continue
        idx = (day - start_date).days
        if 0 <= idx < days:
            delta = values[-1] - values[0]
            result[idx] = values[-1] if delta < 0 else delta
    return result


def get_extra_spend_current(email: str, start: datetime, end: datetime) -> str | None:
    """Return the latest Extra usage spent amount in [start, end], e.g. '$3.50'.

    Used for 'This Month' where the cumulative total IS the monthly spend.
    """
    conn = db.get_connection()
    rows = conn.execute(
        """SELECT spent FROM usage_snapshots
           WHERE email=? AND label='Extra usage'
             AND ts >= ? AND ts <= ? AND spent IS NOT NULL
           ORDER BY ts DESC LIMIT 1""",
        (email, start.isoformat(), end.isoformat()),
    ).fetchall()
    if not rows:
        return None
    parsed = _parse_spend(rows[0][0])
    if parsed is None:
        return None
    return f"${parsed[0]:.2f}"


def get_extra_spend_delta(email: str, start: datetime, end: datetime) -> str | None:
    """Return the Extra usage spend delta (end - start) in [start, end], e.g. '$1.20'.

    Used for 'Today' and 'This Week' to show incremental spend over the period.
    If the billing period reset mid-range (value drops), the last value is used directly.
    Returns None when there is no spend or the delta is zero.
    """
    conn = db.get_connection()

    # Baseline: latest snapshot strictly before start
    baseline_row = conn.execute(
        """SELECT spent FROM usage_snapshots
           WHERE email=? AND label='Extra usage'
             AND ts < ? AND spent IS NOT NULL
           ORDER BY ts DESC LIMIT 1""",
        (email, start.isoformat()),
    ).fetchone()

    # In-range snapshots ordered by time
    in_range = conn.execute(
        """SELECT spent FROM usage_snapshots
           WHERE email=? AND label='Extra usage'
             AND ts >= ? AND ts <= ? AND spent IS NOT NULL
           ORDER BY ts""",
        (email, start.isoformat(), end.isoformat()),
    ).fetchall()

    if not in_range:
        return None

    # Parse first and last in-range values
    first_parsed = None
    last_parsed = None
    for (spent_str,) in in_range:
        p = _parse_spend(spent_str)
        if p is not None:
            if first_parsed is None:
                first_parsed = p
            last_parsed = p

    if last_parsed is None:
        return None

    last_val = last_parsed[0]

    # Determine baseline value
    if baseline_row is not None:
        b = _parse_spend(baseline_row[0])
        baseline_val = b[0] if b else (first_parsed[0] if first_parsed else 0.0)
    else:
        baseline_val = first_parsed[0] if first_parsed else 0.0

    delta = last_val - baseline_val

    # Billing reset mid-period: value dropped below baseline
    if delta < 0:
        delta = last_val

    if delta <= 0:
        return None

    return f"${delta:.2f}"


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
