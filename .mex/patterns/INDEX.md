# Pattern Index

Lookup table for all pattern files in this directory. Check here before starting any task — if a pattern exists, follow it.

| Pattern | Use when |
|---------|----------|
| [add-setting.md](add-setting.md) | Adding a new per-account or global user setting (persistence + optional UI toggle) |
| [add-ui-feature.md](add-ui-feature.md) | Adding a new feature, widget, or panel to the usage popup |
| [debug-pty-parsing.md](debug-pty-parsing.md) | Diagnosing empty output, parse errors, PTY hangs, or the app stuck on loading |
| [release.md](release.md) | Building the exe, bumping the version, merging staging→main, and publishing a GitHub release |
| [fix-cross-thread-dispatch.md](fix-cross-thread-dispatch.md) | Background threads dispatching UI callbacks to the main Tkinter thread without Windows PostMessage stalls |
| [fix-pty-rerender-bleed.md](fix-pty-rerender-bleed.md) | Garbled /usage capture: resize-trick re-render output bleeds into capture buffer, returning banner/status instead of usage percentages |
