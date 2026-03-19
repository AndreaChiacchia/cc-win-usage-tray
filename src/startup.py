"""Windows Registry startup management for ClaudeUsageTray."""

import sys
import winreg

_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "ClaudeUsageTray"


def _get_exe_path() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{sys.argv[0]}"'


def is_startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY) as key:
            winreg.QueryValueEx(key, _APP_NAME)
            return True
    except FileNotFoundError:
        return False


def set_startup_enabled(enabled: bool):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, access=winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, _get_exe_path())
        else:
            try:
                winreg.DeleteValue(key, _APP_NAME)
            except FileNotFoundError:
                pass
