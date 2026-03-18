"""Generate dynamic system tray icons using the Claude logo as a base."""

import os
import sys
from PIL import Image, ImageDraw
from config import (
    ICON_SIZE, COLOR_GREEN_MAX, COLOR_YELLOW_MAX,
    BAR_GREEN, BAR_YELLOW, BAR_RED, BG_COLOR
)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color string to RGB tuple."""
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _pct_color(percentage: int) -> tuple[int, int, int]:
    """Return RGB color based on usage percentage."""
    if percentage < COLOR_GREEN_MAX:
        return _hex_to_rgb(BAR_GREEN)
    elif percentage < COLOR_YELLOW_MAX:
        return _hex_to_rgb(BAR_YELLOW)
    else:
        return _hex_to_rgb(BAR_RED)


def _get_logo_path() -> str:
    """Get the path to claude_icon.png, handling both dev and PyInstaller."""
    # When bundled by PyInstaller, files are in sys._MEIPASS
    if getattr(sys, '_MEIPASS', None):
        return os.path.join(sys._MEIPASS, 'claude_icon.png')
    return os.path.join(os.path.dirname(__file__), 'claude_icon.png')


def _load_logo() -> Image.Image:
    """Load and return the Claude logo PNG."""
    path = _get_logo_path()
    return Image.open(path).convert("RGBA").resize((ICON_SIZE, ICON_SIZE), Image.NEAREST)


def generate_icon(max_percentage: int = 0) -> Image.Image:
    """
    Generate a 64x64 RGBA tray icon using the Claude logo.
    """
    return _load_logo()


def generate_loading_icon() -> Image.Image:
    """Generate a loading icon: the Claude logo slightly dimmed."""
    size = ICON_SIZE
    img = _load_logo()

    # Dim the logo by blending with a semi-transparent dark overlay
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 100))
    img = Image.alpha_composite(img, overlay)

    return img


def generate_error_icon() -> Image.Image:
    """Generate an error icon: the Claude logo slightly dimmed."""
    size = ICON_SIZE
    img = _load_logo()

    # Dim the logo to indicate error
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 120))
    img = Image.alpha_composite(img, overlay)

    return img
