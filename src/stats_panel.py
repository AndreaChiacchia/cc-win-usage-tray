"""Stats Panel - historical usage visualization for Claude Usage Tray.

Borderless Toplevel positioned to the left of the main popup (falls back to
right when there is no room). Triggered by hovering over an account header in
the main popup.

States
------
hidden      Default; window is withdrawn.
previewing  Window visible; thin pin-progress bar fills over STATS_PIN_DURATION_MS.
            Leaving the account label before the bar completes -> back to hidden.
pinned      Bar completed; panel stays open regardless of mouse position.
            A close button in the header dismisses it.
"""

import calendar
import time
import tkinter as tk
from datetime import date, datetime, timedelta

import settings as settings_mod
import theme as theme_mod
import time_utils
import token_history
import usage_history
from config import (
    ANIM_FRAME_MS,
    COLOR_GREEN_MAX,
    COLOR_YELLOW_MAX,
    STATS_BAR_MAX_HEIGHT,
    STATS_BAR_MIN_HEIGHT,
    STATS_CHART_HEIGHT,
    STATS_CLOSE_DURATION_MS,
    STATS_OPEN_DURATION_MS,
    STATS_OPEN_SLIDE_PX,
    STATS_PANEL_WIDTH,
    STATS_PIN_DURATION_MS,
    STATS_TOP_LABEL_HEIGHT,
)
from format_utils import fmt_tokens
from token_detail_panel import TokenDetailPanel

_STATS_BAR_MODE_FILL = "fill"
_STATS_BAR_MODE_COLOR = "color"


def _bar_color(pct: int) -> str:
    t = theme_mod.current()
    if pct < COLOR_GREEN_MAX:
        return t.bar_green
    if pct < COLOR_YELLOW_MAX:
        return t.bar_yellow
    return t.bar_red


def _now() -> datetime:
    return datetime.now()


def _blend_color(color: str, bg: str, blend: float) -> str:
    color = color.lstrip("#")
    bg = bg.lstrip("#")
    blend = max(0.0, min(1.0, blend))
    cr, cg, cb = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    br, bgc, bb = (int(bg[i:i + 2], 16) for i in (0, 2, 4))
    r = round(cr * (1.0 - blend) + br * blend)
    g = round(cg * (1.0 - blend) + bgc * blend)
    b = round(cb * (1.0 - blend) + bb * blend)
    return f"#{r:02x}{g:02x}{b:02x}"


def _chart_max_value(data: list[int], disabled_indices: set[int] | None = None) -> int:
    disabled = disabled_indices or set()
    return max((v for i, v in enumerate(data) if i not in disabled), default=0) or 100


def _normalize_chart_value(pct: int, max_val: int) -> int:
    if max_val <= 0:
        return 0
    return max(0, min(100, int(pct / max_val * 100)))


def _chart_bar_fill(
    base_color: str,
    track_color: str,
    bg_color: str,
    normalized_pct: int,
    mode: str,
    disabled: bool = False,
) -> str:
    if disabled:
        return _blend_color(base_color, bg_color, 0.45)
    if mode == _STATS_BAR_MODE_COLOR:
        muted_track = _blend_color(track_color, bg_color, 0.2)
        blend = 0.9 - (0.9 * (max(0, min(100, normalized_pct)) / 100.0))
        return _blend_color(base_color, muted_track, blend)
    return base_color


