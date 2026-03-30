---
name: stack
description: Technology stack, library choices, and the reasoning behind them. Load when working with specific technologies or making decisions about libraries and tools.
triggers:
  - "library"
  - "package"
  - "dependency"
  - "which tool"
  - "technology"
edges:
  - target: context/decisions.md
    condition: when the reasoning behind a tech choice is needed
  - target: context/conventions.md
    condition: when understanding how to use a technology in this codebase
  - target: context/pty-runner.md
    condition: when working with pywinpty or PTY session details
last_updated: 2026-03-30
---

# Stack

## Core Technologies

- **Python 3.10+** — primary language; uses `X | Y` union type syntax in annotations
- **Tkinter** — UI framework for the popup window (stdlib; no extra install)
- **SQLite** (stdlib `sqlite3`) — persistence for accounts, usage snapshots, and token history
- **PyInstaller** — builds the single-file `ClaudeUsageTray.exe` (spec: `ClaudeUsageTray.spec` in repo root)

## Key Libraries

- **`pystray`** — system tray icon and right-click menu; runs in a daemon thread separate from Tkinter
- **`pywinpty`** (`winpty`) — PTY to spawn the Claude CLI; essential for capturing interactive terminal output that subprocess cannot handle
- **`winotify`** — Windows toast notifications (not `plyer` or `win10toast`); requires Start Menu shortcut with AUMID
- **`pywin32`** — Win32 API for taskbar positioning, window focus, and shortcut property store (AUMID)
- **`Pillow`** — RGBA tray icon generation (normal / loading / error states)

## What We Deliberately Do NOT Use

- **No asyncio** — threading + `root.after()` is the concurrency model; mixing asyncio with Tkinter adds complexity for no gain
- **No ORM** — SQLite accessed directly via `sqlite3` through the `db.py` singleton; queries are in `storage.py` and `db.py` only
- **No subprocess for Claude CLI** — Claude's interactive terminal features require a real PTY; `subprocess.Popen` cannot capture the output correctly

## Version Constraints

Python 3.10+ is required for the `X | Y` union type annotation syntax used in type hints throughout the codebase (e.g., `str | None`, `dict[str, AccountUsage]`). The built executable requires Windows 10 or 11.
