"""Relative time formatting utilities for Claude Usage Tray."""

import re
from datetime import datetime, date, timedelta


def is_peak_time(start_local: int, end_local: int) -> bool:
    """Return True if the current local hour is within the peak window."""
    if start_local == end_local:
        return False
    hour = datetime.now().hour
    if start_local < end_local:
        return start_local <= hour < end_local
    # midnight wrap
    return hour >= start_local or hour < end_local


def peak_local_hours(start_local: int, end_local: int) -> set:
    """Return the set of local hours (0-23) that fall within the peak window."""
    if start_local == end_local:
        return set()
    if start_local < end_local:
        return set(range(start_local, end_local))
    # midnight wrap
    return set(range(start_local, 24)) | set(range(0, end_local))


def format_last_sync_relative(iso_timestamp: str) -> str:
    """Return a human-readable relative sync time, e.g. 'Synced 5 min ago'."""
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        now = datetime.now()
        delta = now - dt
        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            total_seconds = 0

        if total_seconds < 60:
            return "Synced just now"

        total_minutes = total_seconds // 60
        if total_minutes < 60:
            return f"Synced {total_minutes} min ago"

        total_hours = total_minutes // 60
        remaining_minutes = total_minutes % 60
        if total_hours < 24:
            if remaining_minutes == 0:
                return f"Synced {total_hours} hours ago"
            return f"Synced {total_hours} hours {remaining_minutes} min ago"

        total_days = total_hours // 24
        remaining_hours = total_hours % 24
        if remaining_hours == 0:
            return f"Synced {total_days} days ago"
        return f"Synced {total_days} days {remaining_hours} hours ago"
    except Exception:
        return iso_timestamp


def parse_reset_datetime(reset_info: str, reference: "datetime | None" = None) -> "datetime | None":
    """Parse a reset_info string into a datetime. Returns None if unparseable.

    If ``reference`` is provided, relative times ("9am", "tomorrow 9am") are
    resolved against it instead of the current wall-clock time.  This is used
    when evaluating data that was captured in the past so that a reset time
    that has already passed is correctly identified as past.
    """
    try:
        tz_match = re.search(r'\(([^)]+)\)', reset_info)
        tz_annotation = tz_match.group(0) if tz_match else ""

        clean = reset_info
        if tz_annotation:
            clean = clean.replace(tz_annotation, "").strip()

        parts = clean.split(None, 1)
        if len(parts) < 2:
            return None
        time_str = parts[1].strip()

        return _parse_reset_time(time_str, ref_dt=reference)
    except Exception:
        return None


def format_reset_relative(reset_info: str) -> str:
    """Return a human-readable relative reset time, e.g. 'Resets in 3 hours'.

    Falls back to the original reset_info string if parsing fails.
    """
    try:
        # Extract optional timezone annotation like (Europe/Rome)
        tz_match = re.search(r'\(([^)]+)\)', reset_info)
        tz_annotation = tz_match.group(0) if tz_match else ""

        # Strip the tz annotation for parsing
        clean = reset_info
        if tz_annotation:
            clean = clean.replace(tz_annotation, "").strip()

        # Extract the prefix verb (first word, e.g. "Resets") and the time portion
        parts = clean.split(None, 1)
        if len(parts) < 2:
            return reset_info
        prefix = parts[0]  # e.g. "Resets"
        time_str = parts[1].strip()

        parsed_dt = _parse_reset_time(time_str)
        if parsed_dt is None:
            return reset_info

        now = datetime.now()
        delta = parsed_dt - now
        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            return reset_info

        result = _format_delta_forward(total_seconds)

        if tz_annotation:
            result = f"{result} {tz_annotation}"
        return result
    except Exception:
        return reset_info


