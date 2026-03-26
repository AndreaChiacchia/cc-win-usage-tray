"""Tkinter popup window with usage progress bars."""

import re
import tkinter as tk
import time
from datetime import datetime

import settings as settings_mod
import theme as theme_mod
import time_utils
from version import __version__
import pace_delta as pace_delta_mod
from config import (
    POPUP_WIDTH, POPUP_PADDING, TASKBAR_OFFSET, BAR_HEIGHT,
)
from usage_parser import UsageSection, AccountUsage
from stats_panel import StatsPanel
from ui_animations import AnimationsMixin, _bar_color
from ui_scroll import ScrollMixin
from ui_monitor import MonitorMixin
from ui_settings import SettingsMixin


class UsagePopup(SettingsMixin, AnimationsMixin, MonitorMixin, ScrollMixin):
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
        if self._sb_canvas.winfo_width() > 0:
            self._update_scroll_sb(*self._scroll_canvas.yview())
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

                # Update pace delta
                if settings_mod.get_pace_delta_enabled(email):
                    new_delta = pace_delta_mod.compute_pace_delta(
                        section.label, section.percentage, section.reset_info
                    )
                else:
                    new_delta = None
                old_delta = refs.get("pace_delta")
                if new_delta != old_delta:
                    self._animate_pace_delta(key, old_delta, new_delta)
                    refs["pace_delta"] = new_delta

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

            if acc.usage.error and not acc.usage.sections:
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

        # Section label row (label + pace delta side by side)
        label_base = section.label
        label_text = label_base
        if section.spent_info:
            label_text += f" · {section.spent_info}"
        label_row = tk.Frame(frame, bg=t.bg)
        label_row.pack(fill=tk.X)
        section_lbl = tk.Label(
            label_row,
            text=label_text,
            bg=t.bg, fg=t.fg,
            font=t.font_bold,
            anchor="w",
        )
        section_lbl.pack(side=tk.LEFT)

        # Pace delta label
        if settings_mod.get_pace_delta_enabled(email):
            initial_delta = pace_delta_mod.compute_pace_delta(
                section.label, section.percentage, section.reset_info
            )
        else:
            initial_delta = None
        if initial_delta is not None:
            sign = "+" if initial_delta >= 0 else ""
            pace_text = f"[{sign}{initial_delta}%]"
            pace_fg = t.bar_green if initial_delta >= 0 else t.bar_red
        else:
            pace_text = ""
            pace_fg = t.fg
        pace_lbl = tk.Label(
            label_row,
            text=pace_text,
            bg=t.bg, fg=pace_fg,
            font=t.font_bold,
            anchor="w",
        )
        pace_lbl.pack(side=tk.LEFT, padx=(6, 0))

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
            "pace_label": pace_lbl,
            "pace_delta": initial_delta,
        }

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
        self._refresh_pace_deltas()
        self._start_relative_timer()

    def _refresh_pace_deltas(self):
        """Recompute pace deltas for all sections and animate any changes."""
        if not self._last_accounts:
            return
        for email, acc in self._last_accounts.items():
            for section in acc.usage.sections:
                key = (email, section.label)
                refs = self._bar_widgets.get(key)
                if not refs:
                    continue
                if settings_mod.get_pace_delta_enabled(email):
                    new_delta = pace_delta_mod.compute_pace_delta(
                        section.label, section.percentage, section.reset_info
                    )
                else:
                    new_delta = None
                old_delta = refs.get("pace_delta")
                if new_delta != old_delta:
                    self._animate_pace_delta(key, old_delta, new_delta)
                    refs["pace_delta"] = new_delta

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
    # Always-on-top
    # ------------------------------------------------------------------

    def set_always_on_top(self, enabled: bool):
        self._always_on_top = enabled
        self.win.attributes("-topmost", enabled)
        for sw in self._settings_windows.values():
            if sw.winfo_exists():
                sw.attributes("-topmost", enabled)
