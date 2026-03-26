"""Stats Panel — historical usage visualization for Claude Usage Tray.

Borderless Toplevel positioned to the left of the main popup (falls back to
right when there is no room).  Triggered by hovering over an account header in
the main popup.

States
------
hidden      Default; window is withdrawn.
previewing  Window visible; thin pin-progress bar fills over STATS_PIN_DURATION_MS.
            Leaving the account label before the bar completes → back to hidden.
pinned      Bar completed; panel stays open regardless of mouse position.
            A close button in the header dismisses it.
"""

import calendar
import time
import tkinter as tk
from datetime import datetime, timedelta

import theme as theme_mod
import token_history
import usage_history
from config import (
    ANIM_FRAME_MS,
    COLOR_GREEN_MAX, COLOR_YELLOW_MAX,
    STATS_PANEL_WIDTH, STATS_BAR_MAX_HEIGHT, STATS_BAR_MIN_HEIGHT,
    STATS_CHART_HEIGHT, STATS_PIN_DURATION_MS,
    STATS_OPEN_DURATION_MS, STATS_OPEN_SLIDE_PX, STATS_CLOSE_DURATION_MS,
)
from token_detail_panel import TokenDetailPanel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bar_color(pct: int) -> str:
    t = theme_mod.current()
    if pct < COLOR_GREEN_MAX:
        return t.bar_green
    elif pct < COLOR_YELLOW_MAX:
        return t.bar_yellow
    return t.bar_red


def _now() -> datetime:
    return datetime.now()


def _today_start() -> datetime:
    n = datetime.now()
    return n.replace(hour=0, minute=0, second=0, microsecond=0)


