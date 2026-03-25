"""Windows toast notifications for usage threshold crossings."""
import datetime
import os
import sys
from winotify import Notification, audio
from usage_parser import AccountUsage
import pace_delta as pace_delta_mod
import settings as settings_mod
import paths


def _log_debug(msg: str):
    """Write a debug message to a log file in the app data directory."""
    try:
        with open(paths.NOTIFIER_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().isoformat()} {msg}\n")
    except Exception:
        pass

# In-memory dict tracking last notified threshold per (email, section_label)
# Format: {("user@example.com", "Current session"): 40}  — means we last notified at 40%
_last_notified: dict[tuple[str, str], int] = {}

THRESHOLD_STEP = 10  # Notify every 10%

APP_ID = "ClaudeUsageTray"
_SHORTCUT_NAME = "Claude Usage Tray.lnk"


def _ensure_shortcut():
    """Create a Start Menu shortcut with AppUserModelID so Windows accepts toasts."""
    try:
        start_menu = os.path.join(
            os.environ.get("APPDATA", ""),
            "Microsoft", "Windows", "Start Menu", "Programs",
        )
        shortcut_path = os.path.join(start_menu, _SHORTCUT_NAME)

        # Always delete and recreate — previous attempt may have left a shortcut
        # without the AUMID property (due to the GPS_READWRITE crash).
        if os.path.exists(shortcut_path):
            os.remove(shortcut_path)

        import win32com.client
        import pythoncom
        from win32com.propsys import propsys, pscon

        target = sys.executable

        shell = win32com.client.Dispatch("WScript.Shell")
        lnk = shell.CreateShortcut(shortcut_path)
        lnk.TargetPath = target
        lnk.WorkingDirectory = os.path.dirname(target)
        lnk.Description = "Claude Usage Tray"
        lnk.Save()

        # GPS_READWRITE = 0x2 (raw Windows SDK constant; propsys.GPS_READWRITE
        # does not exist as a Python attribute in pywin32)
        store = propsys.SHGetPropertyStoreFromParsingName(
            shortcut_path,
            None,
            0x2,
            propsys.IID_IPropertyStore,
        )
        prop_variant = propsys.PROPVARIANTType(APP_ID, pythoncom.VT_LPWSTR)
        store.SetValue(pscon.PKEY_AppUserModel_ID, prop_variant)
        store.Commit()
        _log_debug(f"Shortcut created with AUMID '{APP_ID}' at {shortcut_path}")
    except Exception as e:
        _log_debug(f"Could not create Start Menu shortcut: {e}")


_ensure_shortcut()


def check_and_notify(old_accounts: dict[str, AccountUsage],
                     new_accounts: dict[str, AccountUsage]):
    """Compare old vs new usage and fire notifications for crossed thresholds."""
    for email, new_acc in new_accounts.items():
        if not settings_mod.get_notifications_enabled(email):
            continue
        if new_acc.usage.error:
            continue
        old_acc = old_accounts.get(email)
        for section in new_acc.usage.sections:
            old_pct = _get_old_percentage(old_acc, section.label)
            new_pct = section.percentage
            if settings_mod.get_pace_delta_enabled(email):
                delta = pace_delta_mod.compute_pace_delta(
                    section.label, new_pct, section.reset_info
                )
            else:
                delta = None
            _check_section(email, section.label, old_pct, new_pct, delta)


def _get_old_percentage(old_acc: AccountUsage | None, label: str) -> int:
    """Get previous percentage for a section, or 0 if unknown."""
    if old_acc is None or old_acc.usage.error:
        return 0
    for sec in old_acc.usage.sections:
        if sec.label == label:
            return sec.percentage
    return 0


def _check_section(email: str, label: str, old_pct: int, new_pct: int,
                   delta: int | None = None):
    """Fire notification if a threshold boundary was crossed upward."""
    key = (email, label)
    threshold_step = settings_mod.get_notification_threshold(email, label)
    last = _last_notified.get(key, (old_pct // threshold_step) * threshold_step)

    # Find the highest threshold crossed
    new_threshold = (new_pct // threshold_step) * threshold_step

    if new_threshold > last and new_threshold > 0:
        _fire_notification(email, label, new_pct, new_threshold, delta)
        _last_notified[key] = new_threshold


def _get_icon_path() -> str:
    """Get absolute path to claude_icon.png, supporting PyInstaller bundles."""
    if getattr(sys, '_MEIPASS', None):
        return os.path.join(sys._MEIPASS, 'claude_icon.png')
    return os.path.join(os.path.dirname(__file__), 'claude_icon.png')


def notify_startup():
    """Send a startup notification."""
    toast = Notification(
        app_id=APP_ID,
        title="Claude Usage Tray",
        msg="Notifications active. Monitoring usage.",
        icon=_get_icon_path(),
        duration="short",
    )
    toast.set_audio(audio.Default, loop=False)
    try:
        toast.show()
    except Exception as e:
        _log_debug(f"notify_startup toast.show() failed: {e}")


_LABEL_TO_TITLE = {
    "Current session": "Session usage at",
    "Current week": "Weekly usage at",
    "Extra usage": "Extra usage at",
}


def _fire_notification(email: str, label: str, pct: int, threshold: int,
                       delta: int | None = None):
    """Send a Windows toast notification."""
    title_prefix = _LABEL_TO_TITLE.get(label, f"{label} at")
    if delta is not None and delta > 0:
        pace_suffix = f" under budget -> +{delta}%"
    elif delta is not None and delta < 0:
        pace_suffix = f" over budget -> -{abs(delta)}%"
    else:
        pace_suffix = ""
    toast = Notification(
        app_id=APP_ID,
        title=f"{title_prefix} {pct}%",
        msg=f"{email} -> {pct}%{('\n' + pace_suffix.strip()) if pace_suffix else ''}",
        icon=_get_icon_path(),
        duration="short",
    )
    toast.set_audio(audio.Default, loop=False)
    try:
        toast.show()
    except Exception as e:
        _log_debug(f"toast.show() failed: {e}")
