# GEMINI.md

This file provides guidance to Gemini (Gemini CLI) when working with code in this repository.

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
7. Switch back to `staging`, fast-forward merge `main` into it, and push: `git checkout staging && git merge main && git push origin staging`.
8. Compile a changelog from commits since the last tag. Each entry is one line prefixed with its type (`feat:`, `fix:`, etc.) followed by a concise summary and the short commit hash. No section grouping. Tag on `main` with an annotated tag containing the changelog: `git tag -a v{version} -m "$(changelog)"` and push the tag.

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

## Design Context

Full details in [`.impeccable.md`](.impeccable.md). Summary for quick reference:

### Users
Developers using Claude Code CLI who want at-a-glance visibility into token budgets. They interact passively — the popup is a quick check-in, not a workflow destination.

### Brand Personality
**Technical + polished/premium.** Three-word anchor: **precise, composed, crafted.**
Base visual reference: Claude.ai (dark, modern, warm dark grays with subtle polish). The app has its own identity and full custom theming — don't copy Claude.ai literally, but match its quality bar.

### Emotional Goals
1. **Awareness** — Usage data must be instantly legible; hierarchy and color do the work.
2. **Delight** — Small purposeful polish moments (smooth bar-fill, shimmer on load, clean transitions). Nothing gratuitous.

### Design Principles
1. **Data clarity first.** No visual noise that competes with numbers.
2. **Polish at the detail level.** Quality lives in consistent spacing (4px grid), precise colors, smooth easing — not in complexity.
3. **Technical confidence.** System fonts, crisp sizes, monospace for numeric values, precise threshold colors (not soft pastels).
4. **Unobtrusive by default, expressive when needed.** Quiet when usage is low; progressively urgent (green → amber → red) as limits approach.
5. **WCAG AA as the floor.** All built-in themes must meet 4.5:1 contrast ratio for text.

### Key Tokens (Default Theme)
- Background: `#1e1e1e` | Text: `#e5e5e5` | Dim text: `#8b8b8b` | Border: `#333333`
- Green: `#10b981` | Amber: `#f59e0b` | Red: `#ef4444`
- Font: Segoe UI 10pt | Popup width: 520px | Padding: 24px | Bar height: 18px | No border-radius