def _week_start() -> datetime:
    n = datetime.now()
    return (n - timedelta(days=n.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _month_start() -> datetime:
    n = datetime.now()
    return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# StatsPanel
# ---------------------------------------------------------------------------

class StatsPanel:
    """Hover-triggered stats panel shown to the left of the main popup."""

    _HIDDEN = "hidden"
    _PREVIEWING = "previewing"
    _PINNED = "pinned"

    def __init__(self, root: tk.Tk, popup_win: tk.Toplevel):
        self.root = root
        self._popup_win = popup_win
        self._state = self._HIDDEN
        self._current_email: str | None = None
        self._current_sections: list | None = None

        # Pin animation state
        self._pin_anim_id: str | None = None
        self._pin_start_time: float | None = None

        # Open animation state
        self._open_anim_id: str | None = None
        self._open_anim_start: float | None = None
        self._open_final_x: int | None = None
        self._open_final_y: int | None = None
        self._open_slide_sign: int = 1  # +1 = panel left of popup (slides left), -1 = right (slides right)

        # Close animation state
        self._close_anim_id: str | None = None
        self._close_anim_start: float | None = None

        t = theme_mod.current()
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.configure(bg=t.border)
        self.win.attributes("-topmost", True)
        self.win.attributes("-toolwindow", True)
        self.win.withdraw()

        # 1-px border via outer frame
        self._outer = tk.Frame(self.win, bg=t.border, padx=1, pady=1)
        self._outer.pack(fill=tk.BOTH, expand=True)

        self._inner = tk.Frame(self._outer, bg=t.bg)
        self._inner.pack(fill=tk.BOTH, expand=True)

        # Pin-progress bar (3 px, top of panel)
        self._pin_canvas = tk.Canvas(
            self._inner, height=3, bg=t.bg, highlightthickness=0
        )
        self._pin_canvas.pack(fill=tk.X)

        # Scrollable content area
        self._content = tk.Frame(self._inner, bg=t.bg, padx=16, pady=16)
        self._content.pack(fill=tk.BOTH, expand=True)

        # Token detail panel (shown on bar hover)
        self._token_panel = TokenDetailPanel(root, self.win)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show(self, email: str, sections: list) -> None:
        """Show (or update) the panel for *email*. Called on hover-enter."""
        currently_closing = self._close_anim_start is not None
        self._cancel_close_animation()
        already_visible = self._state != self._HIDDEN or currently_closing
        was_pinned = self._state == self._PINNED
        self._current_email = email
        self._current_sections = sections

        if not was_pinned:
            self._state = self._PREVIEWING

        self._rebuild_content()

        if already_visible:
            self._position_panel()
            self.win.attributes("-alpha", 1.0)
        else:
            self._start_open_animation()

        if not was_pinned:
            self._start_pin_animation()

    def hide(self) -> None:
        """Hide the panel unless it is pinned."""
        if self._state == self._PINNED:
            return
        self._cancel_open_animation()
        self._cancel_pin_animation()
        self._state = self._HIDDEN
        self._start_close_animation()

    def force_hide(self) -> None:
        """Force-hide regardless of pin state (e.g. when popup closes)."""
        self._cancel_open_animation()
        self._cancel_pin_animation()
        self._state = self._HIDDEN
        self._current_email = None
        self._start_close_animation()
        self._token_panel.force_hide()

    def apply_theme(self) -> None:
        """Reapply current theme colours to all widgets."""
        t = theme_mod.current()
        self.win.configure(bg=t.border)
        self._outer.configure(bg=t.border)
        self._inner.configure(bg=t.bg)
        self._pin_canvas.configure(bg=t.bg)
        self._content.configure(bg=t.bg)
        self._token_panel.apply_theme()
        if self._state != self._HIDDEN:
            self._rebuild_content()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _position_panel(self) -> None:
        self.win.update_idletasks()
        panel_w = STATS_PANEL_WIDTH
        panel_h = self.win.winfo_reqheight()

        popup_x = self._popup_win.winfo_x()
        popup_y = self._popup_win.winfo_y()

        x = popup_x - panel_w - 4
        if x < 0:
            x = popup_x + self._popup_win.winfo_width() + 4

        # Clamp y to screen
        screen_h = self.root.winfo_screenheight()
        y = max(0, min(popup_y, screen_h - panel_h))

        self.win.geometry(f"{panel_w}x{panel_h}+{x}+{y}")

    def _rebuild_content(self) -> None:
        for w in self._content.winfo_children():
            w.destroy()

        t = theme_mod.current()
        email = self._current_email

        # --- Header ---
        header_row = tk.Frame(self._content, bg=t.bg)
        header_row.pack(fill=tk.X, pady=(0, 12))
        tk.Label(
            header_row,
            text="Usage Stats",
            bg=t.bg, fg=t.fg,
            font=t.font_bold,
            anchor="w",
        ).pack(side=tk.LEFT)
        if self._state == self._PINNED:
            tk.Button(
                header_row,
                text="✕",
                bg=t.button_bg, fg=t.button_fg,
                activebackground=t.button_active_bg, activeforeground=t.button_fg,
                padx=4, pady=1,
                font=t.font,
                cursor="hand2",
                command=self.force_hide,
                **t.button_style_kwargs(),
            ).pack(side=tk.RIGHT)

        if email is None:
            return

        now = _now()

        # --- Pre-fetch token data for hover panels ---
        token_history.scan_blocking(email)
        hourly_tokens = token_history.get_hourly_tokens(now.date(), email)
        week_tokens = token_history.get_daily_tokens(_week_start().date(), 7, email)
        days_in_month = calendar.monthrange(now.year, now.month)[1]
        month_tokens = token_history.get_daily_tokens(_month_start().date(), days_in_month, email)

        # --- Today ---
        self._section_title(t, "Today")
        today_data = usage_history.get_hourly_avg(email, now.date())

        def _today_hover(i: int) -> dict:
            d = hourly_tokens[i] if 0 <= i < len(hourly_tokens) else {}
            return {
                "label": f"{i:02d}:00 – {i:02d}:59",
                **d,
            }

        self._bar_chart(t, today_data, label_fn=lambda i: str(i) if i % 3 == 0 else "",
                        hover_fn=_today_hover)
        extra = usage_history.get_extra_spend_delta(email, _today_start(), now)
        if extra:
            self._extra_spend_label(t, "Extra spend today: ", extra)
        else:
            self._dim_label(t, "No extra spending")

        self._separator(t)

        # --- This Week ---
        self._section_title(t, "This Week")
        _day_abbrs = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        week_data = usage_history.get_daily_avg(email, _week_start().date(), 7)
        _wk_start = _week_start().date()

        def _week_hover(i: int) -> dict:
            d = week_tokens[i] if 0 <= i < len(week_tokens) else {}
            day_date = _wk_start + timedelta(days=i)
            return {
                "label": f"{_day_abbrs[i]} {day_date.strftime('%d %b')}",
                **d,
            }

        self._bar_chart(t, week_data, label_fn=lambda i: _day_abbrs[i] if i < 7 else "",
                        hover_fn=_week_hover)
        extra = usage_history.get_extra_spend_delta(email, _week_start(), now)
        if extra:
            self._extra_spend_label(t, "Extra spend this week: ", extra)
        else:
            self._dim_label(t, "No extra spending")

        self._separator(t)

        # --- This Month ---
        self._section_title(t, "This Month")
        month_data = usage_history.get_daily_avg(email, _month_start().date(), days_in_month)
        _mo_start = _month_start().date()

        def _month_hover(i: int) -> dict:
            d = month_tokens[i] if 0 <= i < len(month_tokens) else {}
            day_date = _mo_start + timedelta(days=i)
            return {
                "label": day_date.strftime("%d %b"),
                **d,
            }

        self._bar_chart(
            t, month_data,
            label_fn=lambda i, dm=days_in_month: str(i + 1) if (i == 0 or (i + 1) % 5 == 0) else "",
            hover_fn=_month_hover,
        )
        extra = usage_history.get_extra_spend_current(email, _month_start(), now)
        if extra:
            self._extra_spend_label(t, "Extra spend this month: ", extra)
        else:
            self._dim_label(t, "No extra spending")

        self._separator(t)

        # --- Text stats ---
        stats = tk.Frame(self._content, bg=t.bg)
        stats.pack(fill=tk.X, pady=(4, 0))

        peak = usage_history.get_peak_hour(email)
        if peak is not None:
            self._dim_label(t, f"Peak usage time: {peak:02d}:00 – {(peak + 1) % 24:02d}:00", parent=stats)

        avg_max = usage_history.get_avg_daily_max(email)
        if avg_max is not None:
            self._dim_label(t, f"Avg daily max: {avg_max:.0f}%", parent=stats)

        self.win.update_idletasks()

    # ------------------------------------------------------------------
    # Widget helpers
    # ------------------------------------------------------------------

    def _separator(self, t) -> None:
        tk.Frame(self._content, bg=t.border, height=1).pack(fill=tk.X, pady=(12, 8))

    def _section_title(self, t, text: str) -> None:
        tk.Label(
            self._content,
            text=text,
            bg=t.bg, fg=t.fg,
            font=t.font_bold,
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 8))

    def _dim_label(self, t, text: str, parent=None) -> None:
        tk.Label(
            parent or self._content,
            text=text,
            bg=t.bg, fg=t.fg_dim,
            font=t.font,
            anchor="w",
        ).pack(fill=tk.X, pady=(4, 0))

    def _accent_label(self, t, text: str, parent=None) -> None:
        tk.Label(
            parent or self._content,
            text=text,
            bg=t.bg, fg=t.fg,
            font=t.font_bold,
            anchor="w",
        ).pack(fill=tk.X, pady=(4, 0))

    def _extra_spend_label(self, t, label_text: str, value_text: str) -> None:
        row = tk.Frame(self._content, bg=t.bg)
        row.pack(fill=tk.X, pady=(4, 0))
        tk.Label(row, text=label_text, bg=t.bg, fg=t.fg_dim, font=t.font, anchor="w").pack(side=tk.LEFT)
        tk.Label(row, text=value_text, bg=t.bg, fg=t.fg, font=t.font_bold, anchor="w").pack(side=tk.LEFT)

    def _bar_chart(self, t, data: list[int], label_fn, hover_fn=None) -> None:
        n = len(data)
        if n == 0:
            self._dim_label(t, "No data yet")
            return

        frame = tk.Frame(self._content, bg=t.bg)
        frame.pack(fill=tk.X)

        canvas = tk.Canvas(
            frame,
            width=STATS_PANEL_WIDTH - 32,
            height=STATS_CHART_HEIGHT,
            bg=t.bg,
            highlightthickness=0,
        )
        canvas.pack(fill=tk.X)

        # Bar boundaries [(x1, x2), ...] updated on each draw
        bar_bounds: list[tuple[int, int]] = []
        hovered_index: list[int] = [-1]  # mutable cell

        def _draw(event=None):
            bar_bounds.clear()
            w = canvas.winfo_width()
            if w <= 1:
                w = STATS_PANEL_WIDTH - 32
            canvas.delete("all")

            bar_area_h = STATS_BAR_MAX_HEIGHT
            label_h = STATS_CHART_HEIGHT - bar_area_h

            gap = max(3, w // (n * 6))
            bar_w = max(6, (w - gap * (n + 1)) // n)

            for i, pct in enumerate(data):
                x1 = gap + i * (bar_w + gap)
                x2 = x1 + bar_w
                bar_bounds.append((x1, x2))

                # Full-height container (matching ui_popup.py bar style)
                canvas.create_rectangle(x1, 0, x2, bar_area_h, fill=t.bar_bg, outline="")

                # Colored fill rising from bottom
                if pct > 0:
                    bh = max(STATS_BAR_MIN_HEIGHT, int(pct / 100 * bar_area_h))
                    y1 = bar_area_h - bh
                    canvas.create_rectangle(x1, y1, x2, bar_area_h, fill=_bar_color(pct), outline="")

                lbl = label_fn(i)
                if lbl:
                    cx = (x1 + x2) // 2
                    canvas.create_text(
                        cx, bar_area_h + 2 + label_h // 2,
                        text=lbl,
                        fill=t.fg_dim,
                        font=(t.font_family, max(t.font_size - 3, 7)),
                        anchor="center",
                    )

        def _on_motion(event):
            if hover_fn is None or not bar_bounds:
                return
            x = event.x
            idx = -1
            for i, (x1, x2) in enumerate(bar_bounds):
                if x1 <= x <= x2:
                    idx = i
                    break
            if idx == hovered_index[0]:
                return
            hovered_index[0] = idx
            if idx >= 0 and data[idx] > 0:
                self._token_panel.show(hover_fn(idx))
            else:
                self._token_panel.hide()

        def _on_leave(event):
            hovered_index[0] = -1
            self._token_panel.hide()

        canvas.bind("<Configure>", _draw)
        if hover_fn is not None:
            canvas.bind("<Motion>", _on_motion)
            canvas.bind("<Leave>", _on_leave)
        self.root.after(10, _draw)

    # ------------------------------------------------------------------
    # Pin animation
    # ------------------------------------------------------------------

    def _start_pin_animation(self) -> None:
        self._cancel_pin_animation()
        self._pin_start_time = time.monotonic()
        self._animate_pin()

    def _animate_pin(self) -> None:
        if self._state != self._PREVIEWING:
            return
        if self._pin_start_time is None:
            return

        elapsed_ms = (time.monotonic() - self._pin_start_time) * 1000
        fraction = min(elapsed_ms / STATS_PIN_DURATION_MS, 1.0)

        t = theme_mod.current()
        if self._pin_canvas.winfo_exists():
            w = self._pin_canvas.winfo_width()
            if w <= 1:
                w = STATS_PANEL_WIDTH - 2
            self._pin_canvas.delete("all")
            bar_w = int(w * fraction)
            if bar_w > 0:
                self._pin_canvas.create_rectangle(
                    0, 0, bar_w, 3, fill=t.bar_green, outline=""
                )

        if fraction >= 1.0:
            self._become_pinned()
        else:
            self._pin_anim_id = self.root.after(33, self._animate_pin)

    def _become_pinned(self) -> None:
        self._state = self._PINNED
        self._pin_start_time = None
        if self._pin_canvas.winfo_exists():
            self._pin_canvas.delete("all")
        self._rebuild_content()
        self._position_panel()

    def _cancel_pin_animation(self) -> None:
        if self._pin_anim_id is not None:
            try:
                self.root.after_cancel(self._pin_anim_id)
            except Exception:
                pass
            self._pin_anim_id = None
        self._pin_start_time = None

    # ------------------------------------------------------------------
    # Open animation
    # ------------------------------------------------------------------

    @staticmethod
    def _ease_out_quad(t: float) -> float:
        return 1.0 - (1.0 - t) ** 2

    def _cancel_open_animation(self) -> None:
        if self._open_anim_id is not None:
            try:
                self.root.after_cancel(self._open_anim_id)
            except Exception:
                pass
            self._open_anim_id = None
        self._open_anim_start = None

    def _start_open_animation(self) -> None:
        self._cancel_open_animation()

        self.win.update_idletasks()
        panel_w = STATS_PANEL_WIDTH
        panel_h = self.win.winfo_reqheight()

        popup_x = self._popup_win.winfo_x()
        popup_y = self._popup_win.winfo_y()

        x = popup_x - panel_w - 4
        if x < 0:
            x = popup_x + self._popup_win.winfo_width() + 4
            self._open_slide_sign = -1  # panel right of popup; starts left, slides right
        else:
            self._open_slide_sign = 1   # panel left of popup; starts right, slides left

        screen_h = self.root.winfo_screenheight()
        y = max(0, min(popup_y, screen_h - panel_h))

        self._open_final_x = x
        self._open_final_y = y

        # Start position: shifted toward the popup by STATS_OPEN_SLIDE_PX
        start_x = x + self._open_slide_sign * STATS_OPEN_SLIDE_PX
        self.win.geometry(f"{panel_w}x{panel_h}+{start_x}+{y}")
        self.win.attributes("-alpha", 0.0)
        self.win.deiconify()

        self._open_anim_start = time.monotonic()
        self._tick_open_animation()

    def _tick_open_animation(self) -> None:
        if self._open_anim_start is None:
            return

        elapsed_ms = (time.monotonic() - self._open_anim_start) * 1000
        t = min(elapsed_ms / STATS_OPEN_DURATION_MS, 1.0)
        progress = self._ease_out_quad(t)

        final_x = self._open_final_x
        final_y = self._open_final_y
        start_x = final_x + self._open_slide_sign * STATS_OPEN_SLIDE_PX

        current_x = int(start_x + (final_x - start_x) * progress)
        panel_w = STATS_PANEL_WIDTH
        panel_h = self.win.winfo_reqheight()

        self.win.geometry(f"{panel_w}x{panel_h}+{current_x}+{final_y}")
        self.win.attributes("-alpha", progress)

        if t >= 1.0:
            self.win.geometry(f"{panel_w}x{panel_h}+{final_x}+{final_y}")
            self.win.attributes("-alpha", 1.0)
            self._open_anim_id = None
            self._open_anim_start = None
        else:
            self._open_anim_id = self.root.after(ANIM_FRAME_MS, self._tick_open_animation)

    # ------------------------------------------------------------------
    # Close animation
    # ------------------------------------------------------------------

    def _cancel_close_animation(self) -> None:
        if self._close_anim_id is not None:
            try:
                self.root.after_cancel(self._close_anim_id)
            except Exception:
                pass
            self._close_anim_id = None
        self._close_anim_start = None

    def _start_close_animation(self) -> None:
        self._cancel_close_animation()
        if not self.win.winfo_viewable():
            self.win.attributes("-alpha", 1.0)
            self.win.withdraw()
            return
        self._close_anim_start = time.monotonic()
        self._tick_close_animation()

    def _tick_close_animation(self) -> None:
        if self._close_anim_start is None:
            return
        elapsed_ms = (time.monotonic() - self._close_anim_start) * 1000
        t = min(elapsed_ms / STATS_CLOSE_DURATION_MS, 1.0)
        # ease-in: (1-t)² — starts at 1, curves quickly to 0
        alpha = (1.0 - t) ** 2
        self.win.attributes("-alpha", alpha)
        if t >= 1.0:
            self.win.attributes("-alpha", 1.0)  # reset for next open
            self._close_anim_id = None
            self._close_anim_start = None
            self.win.withdraw()
        else:
            self._close_anim_id = self.root.after(ANIM_FRAME_MS, self._tick_close_animation)
