"""User settings persistence for Claude Usage Tray."""
import json
import os

from paths import SETTINGS_FILE
_DEFAULT_REFRESH_MINUTES = 5
_DEFAULT_THRESHOLD = 10


def load_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(settings: dict):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"Error saving settings: {e}")


def get_refresh_interval_minutes(email: str) -> int:
    s = load_settings()
    return s.get(email, {}).get("refresh_interval_minutes", _DEFAULT_REFRESH_MINUTES)


def set_refresh_interval_minutes(email: str, val: int):
    s = load_settings()
    if email not in s:
        s[email] = {}
    s[email]["refresh_interval_minutes"] = val
    save_settings(s)


def get_notification_threshold(email: str, section_label: str) -> int:
    s = load_settings()
    return s.get(email, {}).get("notification_thresholds", {}).get(section_label, _DEFAULT_THRESHOLD)


def set_notification_threshold(email: str, section_label: str, val: int):
    s = load_settings()
    if email not in s:
        s[email] = {}
    if "notification_thresholds" not in s[email]:
        s[email]["notification_thresholds"] = {}
    s[email]["notification_thresholds"][section_label] = val
    save_settings(s)


def get_notifications_enabled(email: str) -> bool:
    s = load_settings()
    return s.get(email, {}).get("notifications_enabled", True)


def set_notifications_enabled(email: str, val: bool):
    s = load_settings()
    s.setdefault(email, {})["notifications_enabled"] = val
    save_settings(s)


def get_relative_time_enabled(email: str) -> bool:
    s = load_settings()
    return s.get(email, {}).get("relative_time", False)


def set_relative_time_enabled(email: str, val: bool):
    s = load_settings()
    s.setdefault(email, {})["relative_time"] = val
    save_settings(s)


def get_theme_name() -> str:
    s = load_settings()
    return s.get("_global", {}).get("theme", "Claude Code")


def set_theme_name(name: str):
    s = load_settings()
    s.setdefault("_global", {})["theme"] = name
    save_settings(s)


def get_popup_position() -> tuple[int, int] | None:
    s = load_settings()
    pos = s.get("_global", {}).get("popup_position")
    if pos and isinstance(pos, list) and len(pos) == 2:
        return (int(pos[0]), int(pos[1]))
    return None


def set_popup_position(x: int, y: int):
    s = load_settings()
    g = s.setdefault("_global", {})
    g["popup_position"] = [x, y]
    save_settings(s)


def clear_popup_position():
    s = load_settings()
    g = s.get("_global", {})
    g.pop("popup_position", None)
    g.pop("popup_monitor_name", None)
    g.pop("popup_monitor_offset", None)
    save_settings(s)


def get_popup_monitor_info() -> tuple[str, tuple[int, int]] | None:
    s = load_settings()
    g = s.get("_global", {})
    name = g.get("popup_monitor_name")
    offset = g.get("popup_monitor_offset")
    if name and offset and isinstance(offset, list) and len(offset) == 2:
        return (name, (int(offset[0]), int(offset[1])))
    return None


def set_popup_monitor_info(monitor_name: str, offset_x: int, offset_y: int):
    s = load_settings()
    g = s.setdefault("_global", {})
    g["popup_monitor_name"] = monitor_name
    g["popup_monitor_offset"] = [offset_x, offset_y]
    save_settings(s)


def get_always_on_top() -> bool:
    s = load_settings()
    return s.get("_global", {}).get("always_on_top", True)


def set_always_on_top(enabled: bool):
    s = load_settings()
    g = s.setdefault("_global", {})
    g["always_on_top"] = enabled
    save_settings(s)
