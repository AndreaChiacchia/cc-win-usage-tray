"""Settings mixin for UsagePopup — account settings, threshold, and theme selector windows."""

import tkinter as tk

import theme as theme_mod
import settings as settings_mod
from config import POPUP_PADDING


class SettingsMixin:
    """Mixin providing settings/dialog windows for UsagePopup."""

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

        pace_var = tk.BooleanVar(value=settings_mod.get_pace_delta_enabled(email))

        def _on_pace_toggle():
            settings_mod.set_pace_delta_enabled(email, pace_var.get())
            self._rebuild_content()

        pace_cb = tk.Checkbutton(
            inner,
            text="Pace delta indicator",
            variable=pace_var,
            bg=t.bg, fg=t.fg,
            selectcolor=t.bar_bg,
            activebackground=t.bg, activeforeground=t.fg,
            font=t.font,
            anchor="w",
            command=_on_pace_toggle,
            **t.checkbutton_style_kwargs(),
        )
        pace_cb.pack(fill=tk.X, pady=(POPUP_PADDING // 2, 0))

        self._position_beside_popup(win, 380, 310)
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
            current_theme = theme_mod.current()
            sb_canvas.delete("all")
            h = sb_canvas.winfo_height()
            if h <= 1:
                h = scroll_height
            sb_canvas.create_rectangle(0, 0, SB_W, h, fill=current_theme.bar_bg, outline="")
            if last - first < 1.0:
                y1 = int(first * h)
                y2 = int(last * h)
                color = current_theme.fg if _sb_hover else current_theme.fg_dim
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
        apply_btn = tk.Button(
            inner,
            text="Apply",
            bg=t.button_bg, fg=t.button_fg,
            activebackground=t.button_active_bg, activeforeground=t.button_fg,
            padx=16, pady=4,
            font=t.font,
            cursor="hand2",
            command=lambda: _apply(),
            **t.button_style_kwargs(),
        )
        apply_btn.pack(side=tk.RIGHT)

        def _apply():
            name = selected_var.get()
            theme_mod.apply(name)
            settings_mod.set_theme_name(name)
            self.apply_theme()
            self._rebuild_content()

            # Re-theme the selector window itself
            new_t = theme_mod.current()
            outer = win.winfo_children()[0]
            win.configure(bg=new_t.bg)
            outer.configure(bg=new_t.border)
            inner.configure(bg=new_t.bg)
            title_bar.configure(bg=new_t.bg)
            for child in title_bar.winfo_children():
                if isinstance(child, tk.Label):
                    child.configure(bg=new_t.bg, fg=new_t.fg, font=new_t.font_bold)
                elif isinstance(child, tk.Button):
                    child.configure(bg=new_t.button_bg, fg=new_t.button_fg,
                                    activebackground=new_t.button_active_bg,
                                    activeforeground=new_t.button_fg, font=new_t.font)
            scroll_wrapper.configure(bg=new_t.bg)
            scroll_canvas.configure(bg=new_t.bg)
            sb_canvas.configure(bg=new_t.bar_bg)
            list_frame.configure(bg=new_t.bg)
            apply_btn.configure(bg=new_t.button_bg, fg=new_t.button_fg,
                                activebackground=new_t.button_active_bg,
                                activeforeground=new_t.button_fg, font=new_t.font)
            _update_sb(*scroll_canvas.yview())

            # Redraw all preview cards (checkmark updates for the new active theme)
            for n, c in card_canvases.items():
                _draw_card(c, themes_dict[n], n == name, is_custom_dict[n])

        win_h = scroll_height + POPUP_PADDING * 4 + 60
        self._position_beside_popup(win, CARD_W + POPUP_PADDING * 2 + 20, win_h)
        win.focus_force()
