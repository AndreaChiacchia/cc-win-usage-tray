---
name: architecture
description: How the major pieces of this project connect and flow. Load when working on system design, integrations, or understanding how components interact.
triggers:
  - "architecture"
  - "system design"
  - "how does X connect to Y"
  - "integration"
  - "flow"
edges:
  - target: context/stack.md
    condition: when specific technology details are needed
  - target: context/decisions.md
    condition: when understanding why the architecture is structured this way
  - target: context/pty-runner.md
    condition: when working on or debugging the Claude CLI capture pipeline
  - target: context/data-layer.md
    condition: when working on storage, history, or database schema
last_updated: 2026-03-30
---

# Architecture

## System Overview

`ClaudeUsageTray` (main.py) owns the Tkinter event loop and the pystray tray icon in a daemon thread. On a configurable timer, `_trigger_refresh()` calls `run_usage_threaded()` which dispatches to the `ClaudePtySession` singleton. The singleton spawns the Claude CLI once via PTY (`pywinpty`), sends `/status` then `/usage`, and returns ANSI-stripped text. The text is parsed by `usage_parser.py` into `UsageData` / `AccountUsage` dataclasses. Results are persisted to SQLite via `storage.py` (using the `db.py` singleton connection) and the `notifier.py` compares old vs new percentages to fire Windows toast notifications. The `UsagePopup` (ui_popup.py) is updated on the Tkinter thread via `root.after()` — pystray callbacks must never touch Tkinter directly.

## Key Components

- **`ClaudeUsageTray`** (main.py) — app coordinator: owns Tkinter root, refresh orchestration, and the tray menu. All cross-thread UI calls go through `self.root.after()`.
- **`ClaudePtySession`** (claude_runner.py) — module-level singleton; spawns Claude CLI once via `winpty.PtyProcess.spawn()`, reuses the session across refresh cycles. Handles trust dialog, banner wait, and the resize-trick before `/usage`.
- **`UsagePopup`** (ui_popup.py) — borderless `tk.Toplevel` composed via mixins: `AnimationsMixin`, `ScrollMixin`, `MonitorMixin`, `SettingsMixin`. Displays progress bars, stats panel, theme selector, and about screen.
- **`usage_parser.py`** — stateless parser: ANSI-stripped CLI text → `UsageData` / `UsageSection` / `AccountUsage` dataclasses via regex. The only module that defines these dataclasses.
- **`storage.py`** — account state persistence; upserts `accounts` and `account_sections` tables via `db.get_connection()`.
- **`db.py`** — SQLite connection singleton (WAL mode, shared across threads). Owns schema creation and incremental numbered migrations (`_apply_migrations`). Handles one-time JSON→SQLite migration on first run.
- **`settings.py`** — per-account settings in `~/.ccwinusage/user_settings.json`. Per-account keys stored under `settings[email]`; cross-account (global) keys under `settings["_global"]`.
- **`notifier.py`** — Windows toast via `winotify`. Maintains `_last_notified` in-memory dict; fires when a usage percentage crosses the next threshold step. Creates a Start Menu shortcut with AUMID on module import.
- **`token_history.py`** — scans `~/.claude/projects/**/*.jsonl` for raw assistant token data; stores in `token_entries` table. Uses `jsonl_processed` to track file position for incremental scans.
- **`paths.py`** — all data file paths under `~/.ccwinusage/`. Imported first; creates dirs and handles legacy migration from old exe directory.

## External Dependencies

- **Claude Code CLI** (`claude` on PATH) — sole source of usage data; queried interactively via PTY. Never called via `subprocess`.
- **Windows notification system** — requires a Start Menu shortcut with AppUserModelID (`ClaudeUsageTray`) for toasts to appear. Set up at import time in `notifier.py`.
- **`~/.claude/projects/**/*.jsonl`** — Claude Code local session files; scanned by `token_history.py` for per-message token breakdowns.

## What Does NOT Exist Here

- No web server or remote API — pure local desktop app, all data comes from the local CLI and local files.
- No test suite — there are no test files; manual testing only.
- No asyncio — concurrency is handled via threading + `root.after()` for Tkinter safety.
- No `.env` file or environment variables — all config is in `config.py` constants and `settings.py` JSON.
