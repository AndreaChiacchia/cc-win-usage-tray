"""Monitor/drag mixin for UsagePopup — Win32 monitor info, drag support, screen-change guard."""

import ctypes
import ctypes.wintypes

import settings as settings_mod


class MonitorMixin:
    """Mixin providing monitor-relative positioning, drag support, and screen-change guard."""

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
