"""Historical usage snapshot storage for Claude Usage Tray.

Persists every refresh snapshot to ~/.ccwinusage/usage_history.json so the
Stats Panel can render hourly/daily/monthly trend charts.

Data structure::

    {
        "user@example.com": [
            {
                "ts": "2026-03-24T14:30:00",
                "sections": {
                    "Current session": {"pct": 42, "spent": null},
                    "Current week":    {"pct": 67, "spent": null},
                    "Extra usage":     {"pct": 12, "spent": "$3.50 / $5.00 spent"}
                }
            }
        ]
    }
"""

import json
import os
from datetime import datetime

from paths import HISTORY_FILE


def record_snapshot(email: str, sections: list) -> None:
    """Append a timestamped snapshot for *email* to the history file.

    *sections* is a list of ``UsageSection`` dataclass instances as returned
    by ``usage_parser.parse_usage()``.
    """
    data = _load()
    entries = data.setdefault(email, [])

    snapshot = {
        "ts": datetime.now().replace(microsecond=0).isoformat(),
        "sections": {
            s.label: {
                "pct": s.percentage,
                "spent": s.spent_info,
            }
            for s in sections
        },
    }
    entries.append(snapshot)
    _save(data)


def get_history(email: str) -> list:
    """Return the full snapshot list for *email* (oldest first)."""
    return _load().get(email, [])


def get_history_range(email: str, start: datetime, end: datetime) -> list:
    """Return snapshots for *email* whose timestamp falls within [start, end]."""
    result = []
    for entry in get_history(email):
        try:
            ts = datetime.fromisoformat(entry["ts"])
        except Exception:
            continue
        if start <= ts <= end:
            result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load() -> dict:
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[usage_history] load error: {e}")
        return {}


def _save(data: dict) -> None:
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
    except Exception as e:
        print(f"[usage_history] save error: {e}")
