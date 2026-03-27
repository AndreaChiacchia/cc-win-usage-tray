# Claude Usage Tray

A Windows app that monitors [Claude Code](https://claude.ai/code) usage and shows session, weekly, and extra token budgets in a compact themed popup with alerts when thresholds are crossed.

![version](https://img.shields.io/badge/version-v1.10.1-blue)
![platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![python](https://img.shields.io/badge/build-python%203.10%2B-blue)
![license](https://img.shields.io/badge/license-Apache%202.0-green)

<!-- screenshot -->

---

## Features

- **Usage overview** - session, weekly, and extra token budgets in a compact popup with color-coded progress bars
- **Theming** - built-in themes let you customize the popup appearance
- **Threshold notifications** - Windows toasts when usage crosses configurable limits
- **Multi-account tracking** - keeps usage data for multiple Claude accounts and surfaces the active one first
- **Historical stats** - charts and token breakdowns to inspect recent usage trends, with peak-hour annotation
- **Peak times indicator** - configurable peak window shown in the bottom bar and highlighted on stats charts
- **Built for Claude Code CLI** - uses a PTY-based runner to fetch and parse live usage output automatically

---

## Requirements

- Windows 10 or 11
- [Claude Code CLI](https://claude.ai/code) installed and available on `PATH`

---

## Running the Executable

Download `ClaudeUsageTray.exe` from the [releases](https://github.com/AndreaChiacchia/cc-win-usage-tray/releases) page and run it directly — no Python required.

---

## Running from Source

Requires Python 3.10+.

```bash
cd src
pip install -r requirements.txt
python main.py
```

---

## Building the Executable

Requires Python 3.10+ and PyInstaller.

```bash
cd src
pyinstaller ../ClaudeUsageTray.spec
```

Output: `dist/ClaudeUsageTray.exe` - single file, no console window.

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

```text
src/
|-- main.py           # ClaudeUsageTray class - Tkinter loop, tray icon, refresh orchestration
|-- claude_runner.py  # Spawns Claude CLI via PTY; state machine extracts /usage output
|-- usage_parser.py   # Parses ANSI-stripped text into UsageData / UsageSection dataclasses
|-- ui_popup.py       # Borderless dark popup positioned above the taskbar
|-- icon_generator.py # Generates 64x64 RGBA tray icons (normal / loading / error)
|-- notifier.py       # Windows toast notifications for threshold crossings
|-- settings.py       # Per-account persistent settings (interval, threshold, toggle)
|-- config.py         # All constants: timeouts, colors, dimensions, refresh interval
|-- version.py        # Single source of truth for the app version
`-- requirements.txt  # Python dependencies
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