def _parse_reset_time(time_str: str, ref_dt: "datetime | None" = None) -> "datetime | None":
    """Parse various time formats into a datetime. Returns None on failure."""
    now = ref_dt or datetime.now()
    today = now.date()

    # Normalize: collapse multiple spaces
    time_str = re.sub(r'\s+', ' ', time_str).strip()

    # "tomorrow, 9am" or "tomorrow 9am"
    tomorrow_match = re.match(r'tomorrow[,\s]+(.+)', time_str, re.IGNORECASE)
    if tomorrow_match:
        t = _parse_time_of_day(tomorrow_match.group(1).strip())
        if t is not None:
            h, m = t
            return datetime(today.year, today.month, today.day, h, m) + timedelta(days=1)
        return None

    # "Mar 30, 9am" or "Mar 30, 9 am"
    month_day_match = re.match(
        r'([A-Za-z]{3})\s+(\d{1,2})[,\s]+(.+)', time_str
    )
    if month_day_match:
        month_str, day_str, tod_str = month_day_match.groups()
        t = _parse_time_of_day(tod_str.strip())
        if t is not None:
            h, m = t
            month_num = _month_abbr_to_num(month_str)
            if month_num is not None:
                day = int(day_str)
                try:
                    dt = datetime(now.year, month_num, day, h, m)
                    # If more than 7 days in the past, assume next year
                    if (now - dt).days > 7:
                        dt = datetime(now.year + 1, month_num, day, h, m)
                    return dt
                except ValueError:
                    pass
        return None

    # "Apr 1" (date only, no time — assume midnight)
    date_only_match = re.match(r'([A-Za-z]{3})\s+(\d{1,2})$', time_str)
    if date_only_match:
        month_str, day_str = date_only_match.groups()
        month_num = _month_abbr_to_num(month_str)
        if month_num is not None:
            day = int(day_str)
            try:
                dt = datetime(now.year, month_num, day, 0, 0)
                if (now - dt).days > 7:
                    dt = datetime(now.year + 1, month_num, day, 0, 0)
                return dt
            except ValueError:
                pass
        return None

    # Time-only: "1 pm", "1pm", "9:30 am", "13:00"
    t = _parse_time_of_day(time_str)
    if t is not None:
        h, m = t
        dt = datetime(today.year, today.month, today.day, h, m)
        if dt <= now:
            dt += timedelta(days=1)
        return dt

    return None


def _parse_time_of_day(s: str) -> "tuple[int, int] | None":
    """Parse a time-of-day string into (hour_24, minute). Returns None on failure."""
    s = s.strip().lower()

    # 12h with colon: "9:30 am", "12:00pm"
    m = re.match(r'^(\d{1,2}):(\d{2})\s*(am|pm)$', s)
    if m:
        h, mn, ampm = int(m.group(1)), int(m.group(2)), m.group(3)
        h = _to_24h(h, ampm)
        if h is None:
            return None
        return h, mn

    # 12h without colon: "9 am", "9am", "1 pm", "12pm"
    m = re.match(r'^(\d{1,2})\s*(am|pm)$', s)
    if m:
        h, ampm = int(m.group(1)), m.group(2)
        h = _to_24h(h, ampm)
        if h is None:
            return None
        return h, 0

    # 24h: "13:00", "9:00"
    m = re.match(r'^(\d{1,2}):(\d{2})$', s)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mn <= 59:
            return h, mn

    return None


def _to_24h(h: int, ampm: str) -> "int | None":
    if ampm == "am":
        if h == 12:
            return 0
        if 1 <= h <= 11:
            return h
    else:  # pm
        if h == 12:
            return 12
        if 1 <= h <= 11:
            return h + 12
    return None


def _month_abbr_to_num(abbr: str) -> "int | None":
    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "may": 5, "jun": 6, "jul": 7, "aug": 8,
        "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    return months.get(abbr.lower())


def _format_delta_forward(total_seconds: int) -> str:
    if total_seconds < 60:
        return "Resets in less than a minute"

    total_minutes = total_seconds // 60
    if total_minutes < 60:
        return f"Resets in {total_minutes} min"

    total_hours = total_minutes // 60
    remaining_minutes = total_minutes % 60
    if total_hours < 24:
        if remaining_minutes == 0:
            return f"Resets in {total_hours} hours"
        return f"Resets in {total_hours} hours {remaining_minutes} min"

    total_days = total_hours // 24
    remaining_hours = total_hours % 24
    if remaining_hours == 0:
        return f"Resets in {total_days} days"
    return f"Resets in {total_days} days {remaining_hours} hours"
