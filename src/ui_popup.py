"""Tkinter popup window with usage progress bars."""

import tkinter as tk
from tkinter import ttk
from datetime import datetime

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

        self._last_updated_var = tk.StringVar(value="")
        tk.Label(
            self._bottom,
            textvariable=self._last_updated_var,
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

        # Hide when focus lost
        self.win.bind("<FocusOut>", self._on_focus_out)
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
        self._last_updated_var.set(f"Fail: {datetime.now().strftime('%H:%M:%S')}")
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

            # Timestamp for this account
            try:
                dt = datetime.fromisoformat(acc.last_updated)
                ts_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                ts_str = acc.last_updated
            
            tk.Label(
                self._content_frame,
                text=f"  Last sync: {ts_str}",
                bg=BG_COLOR, fg=FG_DIM_COLOR,
                font=TERMINAL_FONT,
                anchor="w",
            ).pack(fill=tk.X)

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
                    self._add_section(self._content_frame, section, top_pad=20 if i == 0 else 2)
            
            # Simple divider between accounts
            tk.Frame(self._content_frame, bg=BORDER_COLOR, height=1).pack(fill=tk.X, pady=2)

        self._refresh_btn.configure(state=tk.NORMAL)
        self._last_updated_var.set(f"Upd: {datetime.now().strftime('%H:%M:%S')}")
        self._reposition_and_resize()

    def _add_section(self, parent: tk.Frame, section: UsageSection, top_pad: int = 2):
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

        # Reset info
        if section.reset_info:
            tk.Label(
                frame,
                text=section.reset_info,
                bg=BG_COLOR, fg=FG_DIM_COLOR,
                font=TERMINAL_FONT,
                anchor="w",
            ).pack(fill=tk.X, pady=(2, 0))

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

    def show(self):
        self._reposition_and_resize()
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        self._visible = True

    def hide(self):
        self.win.withdraw()
        self._visible = False

    def set_refresh_callback(self, callback):
        self._on_refresh_cb = callback

    def _on_refresh(self):
        if self._on_refresh_cb:
            self._on_refresh_cb()

    def _on_focus_out(self, event):
        # Only hide if focus went outside the popup (not to a child widget)
        # We delay the check slightly to allow focus to settle (e.g. when clicking Refresh)
        self.win.after(100, self._check_focus)

    def _check_focus(self):
        if self._refreshing:
            return
        focused = self.win.focus_get()
        # If focused is None, focus went to another application or the desktop.
        if focused is None:
            self.hide()
            return
            
        # Check if the focused widget is a child of self.win
        try:
            # Walk up the widget hierarchy
            curr = focused
            while curr:
                if curr == self.win:
                    return # Focus is still inside the popup
                curr = curr.master
            # If we reach here, focus is in the app but not in the popup
            self.hide()
        except Exception:
            self.hide()

    @property
    def visible(self) -> bool:
        return self._visible
