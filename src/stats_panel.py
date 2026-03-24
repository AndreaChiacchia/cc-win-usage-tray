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
import re
import time
import tkinter as tk
from datetime import datetime, timedelta

import theme as theme_mod
import usage_history
from config import (
    COLOR_GREEN_MAX, COLOR_YELLOW_MAX,
    STATS_PANEL_WIDTH, STATS_BAR_MAX_HEIGHT, STATS_BAR_MIN_HEIGHT,
    STATS_CHART_HEIGHT, STATS_PIN_DURATION_MS,
)


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

        t = theme_mod.current()
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.configure(bg=t.border)
        self.win.attributes("-topmost", True)
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show(self, email: str, sections: list) -> None:
        """Show (or update) the panel for *email*. Called on hover-enter."""
        was_pinned = self._state == self._PINNED
        self._current_email = email
        self._current_sections = sections

        if not was_pinned:
            self._state = self._PREVIEWING

        self._rebuild_content()
        self._position_panel()
        self.win.deiconify()

        if not was_pinned:
            self._start_pin_animation()

    def hide(self) -> None:
        """Hide the panel unless it is pinned."""
        if self._state == self._PINNED:
            return
        self._cancel_pin_animation()
        self._state = self._HIDDEN
        self.win.withdraw()

    def force_hide(self) -> None:
        """Force-hide regardless of pin state (e.g. when popup closes)."""
        self._cancel_pin_animation()
        self._state = self._HIDDEN
        self._current_email = None
        self.win.withdraw()

    def apply_theme(self) -> None:
        """Reapply current theme colours to all widgets."""
        t = theme_mod.current()
        self.win.configure(bg=t.border)
        self._outer.configure(bg=t.border)
        self._inner.configure(bg=t.bg)
        self._pin_canvas.configure(bg=t.bg)
        self._content.configure(bg=t.bg)
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
        header_row.pack(fill=tk.X, pady=(0, 8))
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

        history = usage_history.get_history(email)

        # --- Today ---
        self._section_title(t, "Today")
        today_data = self._aggregate_hourly(history)
        self._bar_chart(t, today_data, label_fn=lambda i: str(i) if i % 3 == 0 else "")
        extra = self._extra_spend_in_range(history, _today_start(), _now())
        if extra:
            self._dim_label(t, f"Extra spend today: {extra}")

        self._separator(t)

        # --- This Week ---
        self._section_title(t, "This Week")
        _day_abbrs = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        week_data = self._aggregate_daily(history, days=7)
        week_labels = _day_abbrs  # always Mon–Sun
        self._bar_chart(t, week_data, label_fn=lambda i, wl=week_labels: wl[i] if i < len(wl) else "")
        extra = self._extra_spend_in_range(history, _week_start(), _now())
        if extra:
            self._dim_label(t, f"Extra spend this week: {extra}")

        self._separator(t)

        # --- This Month ---
        self._section_title(t, "This Month")
        now = datetime.now()
        days_in_month = calendar.monthrange(now.year, now.month)[1]
        month_data = self._aggregate_daily(history, days=days_in_month, from_month_start=True)
        self._bar_chart(
            t, month_data,
            label_fn=lambda i, d=days_in_month: str(i + 1) if (i == 0 or (i + 1) % 5 == 0) else "",
        )
        extra = self._extra_spend_in_range(history, _month_start(), _now())
        if extra:
            self._dim_label(t, f"Extra spend this month: {extra}")

        self._separator(t)

        # --- Text stats ---
        stats = tk.Frame(self._content, bg=t.bg)
        stats.pack(fill=tk.X, pady=(4, 0))

        peak = self._peak_hour(history)
        if peak is not None:
            self._dim_label(t, f"Peak usage time: {peak:02d}:00 – {(peak + 1) % 24:02d}:00", parent=stats)

        avg_max = self._avg_daily_max(history)
        if avg_max is not None:
            self._dim_label(t, f"Avg daily max: {avg_max:.0f}%", parent=stats)

        self.win.update_idletasks()

    # ------------------------------------------------------------------
    # Widget helpers
    # ------------------------------------------------------------------

    def _separator(self, t) -> None:
        tk.Frame(self._content, bg=t.border, height=1).pack(fill=tk.X, pady=(8, 4))

    def _section_title(self, t, text: str) -> None:
        tk.Label(
            self._content,
            text=text,
            bg=t.bg, fg=t.fg,
            font=t.font_bold,
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 4))

    def _dim_label(self, t, text: str, parent=None) -> None:
        tk.Label(
            parent or self._content,
            text=text,
            bg=t.bg, fg=t.fg_dim,
            font=t.font,
            anchor="w",
        ).pack(fill=tk.X, pady=(2, 0))

    def _bar_chart(self, t, data: list[int], label_fn) -> None:
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

        def _draw(event=None):
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

        canvas.bind("<Configure>", _draw)
        self.root.after(10, _draw)

    # ------------------------------------------------------------------
    # Data aggregation
    # ------------------------------------------------------------------

    @staticmethod
    def _max_pct(entry: dict) -> int:
        secs = entry.get("sections", {})
        if not secs:
            return 0
        return max(v.get("pct", 0) for v in secs.values())

    def _aggregate_hourly(self, history: list) -> list[int]:
        """24-element list: avg % per hour for today."""
        buckets: list[list[int]] = [[] for _ in range(24)]
        today = datetime.now().date()
        for entry in history:
            try:
                ts = datetime.fromisoformat(entry["ts"])
            except Exception:
                continue
            if ts.date() != today:
                continue
            buckets[ts.hour].append(self._max_pct(entry))
        return [int(sum(b) / len(b)) if b else 0 for b in buckets]

    def _aggregate_daily(
        self, history: list, days: int, from_month_start: bool = False
    ) -> list[int]:
        """*days*-element list: avg % per day, oldest-first."""
        now = datetime.now()
        if from_month_start:
            start_date = now.date().replace(day=1)
        else:
            start_date = (now - timedelta(days=days - 1)).date()

        buckets: dict[int, list[int]] = {}
        for entry in history:
            try:
                ts = datetime.fromisoformat(entry["ts"])
            except Exception:
                continue
            day_idx = (ts.date() - start_date).days
            if day_idx < 0 or day_idx >= days:
                continue
            buckets.setdefault(day_idx, []).append(self._max_pct(entry))

        return [
            int(sum(buckets[i]) / len(buckets[i])) if i in buckets else 0
            for i in range(days)
        ]

    def _extra_spend_in_range(
        self, history: list, start: datetime, end: datetime
    ) -> str | None:
        """Return the max observed Extra usage spent string in the range."""
        max_val: float | None = None
        cap_val: float | None = None
        for entry in history:
            try:
                ts = datetime.fromisoformat(entry["ts"])
            except Exception:
                continue
            if ts < start or ts > end:
                continue
            spent_str = entry.get("sections", {}).get("Extra usage", {}).get("spent")
            if not spent_str:
                continue
            m = re.search(r'\$([\d.]+)\s*/\s*\$([\d.]+)', spent_str)
            if m:
                v, c = float(m.group(1)), float(m.group(2))
                if max_val is None or v > max_val:
                    max_val, cap_val = v, c
        if max_val is not None and cap_val is not None:
            return f"${max_val:.2f} / ${cap_val:.2f}"
        return None

    def _peak_hour(self, history: list) -> int | None:
        buckets: list[list[int]] = [[] for _ in range(24)]
        for entry in history:
            try:
                ts = datetime.fromisoformat(entry["ts"])
            except Exception:
                continue
            pct = self._max_pct(entry)
            if pct > 0:
                buckets[ts.hour].append(pct)
        avgs = [sum(b) / len(b) if b else 0 for b in buckets]
        best = max(range(24), key=lambda i: avgs[i])
        return best if avgs[best] > 0 else None

    def _avg_daily_max(self, history: list) -> float | None:
        daily_max: dict[str, int] = {}
        for entry in history:
            try:
                ts = datetime.fromisoformat(entry["ts"])
            except Exception:
                continue
            pct = self._max_pct(entry)
            key = ts.date().isoformat()
            if key not in daily_max or pct > daily_max[key]:
                daily_max[key] = pct
        if not daily_max:
            return None
        return sum(daily_max.values()) / len(daily_max)

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
