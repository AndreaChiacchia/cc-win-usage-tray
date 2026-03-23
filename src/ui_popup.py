"""Tkinter popup window with usage progress bars."""

import tkinter as tk
from datetime import datetime

import settings as settings_mod
import theme as theme_mod
from version import __version__
from config import (
    POPUP_WIDTH, POPUP_PADDING, TASKBAR_OFFSET,
    COLOR_GREEN_MAX, COLOR_YELLOW_MAX,
)
from usage_parser import UsageSection, AccountUsage


def _bar_color(percentage: int) -> str:
    t = theme_mod.current()
    if percentage < COLOR_GREEN_MAX:
        return t.bar_green
    elif percentage < COLOR_YELLOW_MAX:
        return t.bar_yellow
    else:
        return t.bar_red


class UsagePopup:
    """Borderless popup window showing Claude Code usage."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self._visible = False
        self._refreshing = False
        self._on_refresh_cb = None
        self._on_refresh_interval_changed_cb = None
        self._settings_windows: dict[str, tk.Toplevel] = {}
        self._last_accounts: dict | None = None

        t = theme_mod.current()

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.configure(bg=t.bg)
        self.win.attributes("-topmost", True)
        self.win.withdraw()

        # Styled border via outer frame
        self._outer = tk.Frame(self.win, bg=t.border, padx=1, pady=1)
        self._outer.pack(fill=tk.BOTH, expand=True)

        self._inner = tk.Frame(self._outer, bg=t.bg, padx=POPUP_PADDING, pady=POPUP_PADDING)
        self._inner.pack(fill=tk.BOTH, expand=True)

        # Top bar: title + close button
        self._top = tk.Frame(self._inner, bg=t.bg)
        self._top.pack(fill=tk.X, pady=(0, POPUP_PADDING // 2))

        self._title_label = tk.Label(
            self._top,
            text="Claude Code Usage",
            bg=t.bg, fg=t.fg,
            font=t.font_bold,
            anchor="w",
        )
        self._title_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._close_btn = tk.Button(
            self._top,
            text="✕",
            bg=t.button_bg, fg=t.button_fg,
            activebackground=t.button_active_bg, activeforeground=t.button_fg,
            padx=6, pady=2,
            font=t.font,
            cursor="hand2",
            command=self.hide,
            **t.button_style_kwargs(),
        )
        self._close_btn.pack(side=tk.RIGHT)

        # Content area (will be rebuilt on each update)
        self._content_frame = tk.Frame(self._inner, bg=t.bg)
        self._content_frame.pack(fill=tk.BOTH, expand=True)

        # Bottom bar: version + refresh button
        self._bottom = tk.Frame(self._inner, bg=t.bg)
        self._bottom.pack(fill=tk.X, pady=(POPUP_PADDING // 2, 0))

        self._version_label = tk.Label(
            self._bottom,
            text=f"v{__version__}",
            bg=t.bg, fg=t.fg_dim,
            font=t.font,
        )
        self._version_label.pack(side=tk.LEFT)

        self._refresh_btn = tk.Button(
            self._bottom,
            text="⟳ Refresh",
            bg=t.button_bg, fg=t.button_fg,
            activebackground=t.button_active_bg, activeforeground=t.button_fg,
            padx=12, pady=4,
            font=t.font,
            cursor="hand2",
            command=self._on_refresh,
            **t.button_style_kwargs(),
        )
        self._refresh_btn.pack(side=tk.RIGHT)

        # Show loading state initially
        self.show_loading()

        self.win.protocol("WM_DELETE_WINDOW", self.hide)

    def apply_theme(self):
        """Reconfigure persistent chrome widgets to the current theme."""
        t = theme_mod.current()
        self.win.configure(bg=t.bg)
        self._outer.configure(bg=t.border)
        self._inner.configure(bg=t.bg)
        self._top.configure(bg=t.bg)
        self._title_label.configure(bg=t.bg, fg=t.fg, font=t.font_bold)
        self._close_btn.configure(
            bg=t.button_bg, fg=t.button_fg,
            activebackground=t.button_active_bg, activeforeground=t.button_fg,
            font=t.font,
            **t.button_style_kwargs(),
        )
        self._content_frame.configure(bg=t.bg)
        self._bottom.configure(bg=t.bg)
        self._version_label.configure(bg=t.bg, fg=t.fg_dim, font=t.font)
        self._refresh_btn.configure(
            bg=t.button_bg, fg=t.button_fg,
            activebackground=t.button_active_bg, activeforeground=t.button_fg,
            font=t.font,
            **t.button_style_kwargs(),
        )

    def _clear_content(self):
        for widget in self._content_frame.winfo_children():
            widget.destroy()

    def show_loading(self):
        """Display a loading indicator."""
        t = theme_mod.current()
        self._clear_content()
        tk.Label(
            self._content_frame,
            text="> Loading usage data...",
            bg=t.bg, fg=t.fg_dim,
            font=t.font,
            pady=20,
        ).pack()
        self._refresh_btn.configure(state=tk.DISABLED)
        self._reposition_and_resize()

    def show_error(self, message: str):
        """Display an error message."""
        t = theme_mod.current()
        self._clear_content()
        tk.Label(
            self._content_frame,
            text="[ERROR]",
            bg=t.bg, fg=t.bar_red,
            font=t.font_bold,
            anchor="w",
        ).pack(fill=tk.X)

        tk.Label(
            self._content_frame,
            text=message,
            bg=t.bg, fg=t.fg,
            font=t.font,
            wraplength=POPUP_WIDTH - POPUP_PADDING * 2 - 4,
            justify=tk.LEFT,
            anchor="w",
            pady=8,
        ).pack(fill=tk.X)

        self._refresh_btn.configure(state=tk.NORMAL)
        self._reposition_and_resize()

    def show_usage(self, accounts: dict[str, AccountUsage]):
        """Display parsed usage data for all known accounts."""
        self._last_accounts = accounts
        t = theme_mod.current()
        self._clear_content()

        if not accounts:
            self.show_error("No usage data available")
            return

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
                bg=t.bg, fg=t.fg if acc.is_active else t.fg_dim,
                font=t.font_bold,
                anchor="w",
            ).pack(fill=tk.X, pady=(4, 0))

            # Timestamp row with cog for account settings
            try:
                dt = datetime.fromisoformat(acc.last_updated)
                ts_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                ts_str = acc.last_updated

            sync_row = tk.Frame(self._content_frame, bg=t.bg)
            sync_row.pack(fill=tk.X)
            tk.Label(
                sync_row,
                text=f"  Last sync: {ts_str}",
                bg=t.bg, fg=t.fg_dim,
                font=t.font,
                anchor="w",
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)
            cog_acct = tk.Label(
                sync_row,
                text="⚙",
                bg=t.bg, fg=t.fg_dim,
                font=t.font,
                cursor="hand2",
            )
            cog_acct.pack(side=tk.RIGHT)
            cog_acct.bind("<Button-1>", lambda e, em=email: self._open_account_settings(em))

            if acc.usage.error:
                tk.Label(
                    self._content_frame,
                    text=f"  Error: {acc.usage.error}",
                    bg=t.bg, fg=t.bar_red,
                    font=t.font,
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
            tk.Frame(self._content_frame, bg=t.border, height=1).pack(fill=tk.X, pady=2)

        self._refresh_btn.configure(state=tk.NORMAL)
        self._reposition_and_resize()

    def _add_section(self, parent: tk.Frame, section: UsageSection, email: str, top_pad: int = 2):
        """Add a usage section with label, canvas bar, and reset info."""
        t = theme_mod.current()
        frame = tk.Frame(parent, bg=t.bg, pady=0)
        frame.pack(fill=tk.X, pady=(top_pad, 0))

        # Section label
        tk.Label(
            frame,
            text=section.label,
            bg=t.bg, fg=t.fg,
            font=t.font_bold,
            anchor="w",
        ).pack(fill=tk.X)

        # Canvas progress bar + percentage
        bar_row = tk.Frame(frame, bg=t.bg)
        bar_row.pack(fill=tk.X, pady=(2, 0))

        color = _bar_color(section.percentage)
        pct = section.percentage

        BAR_HEIGHT = 18
        canvas = tk.Canvas(bar_row, height=BAR_HEIGHT, bg=t.bar_bg,
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
            bg=t.bg, fg=color,
            font=t.font_bold,
            width=5,
            anchor="e",
        ).pack(side=tk.RIGHT)

        # Reset info row with cog, or standalone cog when reset_info is absent
        _em = email
        _sl = section.label
        if section.reset_info:
            reset_row = tk.Frame(frame, bg=t.bg)
            reset_row.pack(fill=tk.X, pady=(2, 0))
            tk.Label(
                reset_row,
                text=section.reset_info,
                bg=t.bg, fg=t.fg_dim,
                font=t.font,
                anchor="w",
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)
            cog = tk.Label(
                reset_row, text="⚙",
                bg=t.bg, fg=t.fg_dim,
                font=t.font, cursor="hand2",
            )
            cog.pack(side=tk.RIGHT)
            cog.bind("<Button-1>", lambda e, em=_em, sl=_sl: self._open_threshold_settings(em, sl))
        else:
            cog_row = tk.Frame(frame, bg=t.bg)
            cog_row.pack(fill=tk.X, pady=(2, 0))
            cog = tk.Label(
                cog_row, text="⚙",
                bg=t.bg, fg=t.fg_dim,
                font=t.font, cursor="hand2", anchor="w",
            )
            cog.pack(side=tk.LEFT)
            cog.bind("<Button-1>", lambda e, em=_em, sl=_sl: self._open_threshold_settings(em, sl))

        # Spent info (Extra usage only)
        if section.spent_info:
            tk.Label(
                frame,
                text=section.spent_info,
                bg=t.bg, fg=t.fg_dim,
                font=t.font,
                anchor="w",
            ).pack(fill=tk.X)

        # Separator line
        sep_frame = tk.Frame(frame, bg=t.bg, height=1)
        sep_frame.pack(fill=tk.X, pady=(2, 0))
        tk.Label(
            sep_frame,
            text="=" * 80,
            bg=t.bg, fg=t.border,
            font=t.font_separator,
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

        t = theme_mod.current()
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.configure(bg=t.bg)
        win.attributes("-topmost", True)
        self._settings_windows[key] = win

        def _close():
            win.destroy()
            self._settings_windows.pop(key, None)

        win.bind("<Escape>", lambda e: _close())

        outer = tk.Frame(win, bg=t.border, padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)
        inner = tk.Frame(outer, bg=t.bg, padx=POPUP_PADDING, pady=POPUP_PADDING)
        inner.pack(fill=tk.BOTH, expand=True)

        # Title bar with close button
        title_bar = tk.Frame(inner, bg=t.bg)
        title_bar.pack(fill=tk.X, pady=(0, POPUP_PADDING // 2))
        tk.Button(
            title_bar,
            text="✕",
            bg=t.button_bg, fg=t.button_fg,
            activebackground=t.button_active_bg, activeforeground=t.button_fg,
            padx=6, pady=2,
            font=t.font,
            cursor="hand2",
            command=_close,
            **t.button_style_kwargs(),
        ).pack(side=tk.RIGHT)
        tk.Label(
            title_bar,
            text=title,
            bg=t.bg, fg=t.fg,
            font=t.font_bold,
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
        t = theme_mod.current()
        result = self._make_settings_window(f"account_{email}", "Auto-Refresh Settings")
        if result is None:
            return
        win, inner, _close = result

        tk.Label(
            inner,
            text=email,
            bg=t.bg, fg=t.fg_dim,
            font=t.font,
            anchor="w",
        ).pack(fill=tk.X)

        current_val = settings_mod.get_refresh_interval_minutes(email)
        val_label = tk.Label(
            inner,
            text=f"Update every {current_val} minutes",
            bg=t.bg, fg=t.fg,
            font=t.font,
            anchor="w",
        )
        val_label.pack(fill=tk.X, pady=(POPUP_PADDING // 2, 4))

        def on_slide(v):
            val = int(float(v))
            val_label.config(text=f"Update every {val} minutes")

        def on_release(event=None):
            val = int(scale.get())
            settings_mod.set_refresh_interval_minutes(email, val)
            if self._on_refresh_interval_changed_cb:
                self._on_refresh_interval_changed_cb()

        scale = tk.Scale(
            inner,
            from_=1, to=30, resolution=1,
            orient=tk.HORIZONTAL,
            command=on_slide,
            bg=t.bg, fg=t.fg,
            troughcolor=t.bar_bg,
            activebackground=t.button_active_bg,
            highlightthickness=0,
            font=t.font,
            showvalue=False,
            **t.scale_style_kwargs(),
        )
        scale.set(current_val)
        scale.bind("<ButtonRelease-1>", on_release)
        scale.pack(fill=tk.X)

        notif_var = tk.BooleanVar(value=settings_mod.get_notifications_enabled(email))
        notif_cb = tk.Checkbutton(
            inner,
            text="Notifications enabled",
            variable=notif_var,
            bg=t.bg, fg=t.fg,
            selectcolor=t.bar_bg,
            activebackground=t.bg, activeforeground=t.fg,
            font=t.font,
            anchor="w",
            command=lambda: settings_mod.set_notifications_enabled(email, notif_var.get()),
            **t.checkbutton_style_kwargs(),
        )
        notif_cb.pack(fill=tk.X, pady=(POPUP_PADDING // 2, 0))

        self._center_window(win, 380, 220)
        win.focus_force()

    def _open_threshold_settings(self, email: str, section_label: str):
        t = theme_mod.current()
        key = f"threshold_{email}_{section_label}"
        result = self._make_settings_window(key, f"Notification Threshold — {section_label}")
        if result is None:
            return
        win, inner, _close = result

        tk.Label(
            inner,
            text=email,
            bg=t.bg, fg=t.fg_dim,
            font=t.font,
            anchor="w",
        ).pack(fill=tk.X)

        current_val = settings_mod.get_notification_threshold(email, section_label)
        val_label = tk.Label(
            inner,
            text=f"Notify every {current_val}%",
            bg=t.bg, fg=t.fg,
            font=t.font,
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
            bg=t.bg, fg=t.fg,
            troughcolor=t.bar_bg,
            activebackground=t.button_active_bg,
            highlightthickness=0,
            font=t.font,
            showvalue=False,
            **t.scale_style_kwargs(),
        )
        scale.set(current_val)
        scale.pack(fill=tk.X)

        self._center_window(win, 380, 180)
        win.focus_force()

    def _open_theme_selector(self):
        """Open the theme selection window with mini preview cards."""
        result = self._make_settings_window("theme_selector", "Themes")
        if result is None:
            return
        win, inner, _close = result

        t = theme_mod.current()
        themes = theme_mod.list_themes()
        selected_var = tk.StringVar(value=t.name)

        CARD_W = 320
        CARD_H = 72
        CARD_PAD = 6
        MAX_VISIBLE = 4
        scroll_height = MAX_VISIBLE * (CARD_H + CARD_PAD)

        SB_W = 8
        _sb_hover = False
        _drag_start_y = None
        _drag_start_frac = None

        scroll_wrapper = tk.Frame(inner, bg=t.bg)
        scroll_wrapper.pack(fill=tk.X, pady=(0, POPUP_PADDING // 2))

        sb_canvas = tk.Canvas(scroll_wrapper, width=SB_W, height=scroll_height,
                              bg=t.bar_bg, highlightthickness=0, cursor="arrow")
        sb_canvas.pack(side=tk.RIGHT, fill=tk.Y)

        scroll_canvas = tk.Canvas(scroll_wrapper, bg=t.bg, highlightthickness=0, height=scroll_height)
        scroll_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def _update_sb(first, last):
            first, last = float(first), float(last)
            sb_canvas.delete("all")
            h = sb_canvas.winfo_height()
            if h <= 1:
                h = scroll_height
            sb_canvas.create_rectangle(0, 0, SB_W, h, fill=t.bar_bg, outline="")
            if last - first < 1.0:
                y1 = int(first * h)
                y2 = int(last * h)
                color = t.fg if _sb_hover else t.fg_dim
                sb_canvas.create_rectangle(1, y1, SB_W - 1, y2, fill=color, outline="")

        scroll_canvas.configure(yscrollcommand=_update_sb)

        def _sb_button1(event):
            nonlocal _drag_start_y, _drag_start_frac
            h = sb_canvas.winfo_height()
            if h <= 1:
                return
            _drag_start_y = event.y
            _drag_start_frac = scroll_canvas.yview()[0]

        def _sb_motion(event):
            nonlocal _drag_start_y, _drag_start_frac
            if _drag_start_y is None:
                return
            h = sb_canvas.winfo_height()
            if h <= 1:
                return
            dy = event.y - _drag_start_y
            scroll_canvas.yview_moveto(_drag_start_frac + dy / h)

        def _sb_release(event):
            nonlocal _drag_start_y, _drag_start_frac
            _drag_start_y = None
            _drag_start_frac = None

        def _sb_enter(event):
            nonlocal _sb_hover
            _sb_hover = True
            _update_sb(*scroll_canvas.yview())

        def _sb_leave(event):
            nonlocal _sb_hover
            _sb_hover = False
            _update_sb(*scroll_canvas.yview())

        sb_canvas.bind("<Button-1>", _sb_button1)
        sb_canvas.bind("<B1-Motion>", _sb_motion)
        sb_canvas.bind("<ButtonRelease-1>", _sb_release)
        sb_canvas.bind("<Enter>", _sb_enter)
        sb_canvas.bind("<Leave>", _sb_leave)

        list_frame = tk.Frame(scroll_canvas, bg=t.bg)
        scroll_canvas.create_window((0, 0), window=list_frame, anchor="nw")

        themes_dict = {name: th for name, th, _ in themes}
        is_custom_dict = {name: is_custom for name, _, is_custom in themes}
        card_canvases: dict[str, tk.Canvas] = {}

        def _draw_card(canvas: tk.Canvas, th: theme_mod.Theme, selected: bool, is_custom: bool = False):
            canvas.delete("all")
            w, h = CARD_W, CARD_H
            p = 8

            # Background
            canvas.create_rectangle(0, 0, w, h, fill=th.bg, outline="")

            # Border — thicker/brighter when selected
            border_color = th.bar_green if selected else th.border
            border_w = 2 if selected else 1
            canvas.create_rectangle(
                border_w // 2, border_w // 2,
                w - border_w // 2, h - border_w // 2,
                outline=border_color, width=border_w,
            )

            # Theme name (bold)
            canvas.create_text(
                p, p + 2,
                text=th.name,
                fill=th.fg,
                font=(th.font_family, th.font_size_bold, "bold"),
                anchor="nw",
            )

            # Top-right: checkmark (active) and/or "Custom" badge
            right_x = w - p
            if th.name == theme_mod.current().name:
                canvas.create_text(
                    right_x, p + 2,
                    text="✓",
                    fill=th.bar_green,
                    font=(th.font_family, th.font_size_bold, "bold"),
                    anchor="ne",
                )
                right_x -= 18  # shift badge left of checkmark
            if is_custom:
                canvas.create_text(
                    right_x, p + 2,
                    text="Custom",
                    fill=th.fg_dim,
                    font=(th.font_family, max(th.font_size - 2, 7)),
                    anchor="ne",
                )

            # "Current session" label + percentage
            label_y = p + 18
            canvas.create_text(
                p, label_y,
                text="Current session",
                fill=th.fg,
                font=(th.font_family, th.font_size - 1),
                anchor="nw",
            )
            canvas.create_text(
                w - p, label_y,
                text="42%",
                fill=th.bar_green,
                font=(th.font_family, th.font_size - 1, "bold"),
                anchor="ne",
            )

            # Progress bar
            bar_y = label_y + 14
            bar_h = 8
            bar_x1 = p
            bar_x2 = w - p
            canvas.create_rectangle(bar_x1, bar_y, bar_x2, bar_y + bar_h,
                                     fill=th.bar_bg, outline="")
            filled = int((bar_x2 - bar_x1) * 0.42)
            canvas.create_rectangle(bar_x1, bar_y, bar_x1 + filled, bar_y + bar_h,
                                     fill=th.bar_green, outline="")

            # Reset info dim text
            canvas.create_text(
                p, bar_y + bar_h + 5,
                text="Resets 1pm (Europe/Rome)",
                fill=th.fg_dim,
                font=(th.font_family, th.font_size - 2),
                anchor="nw",
            )

        def _select(name: str):
            selected_var.set(name)
            for n, c in card_canvases.items():
                _draw_card(c, themes_dict[n], n == name, is_custom_dict[n])

        # Build cards
        for theme_name, th, is_custom in themes:
            c = tk.Canvas(list_frame, width=CARD_W, height=CARD_H,
                          highlightthickness=0, cursor="hand2")
            c.pack(pady=(0, CARD_PAD))
            card_canvases[theme_name] = c
            _draw_card(c, th, theme_name == t.name, is_custom)
            c.bind("<Button-1>", lambda e, n=theme_name: _select(n))

        list_frame.update_idletasks()
        scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))
        sb_canvas.after(10, lambda: _update_sb(*scroll_canvas.yview()))

        def _on_mousewheel(event):
            scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        scroll_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        original_close = _close

        def _close_with_unbind():
            scroll_canvas.unbind_all("<MouseWheel>")
            original_close()

        win.bind("<Escape>", lambda e: _close_with_unbind())

        # Patch the ✕ button in the title bar to also unbind mousewheel
        title_bar = inner.winfo_children()[0]
        for child in title_bar.winfo_children():
            if isinstance(child, tk.Button) and child.cget("text") == "✕":
                child.configure(command=_close_with_unbind)
                break

        # Apply button
        tk.Button(
            inner,
            text="Apply",
            bg=t.button_bg, fg=t.button_fg,
            activebackground=t.button_active_bg, activeforeground=t.button_fg,
            padx=16, pady=4,
            font=t.font,
            cursor="hand2",
            command=lambda: _apply(),
            **t.button_style_kwargs(),
        ).pack(side=tk.RIGHT)

        def _apply():
            name = selected_var.get()
            theme_mod.apply(name)
            settings_mod.set_theme_name(name)
            self.apply_theme()
            self._rebuild_content()
            _close_with_unbind()

        win_h = scroll_height + POPUP_PADDING * 4 + 60
        self._center_window(win, CARD_W + POPUP_PADDING * 2 + 20, win_h)
        win.focus_force()

    def _rebuild_content(self):
        """Re-render content with the current theme."""
        self.apply_theme()
        if self._last_accounts is not None:
            self.show_usage(self._last_accounts)
        else:
            self.show_loading()

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
            return
        if self._refreshing:
            self.win.after(200, self._poll_focus)
            return
        focused = self.win.focus_get()
        if focused is None:
            self.hide()
            return
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
        self.win.after(200, self._poll_focus)

    def show(self, steal_focus: bool = True):
        self._reposition_and_resize()
        if steal_focus:
            self.win.deiconify()
            self.win.lift()
            self.win.focus_force()
            self._start_focus_poll()
        else:
            self.win.attributes("-topmost", True)
        self._visible = True

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
