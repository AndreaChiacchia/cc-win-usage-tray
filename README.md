# Claude Usage Tray

Sits in the Windows system tray and shows your [Claude Code](https://claude.ai/code) token budgets — session, weekly, and extra — in a compact themed popup. Fires toast notifications when usage crosses a threshold.

![version](https://img.shields.io/badge/version-v1.10.1-blue)
![platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![python](https://img.shields.io/badge/build-python%203.10%2B-blue)
![license](https://img.shields.io/badge/license-Apache%202.0-green)

<!-- screenshot -->

---

## Features

- Session, weekly, and extra token budgets in a compact popup with color-coded progress bars
- Built-in themes to customize the popup appearance
- Windows toast notifications when usage crosses configurable thresholds
- Tracks multiple Claude accounts; the active one shows at the top
- Historical stats with charts, token breakdowns, and peak-hour annotation
- Configurable peak times window shown in the bottom bar and on stats charts
- PTY-based runner fetches and parses live Claude CLI output without stealing focus

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
5. The popup and tray icon update on every refresh cycle.
6. Windows toasts fire when usage crosses a threshold boundary.

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
