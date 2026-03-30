---
name: setup
description: Dev environment setup and commands. Load when setting up the project for the first time or when environment issues arise.
triggers:
  - "setup"
  - "install"
  - "environment"
  - "getting started"
  - "how do I run"
  - "local development"
edges:
  - target: context/stack.md
    condition: when specific technology versions or library details are needed
  - target: context/architecture.md
    condition: when understanding how components connect during setup
  - target: context/pty-runner.md
    condition: when the Claude CLI is not being found or PTY fails to spawn
last_updated: 2026-03-30
---

# Setup

## Prerequisites

- Windows 10 or 11
- Python 3.10+ (for source run and building the exe)
- Claude Code CLI installed and available on `PATH` (or in common locations — see `_resolve_claude_path()` in `claude_runner.py`)

## First-time Setup

1. Clone the repo
2. `cd src`
3. `pip install -r requirements.txt`
4. `python main.py`

The app creates `~/.ccwinusage/` on first run and migrates any legacy JSON files automatically.

## Environment Variables

None required. The app locates Claude CLI via `PATH` and writes all data to `~/.ccwinusage/`.

## Common Commands

- **Run from source:** `cd src && python main.py`
- **Build exe:** `cd src && pyinstaller ../ClaudeUsageTray.spec` → output: `dist/ClaudeUsageTray.exe`
- **Debug log (raw PTY output):** `~/.ccwinusage/logs/usage_output_debug.txt` — written on every refresh
- **Notifier log:** `~/.ccwinusage/logs/notifier_debug.log` — written on toast failures or shortcut creation issues
- **Settings file:** `~/.ccwinusage/user_settings.json`
- **Database:** `~/.ccwinusage/usage.db` (SQLite, WAL mode)

## Common Issues

**Claude CLI not found on PATH:**
Check `_resolve_claude_path()` in `claude_runner.py`. It probes `~/.local/bin/claude.exe`, `~/AppData/Local/Programs/claude/claude.exe`, and `%APPDATA%/npm/claude.cmd` as fallbacks. Add a candidate there if the install location differs.

**PTY hangs waiting for banner:**
Check `~/.ccwinusage/logs/usage_output_debug.txt` for what the PTY actually received. If the CLI shows a trust dialog at a different path, `_TRUST_PROMPT_RE` in `claude_runner.py` may need updating. If the banner never appears, `_BANNER_FALLBACK_S` (8s) kicks in — increase it if startup is slow.

**Toast notifications not appearing:**
Check `~/.ccwinusage/logs/notifier_debug.log`. Most common cause: `_ensure_shortcut()` failed to create the Start Menu shortcut with AUMID. Ensure `pywin32` is installed correctly. Running as administrator can help diagnose permission issues.

**Stats panel shows no token data:**
`token_history.py` scans `~/.claude/projects/**/*.jsonl`. If Claude Code data dir is in a non-standard location, `CLAUDE_DATA_DIR` in `config.py` may need updating.
