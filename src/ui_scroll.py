"""Scroll mixin for UsagePopup — custom scrollbar and scroll canvas logic."""

import tkinter as tk

import theme as theme_mod
from config import POPUP_MAX_CONTENT_HEIGHT


class ScrollMixin:
    """Mixin providing scroll-canvas and custom scrollbar logic for UsagePopup."""

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
