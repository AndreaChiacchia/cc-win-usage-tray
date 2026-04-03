---
name: fix-pty-rerender-bleed
description: Fix garbled /usage capture caused by resize-trick re-render output bleeding into the capture buffer. Use when auto-refresh returns duplicate banner/status text instead of usage percentages.
triggers:
  - "garbled output"
  - "duplicate banner"
  - "re-render bleed"
  - "resize trick"
  - "_drain_until_silent"
edges:
  - target: context/pty-runner.md
    condition: always — primary reference for PTY internals and capture flow
  - target: patterns/debug-pty-parsing.md
    condition: when diagnosing the symptom before applying the fix
last_updated: 2026-04-03
---

# Fix: PTY Re-render Bleed into `/usage` Capture

## Root Cause

In `query_usage()` (`src/claude_runner.py`), the resize trick (`setwinsize` twice) forces a full terminal re-render. If fixed `time.sleep()` calls are too short for slow renders, re-render output (banner + status text) still arrives after `/usage\r` is sent. `_capture_usage()` then accumulates this garbage and returns it. `parse_usage()` fails because no usage headers are present.

## The Fix

### 1. `_drain_until_silent()` helper

Replaces fixed `time.sleep()` calls with adaptive draining. Polls the queue until no new data arrives for a `silence` threshold (default 0.3s), capped at `timeout`.

```python
def _drain_until_silent(self, timeout: float = 2.0, silence: float = 0.3):
    deadline = time.monotonic() + timeout
    last_data_at = time.monotonic()
    while time.monotonic() < deadline:
        got_data = False
        while True:
            try:
                chunk = self._data_queue.get_nowait()
                if chunk is None:
                    return
                got_data = True
            except queue.Empty:
                break
        if got_data:
            last_data_at = time.monotonic()
        if (time.monotonic() - last_data_at) >= silence:
            return
        time.sleep(0.02)
```

### 2. Replace sleeps in `query_usage()`

| Step | Old | New |
|------|-----|-----|
| After ESC dismiss of /status | `sleep(0.1)` + `_drain_queue()` | `_drain_until_silent(2.0, 0.3)` |
| After resize trick | `sleep(0.05)` | `_drain_until_silent(2.0, 0.3)` |
| After ESC dismiss of /usage | `sleep(0.1)` + `_drain_queue()` | `_drain_until_silent(1.0, 0.2)` |

### 3. Garbage guard in `_capture_usage()`

Safety net: if the silence-timeout path returns a buffer with no usage headers, return `""` instead. This increments `_consecutive_failures` and triggers auto-respawn after 3 failures rather than silently showing stale/bad data.

```python
if silence > 3.0 and len(clean.strip()) > 10:
    if not _USAGE_HEADER_RE.search(clean):
        return ""  # garbage from re-render, treat as empty
    return buf
```

## Tuning

If bleed still occurs on very slow renders, increase the `silence` parameter in the `_drain_until_silent()` call after the resize trick (currently `0.3`). The `timeout` cap prevents it from blocking indefinitely.
