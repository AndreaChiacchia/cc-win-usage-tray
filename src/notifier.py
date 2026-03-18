"""Windows toast notifications for usage threshold crossings."""
from winotify import Notification, audio
from usage_parser import AccountUsage

# In-memory dict tracking last notified threshold per (email, section_label)
# Format: {("user@example.com", "Current session"): 40}  — means we last notified at 40%
_last_notified: dict[tuple[str, str], int] = {}

THRESHOLD_STEP = 10  # Notify every 10%


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
        app_id="Claude Usage Tray",
        title=f"Usage Alert: {threshold}%",
        msg=f"{label} for {email} has reached {pct}%",
        duration="short",
    )
    toast.set_audio(audio.Default, loop=False)
    toast.show()
