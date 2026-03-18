"""Windows toast notifications for usage threshold crossings."""
import os
import sys
from winotify import Notification, audio
from usage_parser import AccountUsage


def _log_debug(msg: str):
    """Write a debug message to a log file next to the executable (visible in --console=False builds)."""
    try:
        base = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else __file__)
        log_path = os.path.join(base, "notifier_debug.log")
        with open(log_path, "a", encoding="utf-8") as f:
            import datetime
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
        if new_acc.usage.error:
            continue
        old_acc = old_accounts.get(email)
        for section in new_acc.usage.sections:
            old_pct = _get_old_percentage(old_acc, section.label)
            new_pct = section.percentage
            _check_section(email, section.label, old_pct, new_pct)


def _get_old_percentage(old_acc: AccountUsage | None, label: str) -> int:
    """Get previous percentage for a section, or 0 if unknown."""
    if old_acc is None or old_acc.usage.error:
        return 0
    for sec in old_acc.usage.sections:
        if sec.label == label:
            return sec.percentage
    return 0


def _check_section(email: str, label: str, old_pct: int, new_pct: int):
    """Fire notification if a 10% boundary was crossed upward."""
    key = (email, label)
    last = _last_notified.get(key, (old_pct // THRESHOLD_STEP) * THRESHOLD_STEP)

    # Find the highest threshold crossed
    new_threshold = (new_pct // THRESHOLD_STEP) * THRESHOLD_STEP

    if new_threshold > last and new_threshold > 0:
        _fire_notification(email, label, new_pct, new_threshold)
        _last_notified[key] = new_threshold


def _fire_notification(email: str, label: str, pct: int, threshold: int):
    """Send a Windows toast notification."""
    toast = Notification(
        app_id=APP_ID,
        title=f"Usage Alert: {threshold}%",
        msg=f"{label} for {email} has reached {pct}%",
        duration="short",
    )
    toast.set_audio(audio.Default, loop=False)
    try:
        toast.show()
    except Exception as e:
        _log_debug(f"toast.show() failed: {e}")
