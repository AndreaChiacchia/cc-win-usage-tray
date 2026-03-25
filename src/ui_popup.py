"""Tkinter popup window with usage progress bars."""

import ctypes
import re
import tkinter as tk
import time
from datetime import datetime

import settings as settings_mod
import theme as theme_mod
import time_utils
from version import __version__
from config import (
    POPUP_WIDTH, POPUP_PADDING, TASKBAR_OFFSET,
    COLOR_GREEN_MAX, COLOR_YELLOW_MAX,
    BAR_HEIGHT, ANIM_FRAME_MS, ANIM_BAR_DURATION_MS,
    ANIM_SHIMMER_WIDTH, ANIM_SHIMMER_SPEED,
    POPUP_MAX_CONTENT_HEIGHT,
)
from usage_parser import UsageSection, AccountUsage
from stats_panel import StatsPanel


def _lighten_color(hex_color: str, factor: float = 0.3) -> str:
    """Blend a hex color toward white by factor (0=unchanged, 1=white)."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


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
        self._relative_timer_id = None

        # Animation state
        # Key: (email, section_label) → {"canvas", "pct_label", "current_pct", "color", "reset_label"}
        self._bar_widgets: dict[tuple[str, str], dict] = {}
        # Key: email → the sync timestamp Label
        self._sync_labels: dict[str, tk.Label] = {}
        self._shimmer_active = False
        self._shimmer_after_id = None
        self._shimmer_x = 0
        self._anim_after_ids: list = []
        self._anim_generation = 0
        self._last_active_email: str | None = None
        self._syncing_dot_active = False
        self._syncing_dot_after_id = None
        self._syncing_dot_phase = 0
        self._last_refresh_error: str | None = None

        # Scroll state
        self._sb_hover = False
        self._drag_start_y = None
        self._drag_start_frac = None

        # Drag state
        self._drag_data = {"x": 0, "y": 0}
        self._custom_position: tuple[int, int] | None = settings_mod.get_popup_position()
        self._screen_check_id = None

        # Monitor-relative position tracking (survives monitor layout changes)
        self._last_vscreen: tuple[int, int, int, int] | None = None
        monitor_info = settings_mod.get_popup_monitor_info()
        if monitor_info:
            self._position_monitor_name: str | None = monitor_info[0]
            self._position_monitor_offset: tuple[int, int] | None = monitor_info[1]
        else:
            self._position_monitor_name = None
            self._position_monitor_offset = None

        # Always-on-top state (default True preserves existing behavior)
        self._always_on_top: bool = settings_mod.get_always_on_top()

        t = theme_mod.current()

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.configure(bg=t.bg)
        self.win.attributes("-topmost", self._always_on_top)
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
            cursor="fleur",
        )
        self._title_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Drag bindings on title bar and label
        for widget in (self._top, self._title_label):
            widget.bind("<ButtonPress-1>", self._on_drag_start)
            widget.bind("<B1-Motion>", self._on_drag_motion)
            widget.bind("<ButtonRelease-1>", self._on_drag_end)
        self._top.configure(cursor="fleur")

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

        # Scrollable content area
        _SB_W = 8
        self._scroll_wrapper = tk.Frame(self._inner, bg=t.bg)
        self._scroll_wrapper.pack(fill=tk.X)

        # Scrollbar canvas — always packed RIGHT so scroll_canvas expand=True works correctly;
        # width=0 hides it, width=_SB_W shows it.
        self._sb_canvas = tk.Canvas(
            self._scroll_wrapper, width=0, height=1,
            bg=t.bar_bg, highlightthickness=0, cursor="arrow",
        )
        self._sb_canvas.pack(side=tk.RIGHT, fill=tk.Y)

        self._scroll_canvas = tk.Canvas(
            self._scroll_wrapper, bg=t.bg, highlightthickness=0, height=1,
        )
        self._scroll_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._content_frame = tk.Frame(self._scroll_canvas, bg=t.bg)
        self._scroll_canvas_window = self._scroll_canvas.create_window(
            (0, 0), window=self._content_frame, anchor="nw",
        )

        self._scroll_canvas.configure(yscrollcommand=self._update_scroll_sb)
        self._scroll_canvas.bind("<Configure>", self._on_scroll_canvas_configure)
        self._sb_canvas.bind("<Button-1>", self._sb_button1)
        self._sb_canvas.bind("<B1-Motion>", self._sb_motion)
        self._sb_canvas.bind("<ButtonRelease-1>", self._sb_release)
        self._sb_canvas.bind("<Enter>", self._sb_enter)
        self._sb_canvas.bind("<Leave>", self._sb_leave)

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

        self._stats_panel = StatsPanel(root, self.win)

    # ------------------------------------------------------------------
    # Scroll helpers
    # ------------------------------------------------------------------

    def _on_scroll_canvas_configure(self, event):
        """Keep content_frame width in sync with scroll canvas width."""
        self._scroll_canvas.itemconfigure(self._scroll_canvas_window, width=event.width)

    def _update_scroll_sb(self, first, last):
        first, last = float(first), float(last)
        t = theme_mod.current()
        self._sb_canvas.delete("all")
        h = self._sb_canvas.winfo_height()
        if h <= 1:
            return
        self._sb_canvas.create_rectangle(0, 0, 8, h, fill=t.bar_bg, outline="")
        if last - first < 1.0:
            y1 = int(first * h)
            y2 = int(last * h)
            color = t.fg if self._sb_hover else t.fg_dim
            self._sb_canvas.create_rectangle(1, y1, 7, y2, fill=color, outline="")

    def _sb_button1(self, event):
        h = self._sb_canvas.winfo_height()
        if h <= 1:
            return
        self._drag_start_y = event.y
        self._drag_start_frac = self._scroll_canvas.yview()[0]

    def _sb_motion(self, event):
        if self._drag_start_y is None:
            return
        h = self._sb_canvas.winfo_height()
        if h <= 1:
            return
        dy = event.y - self._drag_start_y
        self._scroll_canvas.yview_moveto(self._drag_start_frac + dy / h)

    def _sb_release(self, event):
        self._drag_start_y = None
        self._drag_start_frac = None

    def _sb_enter(self, event):
        self._sb_hover = True
        self._update_scroll_sb(*self._scroll_canvas.yview())

    def _sb_leave(self, event):
        self._sb_hover = False
        self._update_scroll_sb(*self._scroll_canvas.yview())

    def _on_content_mousewheel(self, event):
        self._scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_mousewheel_to_content(self):
        """Recursively bind mousewheel on all content widgets to the scroll canvas."""
        def _bind(widget):
            widget.bind("<MouseWheel>", self._on_content_mousewheel)
            for child in widget.winfo_children():
                _bind(child)
        _bind(self._content_frame)
        self._scroll_canvas.bind("<MouseWheel>", self._on_content_mousewheel)

    def _update_scroll_height(self):
        """Cap scroll canvas height and show/hide the custom scrollbar based on content size."""
        self.win.update_idletasks()
        content_h = self._content_frame.winfo_reqheight()
        visible_h = min(content_h, POPUP_MAX_CONTENT_HEIGHT)

        self._scroll_canvas.configure(height=visible_h)
        self._scroll_canvas.configure(scrollregion=(0, 0, 0, content_h))

        if content_h > POPUP_MAX_CONTENT_HEIGHT:
            self._sb_canvas.configure(width=8, height=visible_h)
            self._bind_mousewheel_to_content()
            self.win.after(10, lambda: self._update_scroll_sb(*self._scroll_canvas.yview()))
        else:
            self._sb_canvas.configure(width=0)

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
        self._scroll_wrapper.configure(bg=t.bg)
        self._scroll_canvas.configure(bg=t.bg)
        self._sb_canvas.configure(bg=t.bar_bg)
        self._content_frame.configure(bg=t.bg)
        self._bottom.configure(bg=t.bg)
        self._version_label.configure(bg=t.bg, fg=t.fg_dim, font=t.font)
        self._refresh_btn.configure(
            bg=t.button_bg, fg=t.button_fg,
            activebackground=t.button_active_bg, activeforeground=t.button_fg,
            font=t.font,
            **t.button_style_kwargs(),
        )
        self._stats_panel.apply_theme()

    def _clear_content(self):
        self._stop_shimmer()
        self._stop_syncing_dots()
        self._cancel_all_anims()
        self._bar_widgets.clear()
        self._sync_labels.clear()
        for widget in self._content_frame.winfo_children():
            widget.destroy()

    def show_loading(self):
        """Display a loading indicator. If bars exist, shimmer over them; otherwise show text."""
        if not self._bar_widgets:
            # No saved data — show the text fallback
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
        else:
            # Saved data exists — shimmer or dots depending on per-account setting
            self._refresh_btn.configure(state=tk.DISABLED)
            if self._last_active_email and settings_mod.get_shimmer_enabled(self._last_active_email):
                for lbl in self._sync_labels.values():
                    if lbl.winfo_exists():
                        lbl.configure(text="  Syncing...")
                self._start_shimmer()
            else:
                self._start_syncing_dots()

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
        """Display parsed usage data. Updates in-place if structure matches, else full rebuild."""
        self._last_accounts = accounts
        self._stop_shimmer()
        self._stop_syncing_dots()
        self._cancel_all_anims()

        if not accounts:
            self.show_error("No usage data available")
            return

        if self._can_update_in_place(accounts):
            self._update_in_place(accounts)
        else:
            self._full_rebuild(accounts)

    def _can_update_in_place(self, accounts: dict[str, AccountUsage]) -> bool:
        """Return True if we can update existing widgets without rebuilding."""
        if not self._bar_widgets:
            return False
        current_active = next((e for e, a in accounts.items() if a.is_active), None)
        if current_active != self._last_active_email:
            return False
        for acc in accounts.values():
            if acc.usage.error:
                return False
        new_keys = set()
        for email, acc in accounts.items():
            for section in acc.usage.sections:
                new_keys.add((email, section.label))
        return new_keys == set(self._bar_widgets.keys())

    def _update_in_place(self, accounts: dict[str, AccountUsage]):
        """Update label text and animate bar fills without rebuilding widgets."""
        for email, acc in accounts.items():
            # Update sync label
            if email in self._sync_labels and self._sync_labels[email].winfo_exists():
                use_relative = settings_mod.get_relative_time_enabled(email)
                if use_relative:
                    ts_text = f"  {time_utils.format_last_sync_relative(acc.last_updated)}"
                else:
                    try:
                        dt = datetime.fromisoformat(acc.last_updated)
                        ts_text = f"  Last sync: {dt.strftime('%Y-%m-%d %H:%M:%S')}"
                    except Exception:
                        ts_text = f"  Last sync: {acc.last_updated}"
                if self._last_refresh_error:
                    ts_text += "  \u26a0"
                self._sync_labels[email].configure(text=ts_text)

            for section in acc.usage.sections:
                key = (email, section.label)
                if key not in self._bar_widgets:
                    continue
                refs = self._bar_widgets[key]
                new_pct = float(section.percentage)
                new_color = _bar_color(section.percentage)
                old_pct = refs["current_pct"]

                # Update reset label if tracked
                reset_lbl = refs.get("reset_label")
                if reset_lbl and reset_lbl.winfo_exists():
                    if section.reset_info:
                        if settings_mod.get_relative_time_enabled(email):
                            display_reset = time_utils.format_reset_relative(section.reset_info)
                        else:
                            display_reset = section.reset_info
                        reset_lbl.configure(text=display_reset)
                        reset_lbl.master.pack(fill=tk.X, pady=(2, 0))
                    else:
                        reset_lbl.configure(text="Usage data may be outdated")

                # Extract old/new spent for animation
                old_spent_info = refs.get("spent_info")
                new_spent_info = section.spent_info
                old_spent = new_spent = spent_cap = None
                if old_spent_info and new_spent_info:
                    m_old = re.search(r'\$([\d.]+)\s*/\s*\$([\d.]+)', old_spent_info)
                    m_new = re.search(r'\$([\d.]+)\s*/\s*\$([\d.]+)', new_spent_info)
                    if m_old and m_new:
                        old_spent = float(m_old.group(1))
                        new_spent = float(m_new.group(1))
                        spent_cap = float(m_new.group(2))
                refs["spent_info"] = new_spent_info

                pct_changed = old_pct != new_pct
                spent_changed = (old_spent is not None and old_spent != new_spent)

                if pct_changed or spent_changed:
                    self._animate_bar(
                        key, old_pct, new_pct, new_color,
                        old_spent, new_spent, spent_cap,
                    )
                else:
                    refs["color"] = new_color
                    if refs["pct_label"].winfo_exists():
                        refs["pct_label"].configure(
                            text=f"{section.percentage:3d}%", fg=new_color
                        )
                    # Snap label text in case spent_info was added/removed
                    section_lbl = refs.get("section_label")
                    if section_lbl and section_lbl.winfo_exists():
                        label_base = refs.get("label_text", section.label)
                        lbl_text = (
                            f"{label_base} · {new_spent_info}"
                            if new_spent_info else label_base
                        )
                        section_lbl.configure(text=lbl_text)

        self._refresh_btn.configure(state=tk.NORMAL)
        self._reposition_and_resize()

    def _full_rebuild(self, accounts: dict[str, AccountUsage]):
        """Full widget rebuild (clears and recreates everything)."""
        t = theme_mod.current()
        self._clear_content()
        self._scroll_canvas.yview_moveto(0)

        # Sort accounts to put active one first
        sorted_emails = sorted(accounts.keys(), key=lambda e: (not accounts[e].is_active, e))
        self._last_active_email = next((e for e in sorted_emails if accounts[e].is_active), None)

        for idx, email in enumerate(sorted_emails):
            acc = accounts[email]

            # Account Header
            header_row = tk.Frame(self._content_frame, bg=t.bg)
            header_row.pack(fill=tk.X, pady=(4, 0))
            header_label = tk.Label(
                header_row,
                text=f"> {email}",
                bg=t.bg, fg=t.fg_dim,
                font=t.font_bold,
                anchor="w",
                cursor="hand2",
            )
            header_label.pack(side=tk.LEFT)
            header_label.bind("<Enter>", lambda e, em=email: self._on_account_hover_enter(em))
            header_label.bind("<Leave>", lambda e: self._on_account_hover_leave())
            if acc.is_active and len(accounts) > 1:
                tk.Label(
                    header_row,
                    text=" ✦",
                    bg=t.bg, fg=t.fg,
                    font=t.font_bold,
                    anchor="w",
                ).pack(side=tk.LEFT)

            # Timestamp row with cog for account settings
            use_relative = settings_mod.get_relative_time_enabled(email)
            if use_relative:
                ts_label = f"  {time_utils.format_last_sync_relative(acc.last_updated)}"
            else:
                try:
                    dt = datetime.fromisoformat(acc.last_updated)
                    ts_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    ts_str = acc.last_updated
                ts_label = f"  Last sync: {ts_str}"
            if self._last_refresh_error:
                ts_label += "  \u26a0"

            sync_row = tk.Frame(self._content_frame, bg=t.bg)
            sync_row.pack(fill=tk.X)
            sync_lbl = tk.Label(
                sync_row,
                text=ts_label,
                bg=t.bg, fg=t.fg_dim,
                font=t.font,
                anchor="w",
            )
            sync_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._sync_labels[email] = sync_lbl

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
                is_last_account = (idx == len(sorted_emails) - 1)
                for i, section in enumerate(acc.usage.sections):
                    key = (email, section.label)
                    widget_refs = self._add_section(
                        self._content_frame, section,
                        email=email, key=key,
                        top_pad=20 if i == 0 else 2,
                        is_last=(is_last_account and i == len(acc.usage.sections) - 1),
                    )
                    self._bar_widgets[key] = widget_refs

            # Divider between accounts and before the bottom bar
            tk.Frame(self._content_frame, bg=t.border, height=1).pack(fill=tk.X, pady=(20, 12))

        self._refresh_btn.configure(state=tk.NORMAL)
        self._reposition_and_resize()

    # ------------------------------------------------------------------
    # Stats panel hover
    # ------------------------------------------------------------------

    def _on_account_hover_enter(self, email: str):
        sections = []
        if self._last_accounts and email in self._last_accounts:
            sections = self._last_accounts[email].usage.sections
        self._stats_panel.show(email, sections)

    def _on_account_hover_leave(self):
        self._stats_panel.hide()

    # ------------------------------------------------------------------
    # Shimmer animation
    # ------------------------------------------------------------------

    def _start_shimmer(self):
        if self._shimmer_active:
            return
        self._shimmer_active = True
        self._shimmer_x = 0
        self._tick_shimmer()

    def _tick_shimmer(self):
        if not self._shimmer_active:
            return
        self._shimmer_x += ANIM_SHIMMER_SPEED

        for refs in self._bar_widgets.values():
            canvas = refs["canvas"]
            if not canvas.winfo_exists():
                continue
            pct = refs["current_pct"]
            color = refs["color"]

            w = canvas.winfo_width()
            if w <= 1:
                w = 300
            filled_w = int(w * pct / 100)
            canvas.delete("all")

            if filled_w > 0:
                canvas.create_rectangle(
                    0, 0, filled_w, BAR_HEIGHT, fill=color, outline=""
                )
                wrap_width = filled_w + ANIM_SHIMMER_WIDTH
                sx = self._shimmer_x % wrap_width - ANIM_SHIMMER_WIDTH
                band_x1 = max(0, sx)
                band_x2 = min(filled_w, sx + ANIM_SHIMMER_WIDTH)
                if band_x1 < band_x2:
                    shimmer_color = _lighten_color(color)
                    canvas.create_rectangle(
                        band_x1, 0, band_x2, BAR_HEIGHT,
                        fill=shimmer_color, outline=""
                    )

        self._shimmer_after_id = self.root.after(ANIM_FRAME_MS, self._tick_shimmer)

    def _stop_shimmer(self):
        self._shimmer_active = False
        if self._shimmer_after_id is not None:
            try:
                self.root.after_cancel(self._shimmer_after_id)
            except Exception:
                pass
            self._shimmer_after_id = None
        # Redraw bars at current static state
        for key in self._bar_widgets:
            self._redraw_bar_static(key)

    def _start_syncing_dots(self):
        if self._syncing_dot_active:
            return
        self._syncing_dot_phase = 0
        self._syncing_dot_active = True
        self._tick_syncing_dots()

    def _tick_syncing_dots(self):
        if not self._syncing_dot_active:
            return
        text = "  Syncing" + "." * (self._syncing_dot_phase + 1)
        for lbl in self._sync_labels.values():
            if lbl.winfo_exists():
                lbl.configure(text=text)
        self._syncing_dot_phase = (self._syncing_dot_phase + 1) % 3
        self._syncing_dot_after_id = self.root.after(400, self._tick_syncing_dots)

    def _stop_syncing_dots(self):
        self._syncing_dot_active = False
        if self._syncing_dot_after_id is not None:
            try:
                self.root.after_cancel(self._syncing_dot_after_id)
            except Exception:
                pass
            self._syncing_dot_after_id = None

    # ------------------------------------------------------------------
    # Bar fill animation
    # ------------------------------------------------------------------

    def _redraw_bar_static(self, key: tuple):
        """Redraw a bar canvas at its current percentage without shimmer."""
        if key not in self._bar_widgets:
            return
        refs = self._bar_widgets[key]
        canvas = refs["canvas"]
        if not canvas.winfo_exists():
            return
        pct = refs["current_pct"]
        color = refs["color"]
        w = canvas.winfo_width()
        if w <= 1:
            w = 300
        canvas.delete("all")
        filled_w = int(w * pct / 100)
        if filled_w > 0:
            canvas.create_rectangle(0, 0, filled_w, BAR_HEIGHT, fill=color, outline="")

    def _cancel_all_anims(self):
        self._anim_generation += 1
        for aid in self._anim_after_ids:
            try:
                self.root.after_cancel(aid)
            except Exception:
                pass
        self._anim_after_ids.clear()

    def _animate_bar(
        self, key: tuple, old_pct: float, new_pct: float, new_color: str,
        old_spent: float | None = None, new_spent: float | None = None,
        spent_cap: float | None = None,
    ):
        """Animate bar fill from old_pct to new_pct over ANIM_BAR_DURATION_MS."""
        start = time.monotonic()
        duration = ANIM_BAR_DURATION_MS / 1000.0
        gen = self._anim_generation
        animate_spent = (old_spent is not None and new_spent is not None and spent_cap is not None)

        def _tick():
            if gen != self._anim_generation:
                return
            if key not in self._bar_widgets:
                return
            elapsed = time.monotonic() - start
            t_val = min(elapsed / duration, 1.0)
            progress = 1.0 - (1.0 - t_val) ** 2  # ease-out-quad
            pct = old_pct + (new_pct - old_pct) * progress

            refs = self._bar_widgets[key]
            refs["current_pct"] = pct
            refs["color"] = new_color
            self._redraw_bar_static(key)

            if refs["pct_label"].winfo_exists():
                display = round(pct) if t_val < 1.0 else int(new_pct)
                refs["pct_label"].configure(text=f"{display:3d}%", fg=new_color)

            if animate_spent:
                section_lbl = refs.get("section_label")
                if section_lbl and section_lbl.winfo_exists():
                    interp_spent = old_spent + (new_spent - old_spent) * progress
                    if t_val >= 1.0:
                        interp_spent = new_spent
                    refs["current_spent"] = interp_spent
                    label_base = refs.get("label_text", key[1])
                    section_lbl.configure(
                        text=f"{label_base} · ${interp_spent:.2f} / ${spent_cap:.2f} spent"
                    )

            if t_val < 1.0:
                aid = self.root.after(ANIM_FRAME_MS, _tick)
                self._anim_after_ids.append(aid)
            else:
                refs["current_pct"] = new_pct
                if not animate_spent:
                    section_lbl = refs.get("section_label")
                    new_spent_info = refs.get("spent_info")
                    if section_lbl and section_lbl.winfo_exists():
                        label_base = refs.get("label_text", key[1])
                        lbl_text = (
                            f"{label_base} · {new_spent_info}"
                            if new_spent_info else label_base
                        )
                        section_lbl.configure(text=lbl_text)

        aid = self.root.after(0, _tick)
        self._anim_after_ids.append(aid)

    def _add_section(
        self,
        parent: tk.Frame,
        section: UsageSection,
        email: str,
        key: tuple,
        top_pad: int = 2,
        is_last: bool = False,
    ) -> dict:
        """Add a usage section with label, canvas bar, and reset info. Returns widget refs."""
        t = theme_mod.current()
        frame = tk.Frame(parent, bg=t.bg, pady=0)
        frame.pack(fill=tk.X, pady=(top_pad, 0))

        # Section label (includes spent_info for Extra usage)
        label_base = section.label
        label_text = label_base
        if section.spent_info:
            label_text += f" · {section.spent_info}"
        section_lbl = tk.Label(
            frame,
            text=label_text,
            bg=t.bg, fg=t.fg,
            font=t.font_bold,
            anchor="w",
        )
        section_lbl.pack(fill=tk.X)

        # Canvas progress bar + percentage
        bar_row = tk.Frame(frame, bg=t.bg)
        bar_row.pack(fill=tk.X, pady=(2, 0))

        color = _bar_color(section.percentage)
        pct = float(section.percentage)

        canvas = tk.Canvas(bar_row, height=BAR_HEIGHT, bg=t.bar_bg, highlightthickness=0)
        canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)
        canvas.bind("<Configure>", lambda e, k=key: self._redraw_bar_static(k))

        pct_lbl = tk.Label(
            bar_row,
            text=f"{section.percentage:3d}%",
            bg=t.bg, fg=color,
            font=t.font_bold,
            width=5,
            anchor="e",
        )
        pct_lbl.pack(side=tk.RIGHT)

        # Reset info row with cog
        _em = email
        _sl = section.label
        if section.reset_info:
            if settings_mod.get_relative_time_enabled(email):
                display_reset = time_utils.format_reset_relative(section.reset_info)
            else:
                display_reset = section.reset_info
        else:
            display_reset = "Usage data may be outdated"
        reset_row = tk.Frame(frame, bg=t.bg)
        reset_row.pack(fill=tk.X, pady=(2, 0))
        reset_lbl = tk.Label(
            reset_row,
            text=display_reset,
            bg=t.bg, fg=t.fg_dim,
            font=t.font,
            anchor="w",
        )
        reset_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
        cog = tk.Label(
            reset_row, text="⚙",
            bg=t.bg, fg=t.fg_dim,
            font=t.font, cursor="hand2",
        )
        cog.pack(side=tk.RIGHT)
        cog.bind("<Button-1>", lambda e, em=_em, sl=_sl: self._open_threshold_settings(em, sl))

        # Separator line (omitted after the last section of the last account)
        if not is_last:
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

        # Parse initial spent value for animation tracking
        current_spent = None
        if section.spent_info:
            m = re.search(r'\$([\d.]+)\s*/\s*\$([\d.]+)', section.spent_info)
            if m:
                current_spent = float(m.group(1))

        return {
            "canvas": canvas,
            "pct_label": pct_lbl,
            "current_pct": pct,
            "color": color,
            "reset_label": reset_lbl,
            "section_label": section_lbl,
            "label_text": label_base,
            "spent_info": section.spent_info,
            "current_spent": current_spent,
        }

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
        win.attributes("-topmost", self._always_on_top)
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

    def _position_beside_popup(self, win: tk.Toplevel, w: int, h: int):
        win.update_idletasks()
        popup_x = self.win.winfo_x()
        popup_y = self.win.winfo_y()

        x = popup_x - w - 4
        if x < 0:
            x = popup_x + self.win.winfo_width() + 4

        screen_h = self.root.winfo_screenheight()
        y = max(0, min(popup_y, screen_h - h))

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

        rel_var = tk.BooleanVar(value=settings_mod.get_relative_time_enabled(email))

        def _on_relative_toggle():
            settings_mod.set_relative_time_enabled(email, rel_var.get())
            self._rebuild_content()

        rel_cb = tk.Checkbutton(
            inner,
            text="Show relative times",
            variable=rel_var,
            bg=t.bg, fg=t.fg,
            selectcolor=t.bar_bg,
            activebackground=t.bg, activeforeground=t.fg,
            font=t.font,
            anchor="w",
            command=_on_relative_toggle,
            **t.checkbutton_style_kwargs(),
        )
        rel_cb.pack(fill=tk.X, pady=(POPUP_PADDING // 2, 0))

        shimmer_var = tk.BooleanVar(value=settings_mod.get_shimmer_enabled(email))
        shimmer_cb = tk.Checkbutton(
            inner,
            text="Shimmer animation",
            variable=shimmer_var,
            bg=t.bg, fg=t.fg,
            selectcolor=t.bar_bg,
            activebackground=t.bg, activeforeground=t.fg,
            font=t.font,
            anchor="w",
            command=lambda: settings_mod.set_shimmer_enabled(email, shimmer_var.get()),
            **t.checkbutton_style_kwargs(),
        )
        shimmer_cb.pack(fill=tk.X, pady=(POPUP_PADDING // 2, 0))

        self._position_beside_popup(win, 380, 280)
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

        self._position_beside_popup(win, 380, 180)
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
        self._position_beside_popup(win, CARD_W + POPUP_PADDING * 2 + 20, win_h)
        win.focus_force()

    def _rebuild_content(self):
        """Re-render content with the current theme."""
        self.apply_theme()
        self._clear_content()  # force full rebuild after theme change
        if self._last_accounts is not None:
            self.show_usage(self._last_accounts)
        else:
            self.show_loading()

    def _start_relative_timer(self):
        self._cancel_relative_timer()
        self._relative_timer_id = self.root.after(60_000, self._tick_relative)

    def _refresh_sync_labels(self):
        """Update sync label text in-place without rebuilding widgets."""
        if not self._last_accounts:
            return
        for email, acc in self._last_accounts.items():
            lbl = self._sync_labels.get(email)
            if lbl and lbl.winfo_exists():
                if settings_mod.get_relative_time_enabled(email):
                    ts = f"  {time_utils.format_last_sync_relative(acc.last_updated)}"
                else:
                    try:
                        dt = datetime.fromisoformat(acc.last_updated)
                        ts = f"  Last sync: {dt.strftime('%Y-%m-%d %H:%M:%S')}"
                    except Exception:
                        ts = f"  Last sync: {acc.last_updated}"
                if self._last_refresh_error:
                    ts += "  \u26a0"
                lbl.configure(text=ts)

    def _tick_relative(self):
        if not self._visible or self._last_accounts is None:
            return
        if any(settings_mod.get_relative_time_enabled(em) for em in self._last_accounts):
            self._refresh_sync_labels()
        self._start_relative_timer()

    def _cancel_relative_timer(self):
        if self._relative_timer_id:
            self.root.after_cancel(self._relative_timer_id)
            self._relative_timer_id = None

    # ------------------------------------------------------------------

    def _reposition_and_resize(self):
        """Position popup above taskbar (or at saved custom position)."""
        self._update_scroll_height()
        self.win.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        if not self._visible:
            # Window is withdrawn — force height recalc via 1px trick
            self.win.geometry(f"{POPUP_WIDTH}x1")
            self.win.update_idletasks()

        req_h = self.win.winfo_reqheight()

        had_custom = bool(self._custom_position)
        if self._custom_position:
            x, y = self._custom_position
        else:
            x = screen_w - POPUP_WIDTH - 8
            y = screen_h - req_h - TASKBAR_OFFSET

        self.win.geometry(f"{POPUP_WIDTH}x{req_h}+{x}+{y}")

        if not had_custom:
            self._save_monitor_relative_position(x, y)

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
        allowed = {self.win, self._stats_panel.win} | {sw for sw in self._settings_windows.values() if sw.winfo_exists()}
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
            self.win.attributes("-topmost", self._always_on_top)
        self._visible = True
        self._refresh_sync_labels()
        self._start_relative_timer()
        self._start_screen_check()
        # If a refresh is in progress and bars exist, start shimmer or dots
        if self._refreshing and self._bar_widgets:
            self._refresh_btn.configure(state=tk.DISABLED)
            if self._last_active_email and settings_mod.get_shimmer_enabled(self._last_active_email):
                if not self._shimmer_active:
                    for lbl in self._sync_labels.values():
                        if lbl.winfo_exists():
                            lbl.configure(text="  Syncing...")
                    self._start_shimmer()
            elif not self._syncing_dot_active:
                self._start_syncing_dots()

    def hide(self):
        self.win.withdraw()
        self._visible = False
        self._cancel_relative_timer()
        self._stop_screen_check()
        self._stats_panel.force_hide()

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

    # ------------------------------------------------------------------
    # Monitor-relative position helpers
    # ------------------------------------------------------------------

    def _get_monitor_info_for_point(self, x: int, y: int):
        """Return (device_name, work_rect) for the monitor containing (x, y).

        work_rect is (left, top, right, bottom) of the working area.
        Returns None if the Win32 call fails.
        """
        try:
            user32 = ctypes.windll.user32

            class RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                             ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

            class MONITORINFOEX(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_ulong),
                             ("rcMonitor", RECT),
                             ("rcWork", RECT),
                             ("dwFlags", ctypes.c_ulong),
                             ("szDevice", ctypes.c_wchar * 32)]

            MONITOR_DEFAULTTONEAREST = 2
            hmon = user32.MonitorFromPoint(ctypes.wintypes.POINT(x, y), MONITOR_DEFAULTTONEAREST)
            info = MONITORINFOEX()
            info.cbSize = ctypes.sizeof(MONITORINFOEX)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
                work = info.rcWork
                return (info.szDevice, (work.left, work.top, work.right, work.bottom))
        except Exception:
            pass
        return None

    def _find_work_area_by_name(self, device_name: str):
        """Return work_rect (left, top, right, bottom) for the named monitor, or None."""
        try:
            user32 = ctypes.windll.user32

            class RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                             ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

            class MONITORINFOEX(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_ulong),
                             ("rcMonitor", RECT),
                             ("rcWork", RECT),
                             ("dwFlags", ctypes.c_ulong),
                             ("szDevice", ctypes.c_wchar * 32)]

            results = []

            def _callback(hmon, hdc, lprect, lparam):
                info = MONITORINFOEX()
                info.cbSize = ctypes.sizeof(MONITORINFOEX)
                if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
                    results.append((info.szDevice, info.rcWork))
                return 1

            MonitorEnumProc = ctypes.WINFUNCTYPE(
                ctypes.c_bool,
                ctypes.c_ulong, ctypes.c_ulong,
                ctypes.POINTER(RECT), ctypes.c_double)
            user32.EnumDisplayMonitors(None, None, MonitorEnumProc(_callback), 0)

            for name, work in results:
                if name == device_name:
                    return (work.left, work.top, work.right, work.bottom)
        except Exception:
            pass
        return None

    def _save_monitor_relative_position(self, x: int, y: int):
        """Compute and persist the popup's offset from its monitor's working area."""
        info = self._get_monitor_info_for_point(x, y)
        if info:
            monitor_name, (wl, wt, _wr, _wb) = info
            self._position_monitor_name = monitor_name
            self._position_monitor_offset = (x - wl, y - wt)
            settings_mod.set_popup_monitor_info(monitor_name, x - wl, y - wt)

    # ------------------------------------------------------------------
    # Drag support
    # ------------------------------------------------------------------

    def _on_drag_start(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _on_drag_motion(self, event):
        x = self.win.winfo_x() + (event.x - self._drag_data["x"])
        y = self.win.winfo_y() + (event.y - self._drag_data["y"])
        self.win.geometry(f"+{x}+{y}")
        self._custom_position = (x, y)

    def _on_drag_end(self, event):
        if self._custom_position:
            settings_mod.set_popup_position(*self._custom_position)
            self._save_monitor_relative_position(*self._custom_position)

    # ------------------------------------------------------------------
    # Monitor-change guard
    # ------------------------------------------------------------------

    def _ensure_on_screen(self):
        """Reposition popup if it has drifted off-screen (e.g. monitor disconnected)."""
        if not self._visible:
            return
        try:
            user32 = ctypes.windll.user32
            vx = user32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
            vy = user32.GetSystemMetrics(77)   # SM_YVIRTUALSCREEN
            vw = user32.GetSystemMetrics(78)   # SM_CXVIRTUALSCREEN
            vh = user32.GetSystemMetrics(79)   # SM_CYVIRTUALSCREEN
        except Exception:
            self._screen_check_id = self.root.after(2500, self._ensure_on_screen)
            return

        new_vscreen = (vx, vy, vw, vh)
        vscreen_changed = (self._last_vscreen is not None
                           and self._last_vscreen != new_vscreen)
        self._last_vscreen = new_vscreen

        wx = self.win.winfo_x()
        wy = self.win.winfo_y()
        ww = self.win.winfo_width()
        wh = self.win.winfo_height()

        # Require at least 50px of the popup to be inside the virtual desktop
        margin = 50
        on_screen = (
            wx + ww > vx + margin
            and wx < vx + vw - margin
            and wy + wh > vy + margin
            and wy < vy + vh - margin
        )

        if not on_screen:
            # Popup is off-screen (monitor disconnected) — reset to default
            self._custom_position = None
            self._position_monitor_name = None
            self._position_monitor_offset = None
            settings_mod.clear_popup_position()
            self._reposition_and_resize()
            # Pin the new position and track it monitor-relative
            new_x = self.win.winfo_x()
            new_y = self.win.winfo_y()
            self._custom_position = (new_x, new_y)
            settings_mod.set_popup_position(new_x, new_y)
            self._save_monitor_relative_position(new_x, new_y)
        elif vscreen_changed and self._position_monitor_name and self._position_monitor_offset:
            # Monitor layout changed but popup is still on-screen.
            # The absolute coords may now point to a different monitor — recompute
            # from the monitor-relative offset against the monitor's new working area.
            new_work = self._find_work_area_by_name(self._position_monitor_name)
            if new_work:
                ox, oy = self._position_monitor_offset
                new_x = new_work[0] + ox
                new_y = new_work[1] + oy
                self._custom_position = (new_x, new_y)
                settings_mod.set_popup_position(new_x, new_y)
                self.win.geometry(f"+{new_x}+{new_y}")

        self._screen_check_id = self.root.after(2500, self._ensure_on_screen)

    def _start_screen_check(self):
        if self._screen_check_id is None:
            self._screen_check_id = self.root.after(2500, self._ensure_on_screen)

    def _stop_screen_check(self):
        if self._screen_check_id is not None:
            self.root.after_cancel(self._screen_check_id)
            self._screen_check_id = None

    # ------------------------------------------------------------------
    # Always-on-top
    # ------------------------------------------------------------------

    def set_always_on_top(self, enabled: bool):
        self._always_on_top = enabled
        self.win.attributes("-topmost", enabled)
        for sw in self._settings_windows.values():
            if sw.winfo_exists():
                sw.attributes("-topmost", enabled)
