"""Burn rate (pace delta) calculation for Claude Usage Tray."""

from datetime import datetime, timedelta

import time_utils
from config import PACE_DEAD_ZONE, PACE_SESSION_WINDOW_H, PACE_WEEK_WINDOW_H

_LABEL_TO_WINDOW_H = {
    "Current session": PACE_SESSION_WINDOW_H,
    "Current week": PACE_WEEK_WINDOW_H,
}


def compute_pace_delta(
    label: str,
    percentage: int,
    reset_info: str,
    now: datetime | None = None,
) -> int | None:
    """Return the pace delta (elapsed% - used%) for a section, or None to hide.

    A positive value means the user is under budget (used less than the time
    elapsed). A negative value means they are over budget. Returns None when
    the indicator should be hidden (Extra usage, unparseable reset, expired
    window, or within the dead zone).
    """
    if label == "Extra usage":
        return None

    window_h = _LABEL_TO_WINDOW_H.get(label)
    if window_h is None:
        return None

    if not reset_info:
        return None

    reset_dt = time_utils.parse_reset_datetime(reset_info)
    if reset_dt is None:
        return None

    now = now or datetime.now()
    window_start = reset_dt - timedelta(hours=window_h)

    if now >= reset_dt or now < window_start:
        return None

    elapsed_pct = (now - window_start) / (reset_dt - window_start) * 100
    delta = round(elapsed_pct - percentage)

    if abs(delta) < PACE_DEAD_ZONE:
        return None

    return delta