def _week_start() -> datetime:
    n = datetime.now()
    return (n - timedelta(days=n.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _month_start() -> datetime:
    n = datetime.now()
    return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _empty_token_totals() -> dict:
    return {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}


def _week_start_for(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _week_end_for(value: date) -> date:
    return _week_start_for(value) + timedelta(days=6)


def _week_title(selected_date: date, today: date) -> str:
    week_start = _week_start_for(selected_date)
    if week_start == _week_start_for(today):
        return "This Week"
    return _range_label(week_start, _week_end_for(selected_date))


def _week_disabled_indices(week_start: date, today: date) -> set[int]:
    if week_start != _week_start_for(today):
        return set()
    return {
        i for i in range(7) if (week_start + timedelta(days=i)) > today
    }


def _is_current_week(value: date, today: date) -> bool:
    return _week_start_for(value) == _week_start_for(today)


def _peak_day_for_week(week_start: date, week_data: list[int], today: date) -> date:
    valid_end = today if _is_current_week(week_start, today) else week_start + timedelta(days=6)
    valid_indices = [
        idx for idx in range(7)
        if week_start + timedelta(days=idx) <= valid_end
    ]
    if not valid_indices:
        return week_start

    best_idx = valid_indices[0]
    best_pct = week_data[best_idx] if best_idx < len(week_data) else 0
    for idx in valid_indices[1:]:
        pct = week_data[idx] if idx < len(week_data) else 0
        if pct >= best_pct:
            best_idx = idx
            best_pct = pct
    return week_start + timedelta(days=best_idx)


def _date_label(value: date) -> str:
    return f"{value.day} {value.strftime('%b')}"


def _compact_range_label(start: date, end: date) -> str:
    if start == end:
        return str(start.day)
    return f"{start.day}-{end.day}"


def _range_label(start: date, end: date) -> str:
    if start == end:
        return _date_label(start)
    return f"{_date_label(start)} - {_date_label(end)}"


def _build_month_week_slots(
    month_start: date,
    days_in_month: int,
    today: date,
    month_data: list[int],
    month_tokens: list[dict],
) -> list[dict]:
    month_end = month_start + timedelta(days=days_in_month - 1)
    cursor = month_start - timedelta(days=month_start.weekday())
    slots: list[dict] = []

    while cursor <= month_end:
        week_end = cursor + timedelta(days=6)
        slot_start = max(cursor, month_start)
        slot_end = min(week_end, month_end)
        valid_indices: list[int] = []

        day_cursor = slot_start
        while day_cursor <= slot_end:
            if day_cursor <= today:
                valid_indices.append((day_cursor - month_start).days)
            day_cursor += timedelta(days=1)

        token_totals = _empty_token_totals()
        pct_values: list[int] = []
        for idx in valid_indices:
            if 0 <= idx < len(month_data):
                pct_values.append(month_data[idx] or 0)
            if 0 <= idx < len(month_tokens):
                token_slot = month_tokens[idx]
                token_totals["input"] += token_slot.get("input", 0)
                token_totals["output"] += token_slot.get("output", 0)
                token_totals["cache_read"] += token_slot.get("cache_read", 0)
                token_totals["cache_creation"] += token_slot.get("cache_creation", 0)

        slots.append({
            "start": slot_start,
            "end": slot_end,
            "label": _compact_range_label(slot_start, slot_end),
            "hover_label": _range_label(slot_start, slot_end),
            "pct": int(sum(pct_values) / len(pct_values)) if pct_values else 0,
            "tokens": token_totals,
            "disabled": not valid_indices,
            "selected_date": valid_indices and (month_start + timedelta(days=valid_indices[-1])) or None,
        })
        cursor += timedelta(days=7)

    return slots


def _build_year_month_slots(
    year: int,
    today: date,
    year_data: list[int],
    year_tokens: list[dict],
) -> list[dict]:
    year_start = date(year, 1, 1)
    slots: list[dict] = []
    for m in range(1, 13):
        month_start = date(year, m, 1)
        days_in_month = calendar.monthrange(year, m)[1]
        day_offset = (month_start - year_start).days

        token_totals = _empty_token_totals()
        pct_values: list[int] = []
        for d in range(days_in_month):
            day_date = month_start + timedelta(days=d)
            if day_date > today:
                break
            idx = day_offset + d
            if 0 <= idx < len(year_data) and year_data[idx] > 0:
                pct_values.append(year_data[idx])
            if 0 <= idx < len(year_tokens):
                slot = year_tokens[idx]
                token_totals["input"] += slot.get("input", 0)
                token_totals["output"] += slot.get("output", 0)
                token_totals["cache_read"] += slot.get("cache_read", 0)
                token_totals["cache_creation"] += slot.get("cache_creation", 0)

        slots.append({
            "month_start": month_start,
            "label": month_start.strftime("%b"),
            "hover_label": month_start.strftime("%B %Y"),
            "pct": int(sum(pct_values) / len(pct_values)) if pct_values else 0,
            "tokens": token_totals,
            "disabled": month_start > today,
        })
    return slots


class StatsPanel:
    """Hover-triggered stats panel shown to the left of the main popup."""

    _HIDDEN = "hidden"
    _PREVIEWING = "previewing"
    _PINNED = "pinned"
    _MONTH_VIEW_DAY = "day"
    _MONTH_VIEW_WEEK = "week"
    _MONTH_VIEW_MONTH = "month"
    _CHART_MODE_FILL = _STATS_BAR_MODE_FILL
    _CHART_MODE_COLOR = _STATS_BAR_MODE_COLOR

    def __init__(self, root: tk.Tk, popup_win: tk.Toplevel):
        self.root = root
        self._popup_win = popup_win
        self._state = self._HIDDEN
        self._current_email: str | None = None
        self._current_sections: list | None = None
        self._selected_date: date | None = None
        self._selected_month: date | None = None
        self._selected_day_frame: tk.Frame | None = None
        self._selected_day_redraw = None
        self._week_chart_redraw = None
        self._week_section_frame: tk.Frame | None = None
        self._week_chart_context: dict | None = None
        self._month_chart_redraw = None
        self._month_section_frame: tk.Frame | None = None
        self._month_chart_context: dict | None = None
        self._month_view_mode = self._MONTH_VIEW_DAY
        self._chart_mode = settings_mod.get_stats_bar_mode()

        # Pin animation state
        self._pin_anim_id: str | None = None
        self._pin_start_time: float | None = None

        # Open animation state
        self._open_anim_id: str | None = None
        self._open_anim_start: float | None = None
        self._open_final_x: int | None = None
        self._open_final_y: int | None = None
        self._open_slide_sign: int = 1

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

        self._outer = tk.Frame(self.win, bg=t.border, padx=1, pady=1)
        self._outer.pack(fill=tk.BOTH, expand=True)

        self._inner = tk.Frame(self._outer, bg=t.bg)
        self._inner.pack(fill=tk.BOTH, expand=True)

        self._pin_canvas = tk.Canvas(
            self._inner, height=3, bg=t.bg, highlightthickness=0
        )
        self._pin_canvas.pack(fill=tk.X)

        self._content = tk.Frame(self._inner, bg=t.bg, padx=16, pady=16)
        self._content.pack(fill=tk.BOTH, expand=True)

        self._token_panel = TokenDetailPanel(root, self.win)

    def show(self, email: str, sections: list) -> None:
        """Show (or update) the panel for *email*. Called on hover-enter."""
        currently_closing = self._close_anim_start is not None
        self._cancel_close_animation()
        already_visible = self._state != self._HIDDEN or currently_closing
        was_pinned = self._state == self._PINNED
        previous_email = self._current_email
        self._current_email = email
        self._current_sections = sections

        if not already_visible or previous_email != email:
            self._selected_date = _now().date()
            self._selected_month = None

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
        self._selected_date = None
        self._selected_month = None
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

    def _position_panel(self) -> None:
        self.win.update_idletasks()
        panel_w = STATS_PANEL_WIDTH
        panel_h = self.win.winfo_reqheight()

        popup_x = self._popup_win.winfo_x()
        popup_y = self._popup_win.winfo_y()
        popup_h = self._popup_win.winfo_height()

        x = popup_x - panel_w - 4
        if x < 0:
            x = popup_x + self._popup_win.winfo_width() + 4

        screen_h = self.root.winfo_screenheight()
        popup_bottom = popup_y + popup_h
        y = max(0, min(popup_bottom - panel_h, screen_h - panel_h))

        self.win.geometry(f"{panel_w}x{panel_h}+{x}+{y}")

    def _rebuild_content(self) -> None:
        for w in self._content.winfo_children():
            w.destroy()

        t = theme_mod.current()
        email = self._current_email
        self._selected_day_frame = None
        self._selected_day_redraw = None
        self._week_chart_redraw = None
        self._week_section_frame = None
        self._week_chart_context = None
        self._month_chart_redraw = None
        self._month_section_frame = None
        self._month_chart_context = None

        header_row = tk.Frame(self._content, bg=t.bg)
        header_row.pack(fill=tk.X, pady=(0, 12))
        tk.Label(
            header_row,
            text="Usage Stats",
            bg=t.bg,
            fg=t.fg,
            font=t.font_bold,
            anchor="w",
        ).pack(side=tk.LEFT)
        if self._state == self._PINNED:
            tk.Button(
                header_row,
                text="X",
                bg=t.button_bg,
                fg=t.button_fg,
                activebackground=t.button_active_bg,
                activeforeground=t.button_fg,
                padx=4,
                pady=1,
                font=t.font,
                cursor="hand2",
                command=self.force_hide,
                **t.button_style_kwargs(),
            ).pack(side=tk.RIGHT)
        if email is not None:
            toggle = tk.Frame(header_row, bg=t.bg)
            toggle.pack(side=tk.RIGHT, padx=(0, 8 if self._state == self._PINNED else 0))
            self._chart_mode_button(toggle, t, "Fill", self._CHART_MODE_FILL).pack(side=tk.LEFT)
            self._chart_mode_button(toggle, t, "Color", self._CHART_MODE_COLOR).pack(side=tk.LEFT, padx=(4, 0))

        if email is None:
            return

        now = _now()
        if self._selected_date is None or self._selected_date > now.date():
            self._selected_date = now.date()

        token_history.scan_blocking(email)
        month_start = self._selected_month or _month_start().date()
        days_in_month = calendar.monthrange(month_start.year, month_start.month)[1]

        self._selected_day_frame = tk.Frame(self._content, bg=t.bg)
        self._selected_day_frame.pack(fill=tk.X)
        self._render_selected_day_section(email)

        self._separator(t)

        self._week_chart_context = self._build_week_chart_context(email, now)
        self._week_section_frame = tk.Frame(self._content, bg=t.bg)
        self._week_section_frame.pack(fill=tk.X)
        self._render_week_section()

        self._separator(t)

        if self._month_view_mode == self._MONTH_VIEW_MONTH:
            year = now.year
            year_start = date(year, 1, 1)
            days_in_year = 366 if calendar.isleap(year) else 365
            year_data = usage_history.get_daily_delta(email, year_start, days_in_year, "Current week")
            year_tokens = token_history.get_daily_tokens(year_start, days_in_year, email)
            self._month_chart_context = {
                "email": email,
                "now": now,
                "month_start": month_start,
                "days_in_month": days_in_month,
                "month_data": [],
                "month_tokens": [],
                "week_slots": [],
                "year_slots": _build_year_month_slots(year, now.date(), year_data, year_tokens),
                "year": year,
            }
        else:
            month_tokens = token_history.get_daily_tokens(month_start, days_in_month, email)
            month_data = usage_history.get_daily_delta(email, month_start, days_in_month, "Current week")
            self._month_chart_context = {
                "email": email,
                "now": now,
                "month_start": month_start,
                "days_in_month": days_in_month,
                "month_data": month_data,
                "month_tokens": month_tokens,
                "week_slots": _build_month_week_slots(
                    month_start,
                    days_in_month,
                    now.date(),
                    month_data,
                    month_tokens,
                ),
            }
        self._month_section_frame = tk.Frame(self._content, bg=t.bg)
        self._month_section_frame.pack(fill=tk.X)
        self._render_month_section()

        self._separator(t)

        stats = tk.Frame(self._content, bg=t.bg)
        stats.pack(fill=tk.X, pady=(4, 0))

        peak = usage_history.get_peak_hour(email)
        if peak is not None:
            self._dim_label(
                t,
                f"Peak usage time: {peak:02d}:00 - {(peak + 1) % 24:02d}:00",
                parent=stats,
            )

        avg_max = usage_history.get_avg_daily_max(email)
        if avg_max is not None:
            self._dim_label(t, f"Avg daily max: {avg_max:.0f}%", parent=stats)

        self.win.update_idletasks()

    def _render_selected_day_section(self, email: str) -> None:
        if self._selected_day_frame is None:
            return

        for widget in self._selected_day_frame.winfo_children():
            widget.destroy()

        t = theme_mod.current()
        selected_date = self._selected_date or _now().date()
        title = "Today" if selected_date == _now().date() else selected_date.strftime("%a %d %b")
        tk.Label(
            self._selected_day_frame,
            text=title,
            bg=t.bg,
            fg=t.fg,
            font=t.font_bold,
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 8))

        hourly_data = usage_history.get_hourly_delta(email, selected_date, "Current session")
        hourly_tokens = token_history.get_hourly_tokens(selected_date, email)

        def _hour_hover(i: int) -> dict:
            d = hourly_tokens[i] if 0 <= i < len(hourly_tokens) else {}
            return {
                "label": f"{i:02d}:00 - {i:02d}:59",
                **d,
            }

        peak_hours = time_utils.peak_local_hours(
            settings_mod.get_peak_start(), settings_mod.get_peak_end()
        )
        self._selected_day_redraw = self._bar_chart(
            t,
            hourly_data,
            label_fn=lambda i: str(i) if i % 3 == 0 else "",
            hover_fn=_hour_hover,
            token_data=hourly_tokens,
            selected_index_fn=self._get_selected_hour_index,
            highlight_indices_fn=lambda h=peak_hours: h,
            parent=self._selected_day_frame,
        )

        extra = self._selected_day_extra_spend(email, selected_date)
        if extra:
            if selected_date == _now().date():
                label_text = "Extra spend today: "
            else:
                label_text = f"Extra spend on {selected_date.strftime('%a %d %b')}: "
            self._extra_spend_label_in(self._selected_day_frame, t, label_text, extra)
        else:
            self._dim_label(t, "No extra spending", parent=self._selected_day_frame)

    def _selected_day_extra_spend(self, email: str, selected_date: date) -> str | None:
        now = _now()
        if selected_date > now.date():
            return None
        start = datetime.combine(selected_date, datetime.min.time())
        end = now if selected_date == now.date() else start + timedelta(days=1) - timedelta(microseconds=1)
        return usage_history.get_extra_spend_delta(email, start, end)

    def _get_selected_hour_index(self) -> int | None:
        now = _now()
        if self._selected_date != now.date():
            return None
        return now.hour

    def _build_week_chart_context(self, email: str, now: datetime) -> dict:
        selected_date = self._selected_date or now.date()
        week_start = _week_start_for(selected_date)
        return {
            "email": email,
            "now": now,
            "selected_date": selected_date,
            "week_start": week_start,
            "week_end": week_start + timedelta(days=6),
            "title": _week_title(selected_date, now.date()),
            "week_data": usage_history.get_daily_delta(email, week_start, 7, "Current week"),
            "week_tokens": token_history.get_daily_tokens(week_start, 7, email),
            "week_disabled": _week_disabled_indices(week_start, now.date()),
        }

    def _render_week_section(self) -> None:
        if self._week_section_frame is None or self._week_chart_context is None:
            return

        for widget in self._week_section_frame.winfo_children():
            widget.destroy()

        t = theme_mod.current()
        ctx = self._week_chart_context
        week_start = ctx["week_start"]
        now = ctx["now"]
        day_abbrs = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        tk.Label(
            self._week_section_frame,
            text=ctx["title"],
            bg=t.bg,
            fg=t.fg,
            font=t.font_bold,
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 8))

        def _week_hover(i: int) -> dict:
            d = ctx["week_tokens"][i] if 0 <= i < len(ctx["week_tokens"]) else {}
            day_date = week_start + timedelta(days=i)
            return {
                "label": f"{day_abbrs[i]} {day_date.strftime('%d %b')}",
                **d,
            }

        self._week_chart_redraw = self._bar_chart(
            t,
            ctx["week_data"],
            label_fn=lambda i: day_abbrs[i] if i < 7 else "",
            hover_fn=_week_hover,
            token_data=ctx["week_tokens"],
            selected_index_fn=self._get_week_selected_index,
            disabled_indices_fn=lambda: ctx["week_disabled"],
            on_click=lambda idx: self._set_selected_date(week_start + timedelta(days=idx)),
            parent=self._week_section_frame,
        )

        extra = self._selected_week_extra_spend(ctx["email"], week_start, now)
        if extra:
            if ctx["title"] == "This Week":
                label_text = "Extra spend this week: "
            else:
                label_text = f"Extra spend for {ctx['title']}: "
            self._extra_spend_label_in(self._week_section_frame, t, label_text, extra)
        else:
            self._dim_label(t, "No extra spending", parent=self._week_section_frame)

    def _selected_week_extra_spend(self, email: str, week_start: date, now: datetime) -> str | None:
        start = datetime.combine(week_start, datetime.min.time())
        if week_start == _week_start_for(now.date()):
            end = now
        else:
            end = start + timedelta(days=7) - timedelta(microseconds=1)
        return usage_history.get_extra_spend_delta(email, start, end)

    def _resolve_month_selection_date(self, target_date: date) -> date:
        now = _now()
        target_week = _week_start_for(target_date)
        current_week = _week_start_for(self._selected_date) if self._selected_date is not None else None
        if target_week == current_week or _is_current_week(target_date, now.date()):
            return target_date

        week_data = usage_history.get_daily_delta(
            self._current_email,
            target_week,
            7,
            "Current week",
        )
        return _peak_day_for_week(target_week, week_data, now.date())

    def _set_selected_date(self, selected_date: date) -> None:
        if self._current_email is None:
            return
        if selected_date > _now().date():
            return
        if selected_date == self._selected_date:
            return

        self._selected_date = selected_date
        self._render_selected_day_section(self._current_email)
        self._week_chart_context = self._build_week_chart_context(self._current_email, _now())
        self._render_week_section()
        if self._month_chart_redraw is not None:
            self._month_chart_redraw()

    def _set_month_view_mode(self, mode: str) -> None:
        if mode not in {self._MONTH_VIEW_DAY, self._MONTH_VIEW_WEEK, self._MONTH_VIEW_MONTH}:
            return
        if mode == self._month_view_mode:
            return
        prev_mode = self._month_view_mode
        self._month_view_mode = mode
        self._token_panel.force_hide()
        if mode == self._MONTH_VIEW_MONTH or prev_mode == self._MONTH_VIEW_MONTH:
            self._rebuild_content()
            self._position_panel()
        else:
            self._render_month_section()

    def _set_chart_mode(self, mode: str) -> None:
        if mode not in {self._CHART_MODE_FILL, self._CHART_MODE_COLOR}:
            return
        if mode == self._chart_mode:
            return
        self._chart_mode = mode
        settings_mod.set_stats_bar_mode(mode)
        self._token_panel.force_hide()
        if self._state != self._HIDDEN:
            self._rebuild_content()
            self._position_panel()

    def _render_month_section(self) -> None:
        if self._month_section_frame is None or self._month_chart_context is None:
            return

        for widget in self._month_section_frame.winfo_children():
            widget.destroy()

        t = theme_mod.current()
        ctx = self._month_chart_context
        month_start = ctx["month_start"]
        days_in_month = ctx["days_in_month"]

        if self._month_view_mode == self._MONTH_VIEW_MONTH:
            title_text = str(ctx["year"])
        else:
            current_month_start = _month_start().date()
            title_text = "This Month" if month_start == current_month_start else month_start.strftime("%B %Y")

        title_row = tk.Frame(self._month_section_frame, bg=t.bg)
        title_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(
            title_row,
            text=title_text,
            bg=t.bg,
            fg=t.fg,
            font=t.font_bold,
            anchor="w",
        ).pack(side=tk.LEFT)

        toggle = tk.Frame(title_row, bg=t.bg)
        toggle.pack(side=tk.RIGHT)
        self._month_toggle_button(toggle, t, "Day", self._MONTH_VIEW_DAY).pack(side=tk.LEFT)
        self._month_toggle_button(toggle, t, "Week", self._MONTH_VIEW_WEEK).pack(side=tk.LEFT, padx=(4, 0))
        self._month_toggle_button(toggle, t, "Month", self._MONTH_VIEW_MONTH).pack(side=tk.LEFT, padx=(4, 0))

        if self._month_view_mode == self._MONTH_VIEW_MONTH:
            year_slots = ctx["year_slots"]

            def _year_hover(i: int) -> dict:
                slot = year_slots[i]
                return {
                    "label": slot["hover_label"],
                    **slot["tokens"],
                }

            self._month_chart_redraw = self._bar_chart(
                t,
                [slot["pct"] for slot in year_slots],
                label_fn=lambda i, slots=year_slots: slots[i]["label"] if i < len(slots) else "",
                hover_fn=_year_hover,
                token_data=[slot["tokens"] for slot in year_slots],
                selected_index_fn=self._get_month_selected_index,
                disabled_indices_fn=lambda slots=year_slots: {
                    idx for idx, slot in enumerate(slots) if slot["disabled"]
                },
                on_click=lambda idx, slots=year_slots: self._on_month_bar_click(slots[idx]["month_start"]),
                parent=self._month_section_frame,
            )

            year = ctx["year"]
            now = ctx["now"]
            year_start_dt = datetime(year, 1, 1)
            extra = usage_history.get_extra_spend_current(self._current_email, year_start_dt, now)
            if extra:
                self._extra_spend_label_in(self._month_section_frame, t, f"Extra spend in {year}: ", extra)
            else:
                self._dim_label(t, "No extra spending", parent=self._month_section_frame)

        elif self._month_view_mode == self._MONTH_VIEW_WEEK:
            week_slots = ctx["week_slots"]

            def _week_hover(i: int) -> dict:
                slot = week_slots[i]
                return {
                    "label": slot["hover_label"],
                    **slot["tokens"],
                }

            self._month_chart_redraw = self._bar_chart(
                t,
                [slot["pct"] for slot in week_slots],
                label_fn=lambda i, slots=week_slots: slots[i]["label"] if i < len(slots) else "",
                hover_fn=_week_hover,
                token_data=[slot["tokens"] for slot in week_slots],
                selected_index_fn=self._get_month_selected_index,
                disabled_indices_fn=lambda slots=week_slots: {
                    idx for idx, slot in enumerate(slots) if slot["disabled"]
                },
                on_click=lambda idx, slots=week_slots: self._set_selected_date(
                    self._resolve_month_selection_date(slots[idx]["selected_date"])
                ),
                parent=self._month_section_frame,
            )

            current_month_start = _month_start().date()
            if month_start == current_month_start:
                extra = usage_history.get_extra_spend_current(self._current_email, _month_start(), ctx["now"])
                label_text = "Extra spend this month: "
            else:
                start_dt = datetime.combine(month_start, datetime.min.time())
                end_dt = start_dt + timedelta(days=days_in_month) - timedelta(microseconds=1)
                extra = usage_history.get_extra_spend_delta(self._current_email, start_dt, end_dt)
                label_text = f"Extra spend in {month_start.strftime('%B %Y')}: "
            if extra:
                self._extra_spend_label_in(self._month_section_frame, t, label_text, extra)
            else:
                self._dim_label(t, "No extra spending", parent=self._month_section_frame)

        else:
            month_data = ctx["month_data"]
            month_tokens = ctx["month_tokens"]
            month_disabled = {
                i for i in range(days_in_month) if (month_start + timedelta(days=i)) > ctx["now"].date()
            }

            def _month_hover(i: int) -> dict:
                d = month_tokens[i] if 0 <= i < len(month_tokens) else {}
                day_date = month_start + timedelta(days=i)
                return {
                    "label": day_date.strftime("%d %b"),
                    **d,
                }

            self._month_chart_redraw = self._bar_chart(
                t,
                month_data,
                label_fn=lambda i, dm=days_in_month: str(i + 1) if (i == 0 or (i + 1) % 5 == 0) else "",
                hover_fn=_month_hover,
                token_data=month_tokens,
                selected_index_fn=self._get_month_selected_index,
                disabled_indices_fn=lambda: month_disabled,
                on_click=lambda idx: self._set_selected_date(
                    self._resolve_month_selection_date(month_start + timedelta(days=idx))
                ),
                parent=self._month_section_frame,
            )

            current_month_start = _month_start().date()
            if month_start == current_month_start:
                extra = usage_history.get_extra_spend_current(self._current_email, _month_start(), ctx["now"])
                label_text = "Extra spend this month: "
            else:
                start_dt = datetime.combine(month_start, datetime.min.time())
                end_dt = start_dt + timedelta(days=days_in_month) - timedelta(microseconds=1)
                extra = usage_history.get_extra_spend_delta(self._current_email, start_dt, end_dt)
                label_text = f"Extra spend in {month_start.strftime('%B %Y')}: "
            if extra:
                self._extra_spend_label_in(self._month_section_frame, t, label_text, extra)
            else:
                self._dim_label(t, "No extra spending", parent=self._month_section_frame)

    def _month_toggle_button(self, parent, t, text: str, mode: str) -> tk.Button:
        return self._segmented_toggle_button(
            parent,
            t,
            text,
            mode == self._month_view_mode,
            lambda m=mode: self._set_month_view_mode(m),
        )

    def _on_month_bar_click(self, month_start: date) -> None:
        now = _now()
        self._selected_month = month_start
        self._month_view_mode = self._MONTH_VIEW_WEEK
        current_month = _month_start().date()
        if month_start == current_month:
            self._selected_date = now.date()
        else:
            days_in_month = calendar.monthrange(month_start.year, month_start.month)[1]
            last_day = month_start + timedelta(days=days_in_month - 1)
            self._selected_date = min(last_day, now.date())
        self._rebuild_content()
        self._position_panel()

    def _get_year_selected_month_index(self) -> int | None:
        if self._selected_date is None:
            return None
        return self._selected_date.month - 1

    def _chart_mode_button(self, parent, t, text: str, mode: str) -> tk.Button:
        return self._segmented_toggle_button(
            parent,
            t,
            text,
            mode == self._chart_mode,
            lambda m=mode: self._set_chart_mode(m),
        )

    def _segmented_toggle_button(self, parent, t, text: str, is_selected: bool, command) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            bg=t.button_active_bg if is_selected else t.button_bg,
            fg=t.button_fg,
            activebackground=t.button_active_bg,
            activeforeground=t.button_fg,
            padx=6,
            pady=1,
            font=t.font_bold if is_selected else t.font,
            cursor="hand2",
            command=command,
            **t.button_style_kwargs(),
        )

    def _get_week_selected_index(self) -> int | None:
        if self._selected_date is None or self._week_chart_context is None:
            return None
        start = self._week_chart_context["week_start"]
        idx = (self._selected_date - start).days
        return idx if 0 <= idx < 7 else None

    def _get_month_selected_index(self) -> int | None:
        if self._selected_date is None:
            return None
        if self._month_view_mode == self._MONTH_VIEW_MONTH:
            return self._get_year_selected_month_index()
        if self._month_view_mode == self._MONTH_VIEW_WEEK:
            if self._month_chart_context is None:
                return None
            for idx, slot in enumerate(self._month_chart_context["week_slots"]):
                if slot["start"] <= self._selected_date <= slot["end"]:
                    return idx
            return None
        if self._month_chart_context is None:
            return None
        start = self._month_chart_context["month_start"]
        days_in_month = self._month_chart_context["days_in_month"]
        idx = (self._selected_date - start).days
        return idx if 0 <= idx < days_in_month else None

    def _separator(self, t) -> None:
        tk.Frame(self._content, bg=t.border, height=1).pack(fill=tk.X, pady=(12, 8))

    def _section_title(self, t, text: str) -> None:
        tk.Label(
            self._content,
            text=text,
            bg=t.bg,
            fg=t.fg,
            font=t.font_bold,
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 8))

    def _dim_label(self, t, text: str, parent=None) -> None:
        tk.Label(
            parent or self._content,
            text=text,
            bg=t.bg,
            fg=t.fg_dim,
            font=t.font,
            anchor="w",
        ).pack(fill=tk.X, pady=(4, 0))

    def _extra_spend_label(self, t, label_text: str, value_text: str) -> None:
        self._extra_spend_label_in(self._content, t, label_text, value_text)

    def _extra_spend_label_in(self, parent, t, label_text: str, value_text: str) -> None:
        row = tk.Frame(parent, bg=t.bg)
        row.pack(fill=tk.X, pady=(4, 0))
        tk.Label(
            row,
            text=label_text,
            bg=t.bg,
            fg=t.fg_dim,
            font=t.font,
            anchor="w",
        ).pack(side=tk.LEFT)
        tk.Label(
            row,
            text=value_text,
            bg=t.bg,
            fg=t.fg,
            font=t.font_bold,
            anchor="w",
        ).pack(side=tk.LEFT)

    def _bar_chart(
        self,
        t,
        data: list[int],
        label_fn,
        hover_fn=None,
        token_data=None,
        selected_index_fn=None,
        disabled_indices_fn=None,
        highlight_indices_fn=None,
        on_click=None,
        parent=None,
    ):
        n = len(data)
        if n == 0:
            self._dim_label(t, "No data yet", parent=parent)
            return None

        frame = tk.Frame(parent or self._content, bg=t.bg)
        frame.pack(fill=tk.X)

        top_h = STATS_TOP_LABEL_HEIGHT if token_data else 0
        canvas = tk.Canvas(
            frame,
            width=STATS_PANEL_WIDTH - 32,
            height=STATS_CHART_HEIGHT + top_h,
            bg=t.bg,
            highlightthickness=0,
        )
        canvas.pack(fill=tk.X)

        bar_bounds: list[tuple[int, int]] = []
        hovered_index: list[int] = [-1]

        def _draw(event=None):
            bar_bounds.clear()
            w = canvas.winfo_width()
            if w <= 1:
                w = STATS_PANEL_WIDTH - 32
            canvas.delete("all")

            selected_index = selected_index_fn() if selected_index_fn is not None else None
            disabled_indices = disabled_indices_fn() if disabled_indices_fn is not None else set()
            peak_indices = highlight_indices_fn() if highlight_indices_fn is not None else set()

            bar_area_h = STATS_BAR_MAX_HEIGHT
            label_h = STATS_CHART_HEIGHT - bar_area_h

            gap = max(3, w // (n * 6))
            bar_w = max(6, (w - gap * (n + 1)) // n)

            if top_h > 0 and token_data is not None:
                period = 7 if n >= 28 else 5 if n > 7 else 3
                show_label = set()
                for chunk_start in range(0, n, period):
                    best_idx, best_tot = -1, 0
                    for idx in range(chunk_start, min(chunk_start + period, len(token_data))):
                        tot = token_data[idx].get("input", 0) + token_data[idx].get("output", 0)
                        if tot > best_tot:
                            best_tot = tot
                            best_idx = idx
                    if best_idx >= 0:
                        show_label.add(best_idx)
                # Collision-suppression: drop label if two selected bars are too close
                sorted_labels = sorted(show_label)
                min_dist = bar_w * 3
                for a, b in zip(sorted_labels, sorted_labels[1:]):
                    dist = (gap + b * (bar_w + gap) + bar_w // 2) - (gap + a * (bar_w + gap) + bar_w // 2)
                    if dist < min_dist:
                        tot_a = token_data[a].get("input", 0) + token_data[a].get("output", 0)
                        tot_b = token_data[b].get("input", 0) + token_data[b].get("output", 0)
                        show_label.discard(a if tot_a <= tot_b else b)
            else:
                show_label = set()

            max_val = _chart_max_value(data, disabled_indices)

            for i, pct in enumerate(data):
                x1 = gap + i * (bar_w + gap)
                x2 = x1 + bar_w
                bar_bounds.append((x1, x2))
                is_disabled = i in disabled_indices
                is_selected = i == selected_index

                track_fill = _blend_color(t.bar_bg, t.bg, 0.35) if is_disabled else t.bar_bg
                canvas.create_rectangle(x1, top_h, x2, top_h + bar_area_h, fill=track_fill, outline="")
                normalized = _normalize_chart_value(pct, max_val)
                base_color = _bar_color(normalized)
                fill = _chart_bar_fill(
                    base_color,
                    t.bar_bg,
                    t.bg,
                    normalized,
                    self._chart_mode,
                    disabled=is_disabled,
                )

                if self._chart_mode == self._CHART_MODE_COLOR and not is_disabled:
                    canvas.create_rectangle(x1, top_h, x2, top_h + bar_area_h, fill=fill, outline="")
                elif pct > 0:
                    bh = max(STATS_BAR_MIN_HEIGHT, int(pct / max_val * bar_area_h))
                    y1 = top_h + bar_area_h - bh
                    canvas.create_rectangle(x1, y1, x2, top_h + bar_area_h, fill=fill, outline="")

                if is_selected:
                    canvas.create_rectangle(
                        x1 - 2,
                        top_h - 2,
                        x2 + 1,
                        top_h + bar_area_h + 1,
                        outline=t.chart_select_border,
                        width=1,
                    )

                if i in show_label and not is_disabled:
                    slot = token_data[i]
                    total = slot.get("input", 0) + slot.get("output", 0)
                    if total > 0:
                        cx = (x1 + x2) // 2
                        canvas.create_text(
                            cx,
                            top_h - 2,
                            text=f"{fmt_tokens(total)} \u25c6",
                            fill=t.fg,
                            font=(t.font_family, max(t.font_size - 2, 7)),
                            anchor="s",
                        )

                lbl = label_fn(i)
                if lbl:
                    cx = (x1 + x2) // 2
                    lbl_fill = (
                        t.chart_select_label
                        if is_selected
                        else _blend_color(t.fg_dim, t.bg, 0.45) if is_disabled else t.fg_dim
                    )
                    lbl_font = (
                        (t.font_family, max(t.font_size - 3, 7), "bold")
                        if is_selected
                        else (t.font_family, max(t.font_size - 3, 7))
                    )
                    canvas.create_text(
                        cx,
                        top_h + bar_area_h + 2 + label_h // 2,
                        text=lbl,
                        fill=lbl_fill,
                        font=lbl_font,
                        anchor="center",
                    )

            if peak_indices and bar_bounds:
                sorted_peak = sorted(i for i in peak_indices if 0 <= i < len(bar_bounds))
                if sorted_peak:
                    runs = []
                    run_start = sorted_peak[0]
                    prev = run_start
                    for idx in sorted_peak[1:]:
                        if idx == prev + 1:
                            prev = idx
                        else:
                            runs.append((run_start, prev))
                            run_start = idx
                            prev = idx
                    runs.append((run_start, prev))
                    line_y = top_h + bar_area_h + 2
                    for rs, re in runs:
                        lx1 = bar_bounds[rs][0]
                        lx2 = bar_bounds[re][1]
                        canvas.create_rectangle(lx1, line_y, lx2, line_y + 2, fill=t.peak_zone, outline="")

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
            disabled_indices = disabled_indices_fn() if disabled_indices_fn is not None else set()
            if idx >= 0 and idx not in disabled_indices and data[idx] > 0:
                self._token_panel.show(hover_fn(idx))
            else:
                self._token_panel.hide()

        def _on_leave(event):
            hovered_index[0] = -1
            self._token_panel.hide()

        def _on_click(event):
            if on_click is None or not bar_bounds:
                return
            disabled_indices = disabled_indices_fn() if disabled_indices_fn is not None else set()
            x = event.x
            for i, (x1, x2) in enumerate(bar_bounds):
                if x1 <= x <= x2:
                    if i not in disabled_indices:
                        on_click(i)
                    break

        canvas.bind("<Configure>", _draw)
        if hover_fn is not None:
            canvas.bind("<Motion>", _on_motion)
            canvas.bind("<Leave>", _on_leave)
        if on_click is not None:
            canvas.bind("<Button-1>", _on_click)
        self.root.after(10, _draw)
        return _draw

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
                self._pin_canvas.create_rectangle(0, 0, bar_w, 3, fill=t.bar_green, outline="")

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
        popup_h = self._popup_win.winfo_height()

        x = popup_x - panel_w - 4
        if x < 0:
            x = popup_x + self._popup_win.winfo_width() + 4
            self._open_slide_sign = -1
        else:
            self._open_slide_sign = 1

        screen_h = self.root.winfo_screenheight()
        popup_bottom = popup_y + popup_h
        y = max(0, min(popup_bottom - panel_h, screen_h - panel_h))

        self._open_final_x = x
        self._open_final_y = y

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
        alpha = (1.0 - t) ** 2
        self.win.attributes("-alpha", alpha)
        if t >= 1.0:
            self.win.attributes("-alpha", 1.0)
            self._close_anim_id = None
            self._close_anim_start = None
            self.win.withdraw()
        else:
            self._close_anim_id = self.root.after(ANIM_FRAME_MS, self._tick_close_animation)
