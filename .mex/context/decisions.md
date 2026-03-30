---
name: decisions
description: Key architectural and technical decisions with reasoning. Load when making design choices or understanding why something is built a certain way.
triggers:
  - "why do we"
  - "why is it"
  - "decision"
  - "alternative"
  - "we chose"
edges:
  - target: context/architecture.md
    condition: when a decision relates to system structure
  - target: context/stack.md
    condition: when a decision relates to technology choice
  - target: context/pty-runner.md
    condition: when a decision relates to the PTY session or CLI capture approach
last_updated: 2026-03-30
---

# Decisions

## Decision Log

### Use PTY (pywinpty) instead of subprocess for Claude CLI

**Date:** ~2024 (inferred from codebase)
**Status:** Active
**Decision:** The Claude CLI is spawned via `winpty.PtyProcess.spawn()`, not `subprocess.Popen`.
**Reasoning:** Claude CLI uses interactive terminal features (ANSI sequences, cursor positioning, prompts). Subprocess pipes capture nothing useful. A PTY emulates a real terminal so the CLI behaves normally and output can be captured.
**Alternatives considered:** `subprocess.Popen` with `stdout=PIPE` (rejected — Claude CLI detects non-TTY and produces no output or garbled output).
**Consequences:** Must handle trust dialog, banner wait, and PTY lifecycle. Adds `pywinpty` as a Windows-only dependency.

---

### Persistent PTY session — spawn once, reuse across refreshes

**Date:** ~2024
**Status:** Active
**Decision:** `ClaudePtySession` is a module-level singleton; the Claude CLI process is spawned once and `/status` + `/usage` commands are re-sent over the same PTY on each refresh.
**Reasoning:** Spawning a new PTY process on every refresh causes a visible console window focus steal (from `CreateProcessW`). Reusing the session avoids this — focus steal happens only at first spawn.
**Alternatives considered:** Spawn + kill on each refresh (rejected — intrusive UX, slow).
**Consequences:** Must detect and recover from dead PTY processes (`_ensure_alive()`). Must force-restart the session when the active Claude account changes.

---

### SQLite instead of JSON for persistence

**Date:** ~2024–2025
**Status:** Active (supersedes JSON approach)
**Decision:** All account state, usage snapshots, and token history are stored in SQLite (`~/.ccwinusage/usage.db`).
**Reasoning:** JSON files are not safe for concurrent writes from multiple threads. SQLite in WAL mode handles concurrent reads and serialised writes without file-lock races. History queries (charting, aggregation) are cleaner in SQL.
**Alternatives considered:** JSON (used originally — now `.bak` files after migration), single JSON file per account (rejected — same concurrency problem).
**Consequences:** `db.py` manages numbered schema migrations. First run migrates legacy JSON files to SQLite and renames them `.bak`.

---

### All data in `~/.ccwinusage/`, not the exe directory

**Date:** ~2024
**Status:** Active
**Decision:** All persistent files (`usage.db`, `user_settings.json`, logs) live under `~/.ccwinusage/`.
**Reasoning:** When the app is launched via the Windows startup registry key, the CWD is `C:\Windows\system32`. Relative file paths would write data there (fails on permission-restricted systems). An absolute home-relative path works regardless of CWD.
**Alternatives considered:** Relative paths next to exe (rejected — CWD is unpredictable), `%APPDATA%` (works but less portable to source-run mode).
**Consequences:** `paths.py` is the single source of truth for all file paths. It also handles a one-time migration of legacy files from the old exe directory location.

---

### Tkinter for the popup UI

**Date:** ~2024
**Status:** Active
**Decision:** The usage popup is built with Tkinter (Python stdlib).
**Reasoning:** Minimal dependencies for a tray utility; no Qt or wx licensing concerns; sufficient for a borderless popup with progress bars and charts.
**Alternatives considered:** PyQt5/6 (rejected — heavy, licensing); wx (rejected — complex install); webview (rejected — overkill).
**Consequences:** UI composition via mixin classes to keep `UsagePopup` manageable. Animation and theming must be implemented manually (no CSS equivalent).
