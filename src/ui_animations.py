"""Animation mixin for UsagePopup — shimmer, syncing dots, bar fill, pace delta."""

import time
import tkinter as tk

import theme as theme_mod
from config import (
    BAR_HEIGHT, ANIM_FRAME_MS, ANIM_BAR_DURATION_MS,
    ANIM_SHIMMER_WIDTH, ANIM_SHIMMER_SPEED,
    ANIM_PACE_DURATION_MS, COLOR_GREEN_MAX, COLOR_YELLOW_MAX,
)


def _lighten_color(hex_color: str, factor: float = 0.3) -> str:
    """Blend a hex color toward white by factor (0=unchanged, 1=white)."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


def _blend_color(c1: str, c2: str, t: float) -> str:
    """Linearly interpolate between two hex colors by factor t (0=c1, 1=c2)."""
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    return f"#{int(r1+(r2-r1)*t):02x}{int(g1+(g2-g1)*t):02x}{int(b1+(b2-b1)*t):02x}"


def _bar_color(percentage: int) -> str:
    t = theme_mod.current()
    if percentage < COLOR_GREEN_MAX:
        return t.bar_green
    elif percentage < COLOR_YELLOW_MAX:
        return t.bar_yellow
    else:
        return t.bar_red


class AnimationsMixin:
    """Mixin providing shimmer, syncing-dots, bar-fill, and pace-delta animations."""

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

    def _animate_pace_delta(self, key: tuple, old_delta: int | None, new_delta: int | None):
        """Animate a pace label transition (materialize, dissolve, count, crossfade)."""
        start = time.monotonic()
        gen = self._anim_generation
        t = theme_mod.current()

        disappearing = old_delta is not None and new_delta is None
        duration = 0.300 if disappearing else ANIM_PACE_DURATION_MS / 1000.0

        val_from = old_delta if old_delta is not None else 0
        val_to = new_delta if new_delta is not None else 0
        color_from = t.bar_green if (old_delta or 0) >= 0 else t.bar_red
        color_to = t.bar_green if (new_delta or 0) >= 0 else t.bar_red
        appearing = old_delta is None and new_delta is not None

        def _tick():
            if gen != self._anim_generation:
                return
            refs = self._bar_widgets.get(key)
            if not refs:
                return
            pace_lbl = refs.get("pace_label")
            if not pace_lbl or not pace_lbl.winfo_exists():
                return

            elapsed = time.monotonic() - start
            raw_t = min(elapsed / duration, 1.0)
            progress = 1.0 - (1.0 - raw_t) ** 2  # ease-out-quad

            current = round(val_from + (val_to - val_from) * progress)
            sign = "+" if current >= 0 else ""
            pace_lbl.configure(text=f"[{sign}{current}%]")

            if appearing:
                fg = _blend_color(t.bg, color_to, progress)
            elif disappearing:
                fg = _blend_color(color_from, t.bg, progress)
            else:
                fg = _blend_color(color_from, color_to, progress)
            pace_lbl.configure(fg=fg)

            if raw_t < 1.0:
                aid = self.root.after(ANIM_FRAME_MS, _tick)
                self._anim_after_ids.append(aid)
            elif disappearing:
                pace_lbl.configure(text="")

        aid = self.root.after(0, _tick)
        self._anim_after_ids.append(aid)
