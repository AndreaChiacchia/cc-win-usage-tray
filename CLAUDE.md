# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Windows system tray application that monitors Claude Code usage (session, weekly, extra) by spawning the Claude Code CLI in a PTY, sending `/usage`, and parsing the output. Displays a color-coded popup and tray icon.

## Versioning

> **MANDATORY — do this before every commit, no exceptions.**

Version source: `src/version.py` (`__version__ = "x.y.z"`).

Follow SemVer:
- **MAJOR** — breaking changes
- **MINOR** — new features, backwards-compatible
- **PATCH** — bug fixes

**Required steps on every commit:**
1. Decide if the change warrants a bump (features → MINOR, fixes → PATCH).
2. If yes: update `src/version.py`, then commit the version file together with the changes.
3. Create and push the tag: `git tag v{version} && git push origin v{version}`.

Never commit code changes without completing these steps first.

## Setup & Running

All source files live in `src/`. Run from there:

```bash
cd src
pip install -r requirements.txt

# Run the app
python main.py

# Run the parser smoke test (no CLI required)
python test_parser.py
```

## Building the Executable

The spec file `ClaudeUsageTray.spec` is configured for PyInstaller and must be run from `src/`:

```bash
cd src
pyinstaller ../ClaudeUsageTray.spec
```

Output: `dist/ClaudeUsageTray.exe` (single-file, no console window).

## Architecture

The app is split into modules, all in `src/`:

| Module | Responsibility |
|---|---|
| `main.py` | `ClaudeUsageTray` class — owns the Tkinter main loop, pystray tray icon, and orchestrates refresh cycles |
| `claude_runner.py` | Spawns Claude CLI via `winpty` PTY, drives a state machine (`WAITING_FOR_BANNER → SENDING_USAGE → CAPTURING → DONE`) to extract `/usage` output |
| `usage_parser.py` | Parses the ANSI-stripped text into `UsageData` / `UsageSection` dataclasses using regex |
| `ui_popup.py` | Borderless Tkinter popup positioned above the taskbar; rebuilt on each refresh |
| `icon_generator.py` | Generates 64×64 RGBA tray icons (normal/loading/error) using Pillow |
| `config.py` | All constants: timeouts, colors, dimensions, refresh interval |
| `notifier.py` | Windows toast notifications for usage threshold crossings |
| `settings.py` | Per-account persistent settings (refresh interval, notification threshold) |
| `version.py` | Single source of truth for the app version (`__version__`) |

### Threading model

- **Tkinter main thread**: owns all UI updates. All cross-thread calls use `root.after(0, ...)`.
- **PTY reader thread** (in `claude_runner.py`): reads raw PTY output into a `queue.Queue`; the state machine loop runs on a separate daemon thread started by `run_usage_threaded()`.
- **pystray thread**: menu callbacks marshal back to the Tkinter thread via `root.after`.

### PTY state machine (`claude_runner.py`)

The runner handles three startup scenarios: normal banner, first-run trust dialog (auto-confirmed by sending `\r`), and a fallback timeout if neither appears. After the banner, it sends `/usage\r` and collects output until `_USAGE_HEADER_RE` matches.

### Color thresholds

Defined in `config.py`: green < 50%, yellow 50–79%, red ≥ 80%. Applied consistently in both `icon_generator.py` and `ui_popup.py`.
