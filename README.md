# Claude Usage Tray

A Windows system tray application that monitors [Claude Code](https://claude.ai/code) usage in real time — session, weekly, and extra tokens — with a dark-themed popup, color-coded progress bars, and Windows toast notifications.

![version](https://img.shields.io/badge/version-v1.7.0-blue)
![platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![license](https://img.shields.io/badge/license-Apache%202.0-green)

<!-- screenshot -->

---

## Features

- **System tray icon** — dynamic states (normal / loading / error), right-click menu, tooltip showing live usage percentages
- **Dark-themed popup** — terminal aesthetic, Consolas font, positioned just above the taskbar, auto-dismisses on focus loss, includes a close button
- **Color-coded progress bars** — green (< 50 %), yellow (50–79 %), red (≥ 80 %) with smooth animated fills, toggleable shimmer refresh effect, syncing dots indicator, and inline animated spent amount
- **Draggable popup** — drag the title bar to reposition anywhere (including across monitors); position persists across restarts; falls back to bottom-right corner
- **Always-on-top toggle** — tray menu checkbox (default: on) to control whether the popup stays above other windows; persists across restarts
- **Theming system** — built-in themes selectable from the tray menu
- **Multi-account support** — tracks all accounts simultaneously; the active account is shown first, historical data is preserved across refreshes
- **Relative / cooldown time display** — per-account toggle to switch between absolute and relative time remaining
- **Windows toast notifications** — fired when usage crosses configurable threshold boundaries, with per-account toggle, per-section step (default 10 %), and per-account pace delta suffix showing rate of change
- **Stats panel** — historical usage charts (hourly today, daily this week Mon–Sun, daily this month) with color-coded bars, extra-spend summaries, and animated open (slide+fade) / close transitions
- **Per-account settings** — refresh interval (1–30 min), notification threshold, notifications on/off
- **PTY-based CLI integration** — a state machine handles the Claude CLI banner, the first-run trust dialog, `/status`, and `/usage` commands automatically

---

## Requirements

- Windows 10 or 11
- Python 3.10+
- [Claude Code CLI](https://claude.ai/code) installed and available on `PATH`

---

## Installation & Running

```bash
cd src
pip install -r requirements.txt
python main.py
```

---

## Building the Executable

```bash
cd src
pyinstaller ../ClaudeUsageTray.spec
```

Output: `dist/ClaudeUsageTray.exe` — single file, no console window.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `pystray` | System tray icon and menu |
| `Pillow` | Tray icon generation |
| `pywinpty` | PTY to spawn the Claude CLI |
| `winotify` | Windows toast notifications |
| `pywin32` | Win32 API (taskbar positioning, window focus) |

---

## Project Structure

```
src/
├── main.py           # ClaudeUsageTray class — Tkinter loop, tray icon, refresh orchestration
├── claude_runner.py  # Spawns Claude CLI via PTY; state machine extracts /usage output
├── usage_parser.py   # Parses ANSI-stripped text into UsageData / UsageSection dataclasses
├── ui_popup.py       # Borderless dark popup positioned above the taskbar
├── icon_generator.py # Generates 64×64 RGBA tray icons (normal / loading / error)
├── notifier.py       # Windows toast notifications for threshold crossings
├── settings.py       # Per-account persistent settings (interval, threshold, toggle)
├── config.py         # All constants: timeouts, colors, dimensions, refresh interval
├── version.py        # Single source of truth for the app version
└── requirements.txt  # Python dependencies
```

---

## How It Works

1. Spawns the Claude Code CLI inside a PTY using `pywinpty`.
2. A state machine drives the session: waits for the banner, auto-confirms any first-run trust dialog, then sends `/status` followed by `/usage`.
3. Raw PTY output is buffered in a `queue.Queue` and ANSI-stripped before parsing.
4. `usage_parser.py` extracts usage sections with regex into typed dataclasses.
5. The Tkinter popup and tray icon are rebuilt on every refresh cycle.
6. Windows toasts fire when usage crosses a boundary in either direction.

### Threading model

| Thread | Role |
|--------|------|
| Tkinter main thread | All UI updates via `root.after(0, ...)` |
| PTY reader thread | Reads raw PTY output; state machine runs on a daemon thread |
| pystray thread | Marshals menu callbacks back to the Tkinter thread |

---

## License

Copyright 2026 Andrea Chiacchiaretta

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for the full text.
