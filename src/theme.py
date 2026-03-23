"""Theme system for Claude Usage Tray.

Built-in themes are defined here as frozen dataclasses.
Custom themes are loaded from ~/.ccwinusage/themes/*.json at runtime.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass

import settings as settings_mod
from paths import CUSTOM_THEMES_DIR


# ---------------------------------------------------------------------------
# Widget style presets
# ---------------------------------------------------------------------------

_WIDGET_STYLE_PRESETS: dict[str, dict] = {
    "flat": {
        "button":      {"relief": "flat",   "borderwidth": 0},
        "scale":       {"relief": "flat",   "borderwidth": 0, "sliderrelief": "flat"},
        "checkbutton": {"relief": "flat",   "borderwidth": 0},
    },
    "classic": {
        "button":      {"relief": "raised", "borderwidth": 2},
        "scale":       {"relief": "sunken", "borderwidth": 1, "sliderrelief": "raised"},
        "checkbutton": {"relief": "flat",   "borderwidth": 0},
    },
    "groove": {
        "button":      {"relief": "groove", "borderwidth": 1},
        "scale":       {"relief": "groove", "borderwidth": 1, "sliderrelief": "raised"},
        "checkbutton": {"relief": "groove", "borderwidth": 1},
    },
}


@dataclass(frozen=True)
class Theme:
    name: str
    # Colors
    bg: str
    fg: str
    fg_dim: str
    border: str
    bar_bg: str
    bar_green: str
    bar_yellow: str
    bar_red: str
    button_bg: str
    button_fg: str
    button_active_bg: str
    # Fonts
    font_family: str
    font_size: int
    font_size_bold: int
    # Widget style preset
    widget_style: str = "flat"

    @property
    def font(self) -> tuple:
        return (self.font_family, self.font_size)

    @property
    def font_bold(self) -> tuple:
        return (self.font_family, self.font_size_bold, "bold")

    @property
    def font_separator(self) -> tuple:
        return (self.font_family, 4)

    def _preset(self) -> dict:
        return _WIDGET_STYLE_PRESETS.get(self.widget_style, _WIDGET_STYLE_PRESETS["flat"])

    def button_style_kwargs(self) -> dict:
        return self._preset()["button"]

    def scale_style_kwargs(self) -> dict:
        return self._preset()["scale"]

    def checkbutton_style_kwargs(self) -> dict:
        return self._preset()["checkbutton"]


# ---------------------------------------------------------------------------
# Built-in theme definitions
# ---------------------------------------------------------------------------

CLAUDE_CODE = Theme(
    name="Claude Code",
    bg="#1e1e1e",
    fg="#e5e5e5",
    fg_dim="#8b8b8b",
    border="#333333",
    bar_bg="#2d2d2d",
    bar_green="#10b981",
    bar_yellow="#f59e0b",
    bar_red="#ef4444",
    button_bg="#2d2d2d",
    button_fg="#e5e5e5",
    button_active_bg="#3d3d3d",
    font_family="Segoe UI",
    font_size=10,
    font_size_bold=11,
    widget_style="flat",
)

TERMINAL = Theme(
    name="Terminal",
    bg="#0c0c0c",
    fg="#cccccc",
    fg_dim="#666666",
    border="#2a2a2a",
    bar_bg="#1a1a1a",
    bar_green="#00cc00",
    bar_yellow="#cccc00",
    bar_red="#cc0000",
    button_bg="#1a1a1a",
    button_fg="#cccccc",
    button_active_bg="#2a2a2a",
    font_family="Consolas",
    font_size=10,
    font_size_bold=11,
    widget_style="flat",
)

DRACULA = Theme(
    name="Dracula",
    bg="#282a36",
    fg="#f8f8f2",
    fg_dim="#6272a4",
    border="#44475a",
    bar_bg="#44475a",
    bar_green="#50fa7b",
    bar_yellow="#f1fa8c",
    bar_red="#ff5555",
    button_bg="#44475a",
    button_fg="#f8f8f2",
    button_active_bg="#6272a4",
    font_family="Consolas",
    font_size=10,
    font_size_bold=11,
    widget_style="flat",
)

LIGHT = Theme(
    name="Light",
    bg="#ffffff",
    fg="#1e1e1e",
    fg_dim="#767676",
    border="#d0d0d0",
    bar_bg="#f0f0f0",
    bar_green="#16a34a",
    bar_yellow="#d97706",
    bar_red="#dc2626",
    button_bg="#f0f0f0",
    button_fg="#1e1e1e",
    button_active_bg="#e0e0e0",
    font_family="Segoe UI",
    font_size=10,
    font_size_bold=11,
    widget_style="flat",
)

SOLARIZED_DARK = Theme(
    name="Solarized Dark",
    bg="#002b36",
    fg="#839496",
    fg_dim="#586e75",
    border="#073642",
    bar_bg="#073642",
    bar_green="#859900",
    bar_yellow="#b58900",
    bar_red="#dc322f",
    button_bg="#073642",
    button_fg="#839496",
    button_active_bg="#0d3c4a",
    font_family="Consolas",
    font_size=10,
    font_size_bold=11,
    widget_style="flat",
)

HIGH_CONTRAST = Theme(
    name="High Contrast",
    bg="#000000",
    fg="#ffffff",
    fg_dim="#aaaaaa",
    border="#555555",
    bar_bg="#1a1a1a",
    bar_green="#00ff00",
    bar_yellow="#ffff00",
    bar_red="#ff0000",
    button_bg="#1a1a1a",
    button_fg="#ffffff",
    button_active_bg="#333333",
    font_family="Consolas",
    font_size=10,
    font_size_bold=11,
    widget_style="flat",
)

BUILTIN_THEMES: dict[str, Theme] = {
    t.name: t for t in [CLAUDE_CODE, TERMINAL, DRACULA, LIGHT, SOLARIZED_DARK, HIGH_CONTRAST]
}

# ---------------------------------------------------------------------------
# Active theme state
# ---------------------------------------------------------------------------

_active: Theme = CLAUDE_CODE


def current() -> Theme:
    """Return the currently active theme."""
    return _active


def apply(name: str) -> None:
    """Set the active theme by name. Falls back to Claude Code if not found."""
    global _active
    _active = _resolve(name)


def _resolve(name: str) -> Theme:
    if name in BUILTIN_THEMES:
        return BUILTIN_THEMES[name]
    for theme_name, theme in _load_custom_themes():
        if theme_name == name:
            return theme
    return CLAUDE_CODE


def list_themes() -> list[tuple[str, Theme, bool]]:
    """Return (name, Theme, is_custom) tuples: custom themes first, then built-ins."""
    result: list[tuple[str, Theme, bool]] = []
    for name, th in _load_custom_themes():
        result.append((name, th, True))
    for name, th in BUILTIN_THEMES.items():
        result.append((name, th, False))
    return result


def _load_custom_themes() -> list[tuple[str, Theme]]:
    themes = []
    try:
        for fname in sorted(os.listdir(CUSTOM_THEMES_DIR)):
            if not fname.lower().endswith(".json"):
                continue
            path = os.path.join(CUSTOM_THEMES_DIR, fname)
            try:
                theme = load_custom_theme(path)
                themes.append((theme.name, theme))
            except Exception as e:
                print(f"[theme] skipping {fname}: {e}", file=sys.stderr)
    except Exception:
        pass
    return themes


def load_custom_theme(path: str) -> Theme:
    """Load a Theme from a JSON file. Raises ValueError if invalid."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    required = [
        "name", "bg", "fg", "fg_dim", "border", "bar_bg",
        "bar_green", "bar_yellow", "bar_red",
        "button_bg", "button_fg", "button_active_bg",
        "font_family", "font_size", "font_size_bold",
    ]
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"missing fields: {missing}")

    return Theme(
        name=data["name"],
        bg=data["bg"],
        fg=data["fg"],
        fg_dim=data["fg_dim"],
        border=data["border"],
        bar_bg=data["bar_bg"],
        bar_green=data["bar_green"],
        bar_yellow=data["bar_yellow"],
        bar_red=data["bar_red"],
        button_bg=data["button_bg"],
        button_fg=data["button_fg"],
        button_active_bg=data["button_active_bg"],
        font_family=data["font_family"],
        font_size=int(data["font_size"]),
        font_size_bold=int(data["font_size_bold"]),
        widget_style=data.get("widget_style", "flat"),
    )


# ---------------------------------------------------------------------------
# Initialize active theme from persisted setting on import
# ---------------------------------------------------------------------------

def _init():
    saved = settings_mod.get_theme_name()
    apply(saved)


_init()
