"""Tkinter popup window with usage progress bars."""

import tkinter as tk
from tkinter import ttk
from datetime import datetime

import settings as settings_mod
from version import __version__
from config import (
    BG_COLOR, FG_COLOR, FG_DIM_COLOR, BORDER_COLOR,
    BAR_BG_COLOR, BAR_GREEN, BAR_YELLOW, BAR_RED,
    BUTTON_BG, BUTTON_FG, BUTTON_ACTIVE_BG,
    POPUP_WIDTH, POPUP_PADDING, TASKBAR_OFFSET,
    COLOR_GREEN_MAX, COLOR_YELLOW_MAX,
)
from usage_parser import UsageData, UsageSection, AccountUsage

# Use a monospace font for terminal aesthetic
TERMINAL_FONT = ("Consolas", 10)
TERMINAL_FONT_BOLD = ("Consolas", 11, "bold")


def _bar_color(percentage: int) -> str:
    if percentage < COLOR_GREEN_MAX:
        return BAR_GREEN
    elif percentage < COLOR_YELLOW_MAX:
        return BAR_YELLOW
    else:
        return BAR_RED



class UsagePopup:
    """Borderless popup window showing Claude Code usage."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self._visible = False
        self._refreshing = False
        self._on_refresh_cb = None
        self._on_refresh_interval_changed_cb = None
        self._settings_windows: dict[str, tk.Toplevel] = {}

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.configure(bg=BG_COLOR)
        self.win.attributes("-topmost", True)
        self.win.withdraw()

        # Styled border via outer frame
        self._outer = tk.Frame(self.win, bg=BORDER_COLOR, padx=1, pady=1)
        self._outer.pack(fill=tk.BOTH, expand=True)

        self._inner = tk.Frame(self._outer, bg=BG_COLOR, padx=POPUP_PADDING, pady=POPUP_PADDING)
        self._inner.pack(fill=tk.BOTH, expand=True)

        # Content area (will be rebuilt on each update)
        self._content_frame = tk.Frame(self._inner, bg=BG_COLOR)
        self._content_frame.pack(fill=tk.BOTH, expand=True)

        # Bottom bar: last updated + refresh button
        self._bottom = tk.Frame(self._inner, bg=BG_COLOR)
        self._bottom.pack(fill=tk.X, pady=(POPUP_PADDING // 2, 0))

        tk.Label(
            self._bottom,
            text=f"v{__version__}",
            bg=BG_COLOR, fg=FG_DIM_COLOR,
            font=TERMINAL_FONT,
        ).pack(side=tk.LEFT)

        self._refresh_btn = tk.Button(
            self._bottom,
            text="⟳ Refresh",
            bg=BUTTON_BG, fg=BUTTON_FG,
            activebackground=BUTTON_ACTIVE_BG, activeforeground=BUTTON_FG,
            relief=tk.FLAT, padx=12, pady=4,
            font=TERMINAL_FONT,
            cursor="hand2",
            command=self._on_refresh,
        )
        self._refresh_btn.pack(side=tk.RIGHT)

        # Show loading state initially
        self.show_loading()

        self.win.protocol("WM_DELETE_WINDOW", self.hide)

    def _clear_content(self):
        for widget in self._content_frame.winfo_children():
            widget.destroy()

    def show_loading(self):
        """Display a loading indicator."""
        self._clear_content()
        tk.Label(
            self._content_frame,
            text="> Loading usage data...",
            bg=BG_COLOR, fg=FG_DIM_COLOR,
            font=TERMINAL_FONT,
            pady=20,
        ).pack()
        self._refresh_btn.configure(state=tk.DISABLED)
        self._reposition_and_resize()

    def show_error(self, message: str):
        """Display an error message."""
        self._clear_content()
        tk.Label(
            self._content_frame,
            text="[ERROR]",
            bg=BG_COLOR, fg=BAR_RED,
            font=TERMINAL_FONT_BOLD,
            anchor="w",
        ).pack(fill=tk.X)

        tk.Label(
            self._content_frame,
            text=message,
            bg=BG_COLOR, fg=FG_COLOR,
            font=TERMINAL_FONT,
            wraplength=POPUP_WIDTH - POPUP_PADDING * 2 - 4,
            justify=tk.LEFT,
            anchor="w",
            pady=8,
        ).pack(fill=tk.X)

        self._refresh_btn.configure(state=tk.NORMAL)
        self._reposition_and_resize()

    def show_usage(self, accounts: dict[str, AccountUsage]):
        """Display parsed usage data for all known accounts."""
        self._clear_content()

        if not accounts:
            self.show_error("No usage data available")
            return

        # Overall Title
        tk.Label(
            self._content_frame,
            text="Claude Code Usage",
            bg=BG_COLOR, fg=FG_COLOR,
            font=TERMINAL_FONT_BOLD,
            anchor="w",
        ).pack(fill=tk.X, pady=(0, POPUP_PADDING // 2))

        # Sort accounts to put active one first
        sorted_emails = sorted(accounts.keys(), key=lambda e: (not accounts[e].is_active, e))

        for email in sorted_emails:
            acc = accounts[email]

            # Account Header
            header_text = f"> {email}"
            if not acc.is_active:
                header_text += " ⚠️"

            tk.Label(
                self._content_frame,
                text=header_text,
                bg=BG_COLOR, fg=FG_COLOR if acc.is_active else FG_DIM_COLOR,
                font=TERMINAL_FONT_BOLD,
                anchor="w",
            ).pack(fill=tk.X, pady=(4, 0))

            # Timestamp row with cog for account settings
            try:
                dt = datetime.fromisoformat(acc.last_updated)
                ts_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                ts_str = acc.last_updated

            sync_row = tk.Frame(self._content_frame, bg=BG_COLOR)
            sync_row.pack(fill=tk.X)
            tk.Label(
                sync_row,
                text=f"  Last sync: {ts_str}",
                bg=BG_COLOR, fg=FG_DIM_COLOR,
                font=TERMINAL_FONT,
                anchor="w",
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)
            cog_acct = tk.Label(
                sync_row,
                text="⚙",
                bg=BG_COLOR, fg=FG_DIM_COLOR,
                font=TERMINAL_FONT,
                cursor="hand2",
            )
            cog_acct.pack(side=tk.RIGHT)
            cog_acct.bind("<Button-1>", lambda e, em=email: self._open_account_settings(em))

            if acc.usage.error:
                tk.Label(
                    self._content_frame,
                    text=f"  Error: {acc.usage.error}",
                    bg=BG_COLOR, fg=BAR_RED,
                    font=TERMINAL_FONT,
                    anchor="w",
                ).pack(fill=tk.X)
            else:
                for i, section in enumerate(acc.usage.sections):
                    self._add_section(
                        self._content_frame, section,
                        email=email,
                        top_pad=20 if i == 0 else 2,
                    )

            # Simple divider between accounts
            tk.Frame(self._content_frame, bg=BORDER_COLOR, height=1).pack(fill=tk.X, pady=2)

        self._refresh_btn.configure(state=tk.NORMAL)
        self._reposition_and_resize()

    def _add_section(self, parent: tk.Frame, section: UsageSection, email: str, top_pad: int = 2):
        """Add a usage section with label, canvas bar, and reset info."""
        frame = tk.Frame(parent, bg=BG_COLOR, pady=0)
        frame.pack(fill=tk.X, pady=(top_pad, 0))

        # Section label
        tk.Label(
            frame,
            text=section.label,
            bg=BG_COLOR, fg=FG_COLOR,
            font=TERMINAL_FONT_BOLD,
            anchor="w",
        ).pack(fill=tk.X)

        # Canvas progress bar + percentage
        bar_row = tk.Frame(frame, bg=BG_COLOR)
        bar_row.pack(fill=tk.X, pady=(2, 0))

        color = _bar_color(section.percentage)
        pct = section.percentage

        BAR_HEIGHT = 18
        canvas = tk.Canvas(bar_row, height=BAR_HEIGHT, bg=BAR_BG_COLOR,
                           highlightthickness=0)
        canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def _draw_bar(event=None, _canvas=canvas, _pct=pct, _color=color, _h=BAR_HEIGHT):
            w = _canvas.winfo_width()
            if w <= 1:
                w = 300
            _canvas.delete("all")
            filled_w = int(w * _pct / 100)
            _canvas.create_rectangle(0, 0, filled_w, _h, fill=_color, outline="")

        canvas.bind("<Configure>", _draw_bar)

        tk.Label(
            bar_row,
            text=f"{section.percentage:3d}%",
            bg=BG_COLOR, fg=color,
            font=TERMINAL_FONT_BOLD,
            width=5,
            anchor="e",
        ).pack(side=tk.RIGHT)

        # Reset info row with cog, or standalone cog when reset_info is absent
        _em = email
        _sl = section.label
        if section.reset_info:
            reset_row = tk.Frame(frame, bg=BG_COLOR)
            reset_row.pack(fill=tk.X, pady=(2, 0))
            tk.Label(
                reset_row,
                text=section.reset_info,
                bg=BG_COLOR, fg=FG_DIM_COLOR,
                font=TERMINAL_FONT,
                anchor="w",
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)
            cog = tk.Label(
                reset_row, text="⚙",
                bg=BG_COLOR, fg=FG_DIM_COLOR,
                font=TERMINAL_FONT, cursor="hand2",
            )
            cog.pack(side=tk.RIGHT)
            cog.bind("<Button-1>", lambda e, em=_em, sl=_sl: self._open_threshold_settings(em, sl))
        else:
            cog_row = tk.Frame(frame, bg=BG_COLOR)
            cog_row.pack(fill=tk.X, pady=(2, 0))
            cog = tk.Label(
                cog_row, text="⚙",
                bg=BG_COLOR, fg=FG_DIM_COLOR,
                font=TERMINAL_FONT, cursor="hand2", anchor="w",
            )
            cog.pack(side=tk.LEFT)
            cog.bind("<Button-1>", lambda e, em=_em, sl=_sl: self._open_threshold_settings(em, sl))

        # Spent info (Extra usage only)
        if section.spent_info:
            tk.Label(
                frame,
                text=section.spent_info,
                bg=BG_COLOR, fg=FG_DIM_COLOR,
                font=TERMINAL_FONT,
                anchor="w",
            ).pack(fill=tk.X)

        # Separator line (Double-dashed for bolder terminal feel)
        sep_frame = tk.Frame(frame, bg=BG_COLOR, height=1)
        sep_frame.pack(fill=tk.X, pady=(2, 0))
        tk.Label(
            sep_frame,
            text="=" * 80,
            bg=BG_COLOR, fg=BORDER_COLOR,
            font=("Consolas", 4),
            pady=0,
            anchor="n",
        ).pack(fill=tk.X)

    # ------------------------------------------------------------------
    # Settings windows
    # ------------------------------------------------------------------

    def _make_settings_window(self, key: str, title: str):
        """Create a borderless settings window. Returns (win, inner, close_fn) or None if already open."""
        existing = self._settings_windows.get(key)
        if existing and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return None

        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.configure(bg=BG_COLOR)
        win.attributes("-topmost", True)
        self._settings_windows[key] = win

        def _close():
            win.destroy()
            self._settings_windows.pop(key, None)

        win.bind("<Escape>", lambda e: _close())

        outer = tk.Frame(win, bg=BORDER_COLOR, padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)
        inner = tk.Frame(outer, bg=BG_COLOR, padx=POPUP_PADDING, pady=POPUP_PADDING)
        inner.pack(fill=tk.BOTH, expand=True)

        # Title bar with close button
        title_bar = tk.Frame(inner, bg=BG_COLOR)
        title_bar.pack(fill=tk.X, pady=(0, POPUP_PADDING // 2))
        tk.Button(
            title_bar,
            text="✕",
            bg=BUTTON_BG, fg=BUTTON_FG,
            activebackground=BUTTON_ACTIVE_BG, activeforeground=BUTTON_FG,
            relief=tk.FLAT, padx=6, pady=2,
            font=TERMINAL_FONT,
            cursor="hand2",
            command=_close,
        ).pack(side=tk.RIGHT)
        tk.Label(
            title_bar,
            text=title,
            bg=BG_COLOR, fg=FG_COLOR,
            font=TERMINAL_FONT_BOLD,
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        return win, inner, _close

    def _center_window(self, win: tk.Toplevel, w: int, h: int):
        win.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")

    def _open_account_settings(self, email: str):
        result = self._make_settings_window(f"account_{email}", "Auto-Refresh Settings")
        if result is None:
            return
        win, inner, _close = result

        tk.Label(
            inner,
            text=email,
            bg=BG_COLOR, fg=FG_DIM_COLOR,
            font=TERMINAL_FONT,
            anchor="w",
        ).pack(fill=tk.X)

        current_val = settings_mod.get_refresh_interval_minutes(email)
        val_label = tk.Label(
            inner,
            text=f"Update every {current_val} minutes",
            bg=BG_COLOR, fg=FG_COLOR,
            font=TERMINAL_FONT,
            anchor="w",
        )
        val_label.pack(fill=tk.X, pady=(POPUP_PADDING // 2, 4))

        def on_change(v):
            val = int(float(v))
            val_label.config(text=f"Update every {val} minutes")
            settings_mod.set_refresh_interval_minutes(email, val)
            if self._on_refresh_interval_changed_cb:
                self._on_refresh_interval_changed_cb()

        scale = tk.Scale(
            inner,
            from_=1, to=30, resolution=1,
            orient=tk.HORIZONTAL,
            command=on_change,
            bg=BG_COLOR, fg=FG_COLOR,
            troughcolor=BAR_BG_COLOR,
            highlightthickness=0,
            font=TERMINAL_FONT,
            showvalue=False,
        )
        scale.set(current_val)
        scale.pack(fill=tk.X)

        self._center_window(win, 380, 180)
        win.focus_force()

    def _open_threshold_settings(self, email: str, section_label: str):
        key = f"threshold_{email}_{section_label}"
        result = self._make_settings_window(key, f"Notification Threshold — {section_label}")
        if result is None:
            return
        win, inner, _close = result

        tk.Label(
            inner,
            text=email,
            bg=BG_COLOR, fg=FG_DIM_COLOR,
            font=TERMINAL_FONT,
            anchor="w",
        ).pack(fill=tk.X)

        current_val = settings_mod.get_notification_threshold(email, section_label)
        val_label = tk.Label(
            inner,
            text=f"Notify every {current_val}%",
            bg=BG_COLOR, fg=FG_COLOR,
            font=TERMINAL_FONT,
            anchor="w",
        )
        val_label.pack(fill=tk.X, pady=(POPUP_PADDING // 2, 4))

        def on_change(v):
            val = int(float(v))
            val_label.config(text=f"Notify every {val}%")
            settings_mod.set_notification_threshold(email, section_label, val)

        scale = tk.Scale(
            inner,
            from_=1, to=100, resolution=1,
            orient=tk.HORIZONTAL,
            command=on_change,
            bg=BG_COLOR, fg=FG_COLOR,
            troughcolor=BAR_BG_COLOR,
            highlightthickness=0,
            font=TERMINAL_FONT,
            showvalue=False,
        )
        scale.set(current_val)
        scale.pack(fill=tk.X)

        self._center_window(win, 380, 180)
        win.focus_force()

    # ------------------------------------------------------------------

    def _reposition_and_resize(self):
        """Position popup in bottom-right corner, above taskbar."""
        self.win.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        self.win.geometry(f"{POPUP_WIDTH}x1")
        self.win.update_idletasks()
        req_h = self.win.winfo_reqheight()

        x = screen_w - POPUP_WIDTH - 8
        y = screen_h - req_h - TASKBAR_OFFSET
        self.win.geometry(f"{POPUP_WIDTH}x{req_h}+{x}+{y}")

    def toggle(self):
        if self._visible:
            self.hide()
        else:
            self.show()

    def _start_focus_poll(self):
        """Start periodic focus checking while popup is visible."""
        self._poll_focus()

    def _poll_focus(self):
        """Periodically check if popup still has focus; hide if not."""
        if not self._visible:
            return  # Stop polling when hidden
        if self._refreshing:
            # Keep polling but don't dismiss during refresh
            self.win.after(200, self._poll_focus)
            return
        focused = self.win.focus_get()
        if focused is None:
            self.hide()
            return
        # Allow focus in our popup or any open settings window
        allowed = {self.win} | {sw for sw in self._settings_windows.values() if sw.winfo_exists()}
        try:
            curr = focused
            while curr:
                if curr in allowed:
                    break
                curr = curr.master
            else:
                self.hide()
                return
        except Exception:
            self.hide()
            return
        # Still focused — keep polling
        self.win.after(200, self._poll_focus)

    def show(self):
        self._reposition_and_resize()
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        self._visible = True
        self._start_focus_poll()

    def hide(self):
        self.win.withdraw()
        self._visible = False

    def set_refresh_callback(self, callback):
        self._on_refresh_cb = callback

    def set_refresh_interval_callback(self, callback):
        self._on_refresh_interval_changed_cb = callback

    def _on_refresh(self):
        if self._on_refresh_cb:
            self._on_refresh_cb()

    def finish_refresh(self):
        """Clear refreshing state. The focus poll handles the rest."""
        self._refreshing = False

    @property
    def visible(self) -> bool:
        return self._visible
