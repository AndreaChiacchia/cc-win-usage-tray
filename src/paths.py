"""Centralized path constants for Claude Usage Tray data files.

All persistent data lives under ~/.ccwinusage so the app works correctly
regardless of the current working directory (e.g. when launched via the
Windows startup registry key, CWD is C:\\Windows\\system32).
"""
import os
import shutil
import sys

APP_DATA_DIR = os.path.join(os.path.expanduser("~"), ".ccwinusage")
APP_LOGS_DIR = os.path.join(APP_DATA_DIR, "logs")
CUSTOM_THEMES_DIR = os.path.join(APP_DATA_DIR, "themes")

os.makedirs(APP_LOGS_DIR, exist_ok=True)
os.makedirs(CUSTOM_THEMES_DIR, exist_ok=True)

SETTINGS_FILE = os.path.join(APP_DATA_DIR, "user_settings.json")
STORAGE_FILE = os.path.join(APP_DATA_DIR, "accounts_usage.json")
DEBUG_LOG_FILE = os.path.join(APP_LOGS_DIR, "usage_output_debug.txt")
NOTIFIER_LOG_FILE = os.path.join(APP_LOGS_DIR, "notifier_debug.log")


def _migrate_old_files():
    """Copy legacy data files from the exe/script directory to APP_DATA_DIR."""
    if getattr(sys, "frozen", False):
        old_base = os.path.dirname(sys.executable)
    else:
        old_base = os.path.dirname(os.path.abspath(__file__))

    migrations = [
        (os.path.join(old_base, "user_settings.json"), SETTINGS_FILE),
        (os.path.join(old_base, "accounts_usage.json"), STORAGE_FILE),
    ]
    for src, dst in migrations:
        if os.path.exists(src) and not os.path.exists(dst):
            try:
                shutil.copy2(src, dst)
            except Exception:
                pass


_migrate_old_files()
