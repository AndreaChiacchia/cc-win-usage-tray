"""Claude Usage Tray — main entry point."""

import tkinter as tk
import threading
import sys

import pystray

from datetime import datetime

from claude_runner import run_usage_threaded
from usage_parser import parse_usage, parse_email, UsageData, AccountUsage
import paths
import storage
import settings as settings_mod
from startup import is_startup_enabled, set_startup_enabled
from ui_popup import UsagePopup
from icon_generator import generate_icon, generate_loading_icon, generate_error_icon


class ClaudeUsageTray:
    def __init__(self):
        # --- Tkinter (main thread) ---
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("Claude Usage Tray")

        self.popup = UsagePopup(self.root)
        self.popup.set_refresh_callback(self._trigger_refresh)
        self.popup.set_refresh_interval_callback(self._on_refresh_interval_changed)

        # --- Tray icon ---
        self._tray_icon: pystray.Icon | None = None
        self._current_data: UsageData | None = None
        self._refreshing = False

        # --- Refresh state ---
        self._was_visible_before_refresh = False
        self._active_email: str = ""
        self._auto_refresh_id: str | None = None

        # --- Auto-refresh ---
        self._schedule_auto_refresh()

        # --- Initial data load ---
        self.root.after(500, self._trigger_refresh)

        # --- Startup notification ---
        from notifier import notify_startup
        notify_startup()

    # ------------------------------------------------------------------
    # Tray icon management
    # ------------------------------------------------------------------

    def _build_tray_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("Show Usage", self._show_usage_menu),
            pystray.MenuItem("Refresh Now", self._refresh_menu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Start on Windows startup", self._toggle_startup,
                             checked=lambda item: is_startup_enabled()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )

    def _start_tray(self):
        icon_img = generate_loading_icon()
        self._tray_icon = pystray.Icon(
            "claude_usage",
            icon=icon_img,
            title="Claude Usage",
            menu=self._build_tray_menu(),
        )
        self._tray_icon.run_detached()

    def _update_tray_icon(self, accounts: dict[str, AccountUsage]):
        if self._tray_icon is None:
            return
        
        # Find active account
        active_acc = next((a for a in accounts.values() if a.is_active), None)
        if not active_acc:
            # Fallback if no active account (shouldn't happen on success)
            return

        data = active_acc.usage
        if data.error and not data.sections:
            img = generate_error_icon()
            title = "Claude Usage — Error"
        else:
            max_pct = max((s.percentage for s in data.sections), default=0)
            img = generate_icon(max_pct)
            parts = [f"{s.label}: {s.percentage}%" for s in data.sections]
            title = f"Claude Usage ({active_acc.email})\n" + "\n".join(parts)
        self._tray_icon.icon = img
        self._tray_icon.title = title

    # ------------------------------------------------------------------
    # Data refresh
    # ------------------------------------------------------------------

    def _trigger_refresh(self):
        if self._refreshing:
            return
        self._refreshing = True
        self._was_visible_before_refresh = self.popup.visible
        self.popup._refreshing = True
        if self.popup.visible:
            self.root.after(0, self.popup.show_loading)
        if self._tray_icon:
            self._tray_icon.icon = generate_loading_icon()
            self._tray_icon.title = "Claude Usage — Loading..."

        run_usage_threaded(
            callback=self._on_usage_success,
            error_callback=self._on_usage_error,
        )

    def _on_usage_success(self, status_text: str, usage_text: str):
        # --- DEBUG: dump raw text to file ---
        try:
            with open(paths.DEBUG_LOG_FILE, "w", encoding="utf-8") as f:
                f.write(f"=== STATUS ===\n{repr(status_text)}\n\n=== USAGE ===\n{repr(usage_text)}")
        except Exception: pass

        try:
            email = parse_email(status_text) or "unknown@claude.ai"
            self._active_email = email
            # Re-schedule with the correct per-account interval (first schedule used "" email)
            self.root.after(0, self._on_refresh_interval_changed)
            usage_data = parse_usage(usage_text)

            # Load OLD accounts BEFORE saving new data
            old_accounts = storage.load_all_accounts()

            account = AccountUsage(
                email=email,
                usage=usage_data,
                last_updated=datetime.now().isoformat(),
                is_active=True
            )
            storage.save_account(account)

            # Load all accounts and reconcile active state
            all_accounts = storage.load_all_accounts()
            for email_key, acc in all_accounts.items():
                acc.is_active = (email_key == email)

            # Check thresholds and notify
            from notifier import check_and_notify
            check_and_notify(old_accounts, all_accounts)

            self.root.after(0, lambda: self._apply_data(all_accounts))
        except Exception as e:
            print(f"Error in _on_usage_success: {e}")
            self._on_usage_error(f"Processing error: {e}")
        finally:
            self._refreshing = False

    def _on_usage_error(self, message: str):
        try:
            # Load existing accounts to show historical data even on error
            all_accounts = storage.load_all_accounts()
            # If no accounts exist, we create a dummy one to show the error
            if not all_accounts:
                dummy_usage = UsageData(error=message)
                all_accounts["(Error)"] = AccountUsage(
                    email="Error",
                    usage=dummy_usage,
                    last_updated=datetime.now().isoformat(),
                    is_active=True
                )
            self.root.after(0, lambda: self._apply_data(all_accounts))
        except Exception as e:
            print(f"Error in _on_usage_error: {e}")
        finally:
            self._refreshing = False

    def _apply_data(self, accounts: dict[str, AccountUsage]):
        self.popup.show_usage(accounts)
        self._update_tray_icon(accounts)
        if self._was_visible_before_refresh:
            self.popup.show(steal_focus=False)
        self.popup.finish_refresh()

    def _schedule_auto_refresh(self):
        interval_ms = settings_mod.get_refresh_interval_minutes(self._active_email) * 60_000

        def _auto():
            self._trigger_refresh()
            self._schedule_auto_refresh()

        self._auto_refresh_id = self.root.after(interval_ms, _auto)

    def _on_refresh_interval_changed(self):
        if self._auto_refresh_id is not None:
            self.root.after_cancel(self._auto_refresh_id)
            self._auto_refresh_id = None
        self._schedule_auto_refresh()

    # ------------------------------------------------------------------
    # Menu actions (called from pystray thread — must be thread-safe)
    # ------------------------------------------------------------------

    def _toggle_startup(self, icon=None, item=None):
        set_startup_enabled(not is_startup_enabled())

    def _show_usage_menu(self, icon=None, item=None):
        self.root.after(0, self._show_popup)

    def _refresh_menu(self, icon=None, item=None):
        self.root.after(0, self._trigger_refresh)

    def _show_popup(self):
        if not self.popup.visible:
            # Only trigger refresh if we have no accounts at all (initial state)
            accounts = storage.load_all_accounts()
            if not accounts and not self._refreshing:
                self._trigger_refresh()
            self.popup.show()

    def _toggle_popup(self):
        if self._current_data is None and not self._refreshing:
            self._trigger_refresh()
        self.popup.toggle()

    # ------------------------------------------------------------------
    # Quit
    # ------------------------------------------------------------------

    def _quit(self, icon=None, item=None):
        from claude_runner import close_session
        close_session()
        if self._tray_icon:
            self._tray_icon.stop()
        self.root.after(0, self.root.quit)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self):
        # Start tray in background thread
        tray_thread = threading.Thread(target=self._start_tray, daemon=True)
        tray_thread.start()

        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self._quit()


def main():
    app = ClaudeUsageTray()
    app.run()


if __name__ == "__main__":
    main()
