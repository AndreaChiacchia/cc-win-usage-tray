---
name: fix-cross-thread-dispatch
description: Pattern for safely dispatching from background/pystray threads to the Tkinter main thread, avoiding Windows PostMessage delivery stalls when windows are withdrawn.
triggers:
  - "cross-thread"
  - "root.after from thread"
  - "auto-refresh stalls"
  - "event loop"
  - "background thread UI update"
---

# Pattern: Cross-Thread Dispatch to Tkinter

## Problem

On Windows, calling `root.after(0, callback)` from a background thread uses `PostMessage` to
an internal Tk HWND. When all Tk windows are withdrawn (root + popup hidden), Windows can
deprioritize or delay delivery of those messages indefinitely. This causes auto-refresh
callbacks to never fire while the popup is hidden.

`_keepalive()` (a Tk timer) does NOT fix this — it keeps Tk's timer queue alive but does not
force Windows to deliver cross-thread `PostMessage`d events.

## Solution

Use a `queue.Queue` polled by a main-thread timer:

1. Background threads put callbacks into `self._ui_queue` via `_dispatch(cb)`.
2. `_poll_ui_queue()` runs on the main thread every 100ms, drains the queue, and re-schedules itself.

`queue.put()` is thread-safe without Tk's cross-thread marshaling. All callbacks still execute
on the main thread — no non-negotiables are violated.

## Implementation

```python
import queue

# In __init__:
self._ui_queue: queue.Queue = queue.Queue()
self._poll_ui_queue()

# Add these methods:
def _dispatch(self, callback):
    """Thread-safe: enqueue a callback for the main thread."""
    self._ui_queue.put(callback)

def _poll_ui_queue(self):
    """Drain all pending callbacks from background threads."""
    while True:
        try:
            cb = self._ui_queue.get_nowait()
            cb()
        except queue.Empty:
            break
    self.root.after(100, self._poll_ui_queue)
```

## What to change / what to leave alone

| Call site | Thread | Action |
|-----------|--------|--------|
| Worker callbacks (`_on_usage_success`, `_on_usage_error`) | Background | Replace `root.after(0/100, ...)` → `_dispatch(...)` |
| pystray menu callbacks (`_show_usage_menu`, `_refresh_menu`, etc.) | pystray | Leave as `root.after(0, ...)` — triggered by user interaction which wakes the loop |
| Main-thread scheduling (`_schedule_auto_refresh`, `_trigger_refresh`) | Main | Leave as `root.after(...)` — already on main thread |

## Gotchas

- Do not use `_dispatch` from the main thread — it adds unnecessary queue overhead.
- Do not replace pystray `root.after(0, ...)` calls — those work fine and are interaction-driven.
- `_poll_ui_queue` reschedules itself unconditionally; it IS the event-loop heartbeat.
