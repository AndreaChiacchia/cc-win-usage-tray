"""Token Detail Panel — shows per-bar token breakdown on hover over stats panel charts.

Borderless Toplevel positioned to the left of the stats panel (falls back to
right when there is no room).  Triggered by hovering over a bar in any chart.

States
------
hidden      Default; window is withdrawn.
previewing  Window visible; thin pin-progress bar fills over STATS_PIN_DURATION_MS.
            Moving away before the bar completes → back to hidden.
pinned      Bar completed; panel stays open regardless of mouse position.
            A close button in the header dismisses it.
"""

import time
import tkinter as tk

import theme as theme_mod
from config import (
    ANIM_FRAME_MS,
    STATS_PIN_DURATION_MS,
    STATS_OPEN_DURATION_MS, STATS_OPEN_SLIDE_PX, STATS_CLOSE_DURATION_MS,
    TOKEN_PANEL_WIDTH,
)
from format_utils import fmt_tokens as _fmt


class TokenDetailPanel:
    """Hover-triggered token detail panel shown to the left of the stats panel."""

    _HIDDEN = "hidden"
    _PREVIEWING = "previewing"
    _PINNED = "pinned"

    def __init__(self, root: tk.Tk, stats_win: tk.Toplevel):
        self.root = root
        self._stats_win = stats_win
        self._state = self._HIDDEN
        self._slot_data: dict | None = None

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

        # Content area
        self._content = tk.Frame(self._inner, bg=t.bg, padx=16, pady=16)
        self._content.pack(fill=tk.BOTH, expand=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show(self, slot_data: dict) -> None:
        """Show (or update) the panel with token data for a hovered bar slot.

        slot_data keys: label, input, output, cache_read, cache_creation
        """
        currently_closing = self._close_anim_start is not None
        self._cancel_close_animation()
        already_visible = self._state != self._HIDDEN or currently_closing
        was_pinned = self._state == self._PINNED
        self._slot_data = slot_data

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
        """Force-hide regardless of pin state."""
        self._cancel_open_animation()
        self._cancel_pin_animation()
        self._state = self._HIDDEN
        self._slot_data = None
        self._start_close_animation()

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
        panel_w = TOKEN_PANEL_WIDTH
        panel_h = self.win.winfo_reqheight()

        stats_x = self._stats_win.winfo_x()
        stats_y = self._stats_win.winfo_y()

        x = stats_x - panel_w - 4
        if x < 0:
            x = stats_x + self._stats_win.winfo_width() + 4

        screen_h = self.root.winfo_screenheight()
        y = max(0, min(stats_y, screen_h - panel_h))

        self.win.geometry(f"{panel_w}x{panel_h}+{x}+{y}")

    def _rebuild_content(self) -> None:
        for w in self._content.winfo_children():
            w.destroy()

        t = theme_mod.current()
        data = self._slot_data

        # --- Header ---
        header_row = tk.Frame(self._content, bg=t.bg)
        header_row.pack(fill=tk.X, pady=(0, 12))

        label_text = data["label"] if data else "—"
        tk.Label(
            header_row,
            text=label_text,
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

        if data is None:
            tk.Label(
                self._content,
                text="No token data",
                bg=t.bg, fg=t.fg_dim,
                font=t.font,
            ).pack()
            self.win.update_idletasks()
            return

        inp = data.get("input", 0)
        out = data.get("output", 0)
        cache_read = data.get("cache_read", 0)
        cache_creation = data.get("cache_creation", 0)
        total = inp + out

        if total == 0 and cache_read == 0 and cache_creation == 0:
            tk.Label(
                self._content,
                text="No token data",
                bg=t.bg, fg=t.fg_dim,
                font=t.font,
            ).pack()
            self.win.update_idletasks()
            return

        # --- Hero total ---
        hero_font = (t.font_family, t.font_size + 6, "bold")
        tk.Label(
            self._content,
            text=_fmt(total),
            bg=t.bg, fg=t.fg,
            font=hero_font,
            anchor="center",
        ).pack(fill=tk.X)

        subtitle_font = (t.font_family, max(t.font_size - 2, 7))
        tk.Label(
            self._content,
            text="total tokens",
            bg=t.bg, fg=t.fg_dim,
            font=subtitle_font,
            anchor="center",
        ).pack(fill=tk.X, pady=(0, 12))

        if total > 0:
            # --- Segmented bar ---
            bar_canvas = tk.Canvas(
                self._content,
                height=14,
                bg=t.bg,
                highlightthickness=0,
            )
            bar_canvas.pack(fill=tk.X, pady=(0, 8))

            def _draw_bar(event=None):
                w = bar_canvas.winfo_width()
                if w <= 1:
                    w = TOKEN_PANEL_WIDTH - 32
                bar_canvas.delete("all")
                # Background track
                bar_canvas.create_rectangle(0, 0, w, 14, fill=t.bar_bg, outline="")
                inp_w = int(w * inp / total)
                if inp_w > 0:
                    bar_canvas.create_rectangle(0, 0, inp_w, 14, fill=t.bar_green, outline="")
                if inp_w < w:
                    bar_canvas.create_rectangle(inp_w, 0, w, 14, fill=t.bar_yellow, outline="")

            bar_canvas.bind("<Configure>", _draw_bar)
            self.root.after(10, _draw_bar)

            # --- Legend row ---
            legend = tk.Frame(self._content, bg=t.bg)
            legend.pack(fill=tk.X, pady=(0, 12))

            self._legend_item(legend, t, t.bar_green, f"Input  {_fmt(inp)}")
            self._legend_item(legend, t, t.bar_yellow, f"Output  {_fmt(out)}")

        # --- Separator ---
        tk.Frame(self._content, bg=t.border, height=1).pack(fill=tk.X, pady=(0, 8))

        # --- Cache rows ---
        self._cache_row(t, "Cache read", cache_read)
        self._cache_row(t, "Cache created", cache_creation)

        self.win.update_idletasks()

    def _legend_item(self, parent, t, color: str, text: str) -> None:
        row = tk.Frame(parent, bg=t.bg)
        row.pack(side=tk.LEFT, padx=(0, 12))
        # Colored square
        sq = tk.Canvas(row, width=10, height=10, bg=t.bg, highlightthickness=0)
        sq.pack(side=tk.LEFT, padx=(0, 4))
        sq.create_rectangle(0, 0, 10, 10, fill=color, outline="")
        tk.Label(row, text=text, bg=t.bg, fg=t.fg, font=t.font).pack(side=tk.LEFT)

    def _cache_row(self, t, label: str, value: int) -> None:
        row = tk.Frame(self._content, bg=t.bg)
        row.pack(fill=tk.X, pady=(4, 0))
        tk.Label(row, text=label, bg=t.bg, fg=t.fg_dim, font=t.font, anchor="w").pack(
            side=tk.LEFT
        )
        tk.Label(row, text=_fmt(value), bg=t.bg, fg=t.fg_dim, font=t.font, anchor="e").pack(
            side=tk.RIGHT
        )

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
                w = TOKEN_PANEL_WIDTH - 2
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
        panel_w = TOKEN_PANEL_WIDTH
        panel_h = self.win.winfo_reqheight()

        stats_x = self._stats_win.winfo_x()
        stats_y = self._stats_win.winfo_y()

        x = stats_x - panel_w - 4
        if x < 0:
            x = stats_x + self._stats_win.winfo_width() + 4
            self._open_slide_sign = -1
        else:
            self._open_slide_sign = 1

        screen_h = self.root.winfo_screenheight()
        y = max(0, min(stats_y, screen_h - panel_h))

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
        panel_w = TOKEN_PANEL_WIDTH
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
        alpha = (1.0 - t) ** 2
        self.win.attributes("-alpha", alpha)
        if t >= 1.0:
            self.win.attributes("-alpha", 1.0)
            self._close_anim_id = None
            self._close_anim_start = None
            self.win.withdraw()
        else:
            self._close_anim_id = self.root.after(ANIM_FRAME_MS, self._tick_close_animation)
