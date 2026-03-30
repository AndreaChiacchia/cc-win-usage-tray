---
name: pty-runner
description: PTY session lifecycle, CLI capture state machine, and non-obvious gotchas in claude_runner.py. Load when working on the data capture pipeline or debugging PTY/parsing failures.
triggers:
  - "PTY"
  - "claude_runner"
  - "ClaudePtySession"
  - "spawn"
  - "banner"
  - "trust dialog"
  - "usage capture"
  - "pywinpty"
edges:
  - target: context/architecture.md
    condition: when understanding where the PTY runner fits in the overall flow
  - target: context/decisions.md
    condition: when questioning why PTY is used instead of subprocess
  - target: context/stack.md
    condition: when checking pywinpty version constraints or library details
  - target: patterns/debug-pty-parsing.md
    condition: when PTY hangs, returns empty output, or parsing fails
last_updated: 2026-03-30
---

# PTY Runner

## Session Lifecycle

`ClaudePtySession` is a **module-level singleton** accessed via `_get_session()`. It spawns the Claude CLI once and reuses the PTY session across all refresh cycles.

**Spawn flow:**
1. `winpty.PtyProcess.spawn(claude_path, dimensions=(PTY_ROWS, PTY_COLS), cwd=tmpdir, env=...)`
2. A background reader thread drains PTY output into a `queue.Queue`
3. `_wait_for_banner()` monitors output until `_BANNER_RE` matches or `_BANNER_FALLBACK_S` (8s) elapses
4. If a trust dialog is detected (`_TRUST_PROMPT_RE`), a `\r` is sent to confirm, then banner wait resumes
5. `_ready = True` after banner; session is now usable

**Query flow (per refresh):**
1. `_ensure_alive()` — re-spawns if PTY process died
2. Drain queue to discard any accumulated output
3. Send `/status\r` → `_capture_status()` — returns when email is seen, silence >0.5s, or 2s elapsed
4. Send `\x1b` to dismiss the status overlay
5. **Resize trick** — `setwinsize(ROWS, COLS-1)` then `setwinsize(ROWS, COLS)` — forces Claude to re-render `/usage` output (without this, output is sometimes empty or clipped)
6. Send `/usage\r` → `_capture_usage()` — returns when `_USAGE_HEADER_RE` matches + 0.4s wait, or silence >3s
7. Send `\x1b` to dismiss usage overlay
8. Return `strip_ansi(status_raw), strip_ansi(usage_raw)`

## Key Constants (config.py)

- `PTY_TIMEOUT_S = 45` — global deadline for all capture operations
- `PTY_COLS = 68`, `PTY_ROWS = 24` — terminal dimensions; match what the CLI expects
- `_BANNER_FALLBACK_S = 8.0` — in `claude_runner.py`; max wait for banner before proceeding anyway

## Non-obvious Gotchas

- **Resize trick is mandatory.** Without the `setwinsize` call before `/usage`, the PTY sometimes delivers empty or partial output because Claude re-renders based on terminal size change events.
- **Trust dialog detection is regex-based on condensed text.** The trust dialog uses cursor-positioning ANSI sequences; when stripped, words run together (e.g., `trustthisfolder`). `_TRUST_PROMPT_RE` matches this condensed form.
- **Account change forces session restart.** If `/status` returns a different email than the previous refresh, `force_restart_session()` is called and `token_history.scan_blocking()` is flushed for the outgoing account before re-querying.
- **`_lock` serializes concurrent calls.** `query_usage()` holds `self._lock` for the full duration — no parallel queries on the same session.
- **Tmpdir CWD.** The PTY is spawned in a `tempfile.mkdtemp()` dir so Claude doesn't ask about trusting the source directory on every spawn. This tmpdir is cleaned up on `_cleanup_proc()`.
- **EOF from queue signals process death.** The reader thread puts `None` into the queue on `EOFError`; capture loops treat `None` as a termination signal.

## Recovery

If the PTY process dies mid-session:
- `_ensure_alive()` detects `not proc.isalive()` → calls `_cleanup_proc()` → calls `_spawn()` again
- The module-level `force_restart_session()` kills and nulls `_session` so the next `_get_session()` call creates a fresh one
