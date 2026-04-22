---
name: router
description: Session bootstrap and navigation hub. Read at the start of every session before any task. Contains project state, routing table, and behavioural contract.
edges:
  - target: context/architecture.md
    condition: when working on system design, integrations, or understanding how components connect
  - target: context/stack.md
    condition: when working with specific technologies, libraries, or making tech decisions
  - target: context/conventions.md
    condition: when writing new code, reviewing code, or unsure about project patterns
  - target: context/decisions.md
    condition: when making architectural choices or understanding why something is built a certain way
  - target: context/setup.md
    condition: when setting up the dev environment or running the project for the first time
  - target: context/pty-runner.md
    condition: when working on or debugging the Claude CLI capture pipeline
  - target: context/data-layer.md
    condition: when working on storage, SQLite schema, or history modules
  - target: context/impeccable.md
    condition: when working on any UI — design tokens, brand personality, animation guidelines, and aesthetic principles
  - target: patterns/INDEX.md
    condition: when starting a task — check the pattern index for a matching pattern file
last_updated: 2026-03-30
---

# Session Bootstrap

If you haven't already read `AGENTS.md`, read it now — it contains the project identity, non-negotiables, and commands.

Then read this file fully before doing anything else in this session.

## Current Project State

**Working:**
- System tray icon with right-click menu (show popup, refresh, themes, peak times, about, quit)
- Usage popup with animated progress bars for session, weekly, and extra usage sections
- Multi-account tracking — active account surfaced first, inactive accounts shown below
- Per-account settings: refresh interval, notification thresholds, notifications on/off, relative time, shimmer, pace delta
- Global settings: theme, always-on-top, popup position (multi-monitor aware), peak times window
- Historical stats panel with bar chart, token breakdown, and peak-hour annotation
- Windows toast notifications on threshold crossings (10% steps, configurable)
- PTY-based runner with persistent session (no focus steal on refresh)
- SQLite persistence with incremental JSON→SQLite migration and numbered schema migrations (v5)
- Token detail panel from `~/.claude/projects/**/*.jsonl` incremental scans
- Windows startup registry integration

**Not yet built:**
- Test suite (no automated tests exist)
- Linux/macOS support (Windows-only: pywinpty, winotify, pywin32)

**Known Issues:**
- None tracked currently. Check git log for recent fixes.

**Resilience (event loop):**
- `_poll_ui_queue()` drains a `queue.Queue` every 100ms on the main thread. Background threads post callbacks via `_dispatch(cb)` instead of `root.after(0, ...)`. This avoids the Windows `PostMessage` delivery problem where cross-thread `root.after` messages are silently delayed when all Tk windows are withdrawn, which caused auto-refresh to stall when the popup was hidden.

**Resilience:**
- PTY auto-respawn on hang: after `MAX_CONSECUTIVE_FAILURES` (3) consecutive empty-output refreshes, `_ensure_alive()` force-kills and respawns the PTY. Counter resets on success. Logged via `[PTY]` prefix in debug output.

**Recently completed (latest first):**
- Bug fix: narrow Claude 2.1.117 usage fix back to `/usage` only - kept Stats-aware parser changes, restored `/status` parsing and PTY capture timing
- Bug fix: usage parser now ignores Claude 2.1.117 Stats text and duplicate `/usage` renders, keeping the latest valid section per label
- Bug fix: garbled /usage capture — resize-trick re-render bled into capture buffer; replaced fixed `time.sleep()` calls in `query_usage()` with `_drain_until_silent()`; added garbage guard in `_capture_usage()` to reject buffers with no usage headers
- Bug fix: auto-refresh stalling when popup hidden — replaced cross-thread `root.after(0, ...)` in worker callbacks with `queue.Queue` polled by `_poll_ui_queue()` every 100ms; removed `_keepalive()`
- Feature: double-click tray icon opens usage popup — `default=True` on "Show Usage" `pystray.MenuItem` in `_build_tray_menu`; item also appears bold in the context menu per Windows convention
- Bug fix: peak label in popup bottom bar now refreshes every 60s via `_tick_relative` (was stale if popup stayed open across a boundary)
- Feature: peak/off-peak transition toast notifications — fires once per transition via `check_peak_transition()` in `notifier.py`, called from `_on_usage_success` and once at startup (silent init)
- Feature: "Month" (year) view added to stats panel month section — 12 monthly bars for current year, click to drill into week view; `_selected_month` state tracks navigated month across Day/Week/Month views
- Feature: "Year" (decade) view added to stats panel — 4th toggle button shows 10 yearly bars (last 10 years); clicking a year drills into Month view for that year; `_selected_year` state persists across view switches; `_build_decade_year_slots()` aggregates ~3652 days into yearly slots

## Routing Table

Load the relevant file based on the current task. Always load `context/architecture.md` first if not already in context this session.

| Task type | Load |
|-----------|------|
| Understanding how the system works | `context/architecture.md` |
| Working with a specific technology | `context/stack.md` |
| Writing or reviewing code | `context/conventions.md` |
| Making a design decision | `context/decisions.md` |
| Setting up or running the project | `context/setup.md` |
| PTY session / CLI capture / parsing failures | `context/pty-runner.md` |
| Database schema / storage / migrations | `context/data-layer.md` |
| UI design — tokens, theming, animations, layout | `context/impeccable.md` |
| Any specific task | Check `patterns/INDEX.md` for a matching pattern |

## Behavioural Contract

For every task, follow this loop:

1. **CONTEXT** — Load the relevant context file(s) from the routing table above. Check `patterns/INDEX.md` for a matching pattern. If one exists, follow it. Narrate what you load: "Loading architecture context..."
2. **BUILD** — Do the work. If a pattern exists, follow its Steps. If you are about to deviate from an established pattern, say so before writing any code — state the deviation and why.
3. **VERIFY** — Load `context/conventions.md` and run the Verify Checklist item by item. State each item and whether the output passes. Do not summarise — enumerate explicitly.
4. **DEBUG** — If verification fails or something breaks, check `patterns/INDEX.md` for a debug pattern. Follow it. Fix the issue and re-run VERIFY.
5. **GROW** — After completing the task:
   - If no pattern exists for this task type, create one in `patterns/` using the format in `patterns/README.md`. Add it to `patterns/INDEX.md`. Flag it: "Created `patterns/<name>.md` from this session."
   - If a pattern exists but you deviated from it or discovered a new gotcha, update it with what you learned.
   - If any `context/` file is now out of date because of this work, update it surgically — do not rewrite entire files.
   - Update the "Current Project State" section above if the work was significant.
