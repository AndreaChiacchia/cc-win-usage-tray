# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Windows system tray application that monitors Claude Code usage (session, weekly, extra) by spawning the Claude Code CLI in a PTY, sending `/usage`, and parsing the output. Displays a color-coded popup and tray icon.

## Versioning

Version source: `src/version.py` (`__version__ = "x.y.z"`).

Follow SemVer:
- **MAJOR** — breaking changes
- **MINOR** — new features (or a commit that includes both features and fixes)
- **PATCH** — bug fixes only

**Version bump and tagging happen on `main` only.** On feature branches, commit without bumping the version.

**Merge procedure (staging → main):**
1. Determine the SemVer level from commits since the last bump (higher level wins if mixed).
2. Bump `src/version.py` on `staging` and commit it there.
3. Update the version badge in `README.md` to match the new version, and check if any other README content needs updating (new features, changed behavior, etc.). Commit on `staging`.
4. Push `staging` to remote.
5. Switch to `main`, merge `staging`.
6. Push `main`.
7. Compile a changelog from commits since the last tag. Each entry is one line prefixed with its type (`feat:`, `fix:`, etc.) followed by a concise summary and the short commit hash. No section grouping. Tag on `main` with an annotated tag containing the changelog: `git tag -a v{version} -m "$(changelog)"` and push the tag.

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
| `ui_popup.py` | `UsagePopup` class — core popup logic (init, show/hide, content build, theme); inherits all four UI mixins below |
| `ui_scroll.py` | `ScrollMixin` — custom scrollbar and scroll canvas logic |
| `ui_animations.py` | `AnimationsMixin` — shimmer, syncing dots, bar-fill, pace-delta animations; also exports `_bar_color`, `_lighten_color`, `_blend_color` helpers |
| `ui_monitor.py` | `MonitorMixin` — Win32 monitor info, drag support, screen-change guard |
| `ui_settings.py` | `SettingsMixin` — account settings, notification threshold, and theme selector windows |
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

### UI popup mixin architecture

`UsagePopup` uses Python mixins to keep the popup module manageable. The class declaration is:

```python
class UsagePopup(SettingsMixin, AnimationsMixin, MonitorMixin, ScrollMixin):
```

Each mixin lives in its own file and defines methods that operate on `self` — no parameter-passing overhead, no interface changes. All shared state (widget refs, animation IDs, etc.) is initialised in `UsagePopup.__init__`. When adding new popup behaviour, place it in the most relevant mixin rather than in `ui_popup.py` directly.

### Color thresholds

Defined in `config.py`: green < 50%, yellow 50–79%, red ≥ 80%. Applied consistently in both `icon_generator.py` and `ui_animations.py` (`_bar_color`).
