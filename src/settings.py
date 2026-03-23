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


def get_theme_name() -> str:
    s = load_settings()
    return s.get("_global", {}).get("theme", "Claude Code")


def set_theme_name(name: str):
    s = load_settings()
    s.setdefault("_global", {})["theme"] = name
    save_settings(s)
