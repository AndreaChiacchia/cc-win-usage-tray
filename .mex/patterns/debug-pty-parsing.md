---
name: debug-pty-parsing
description: Diagnose failures in the PTY → parse → display pipeline. Use when usage data is empty, wrong, or the app shows an error instead of percentages.
triggers:
  - "debug"
  - "empty output"
  - "parse error"
  - "PTY hang"
  - "usage not updating"
  - "error state"
  - "Could not parse"
  - "timeout"
edges:
  - target: context/pty-runner.md
    condition: always — primary reference for PTY internals and gotchas
  - target: context/architecture.md
    condition: when tracing which component in the pipeline is failing
last_updated: 2026-04-22
---

# Debug: PTY / Parsing Failures

## Context

The capture pipeline has three boundaries where failures occur:

1. **PTY spawn** — Claude CLI not found, trust dialog not dismissed, banner never appears
2. **Capture** — `/status` or `/usage` returns empty, clipped, or garbled text
3. **Parse** — `usage_parser.py` can't extract sections from the captured text

## Steps

### 1. Check the debug log first

`~/.ccwinusage/logs/usage_output_debug.txt` — written on every successful PTY round trip. Contains `repr()` of raw status and usage text including ANSI escapes.

- **Empty file or file not written:** PTY raised an exception before `_on_usage_success()` was reached. Check the console (if running from source) for the exception.
- **`status_text` has no `@` sign:** `parse_email()` will return `None` → triggers `_on_usage_error("Could not identify account...")`. The CLI is returning something unexpected from `/status`.
- **`usage_text` has no `Current session` / `Current week`:** `_USAGE_HEADER_RE` didn't match. The resize trick may not have triggered a re-render, or PTY dimensions are wrong.

### 2. Check for PTY timeout

If the app hangs in "Loading..." state:
- `PTY_TIMEOUT_S = 45` in `config.py` — this is the max wait. If it's hitting this, the CLI is unresponsive.
- Confirm Claude CLI works in a regular terminal: run `claude` manually, type `/usage`, check the output.

### 3. Check banner detection

If PTY spawns but never completes:
- `_BANNER_RE = re.compile(r'Claude Code|╭|Welcome', re.IGNORECASE)` — if the CLI greeting changed, this won't match.
- `_BANNER_FALLBACK_S = 8.0` provides a fallback — after 8s of any output, banner wait ends regardless.
- Check the trust dialog: `_TRUST_PROMPT_RE` looks for `trust.{0,10}folder|trustthisfolder|Entertoconfirm`. If the dialog text changed, the `\r` confirmation won't be sent.

### 4. Check parse regex

If the debug log shows text with usage info but sections aren't displayed, or if the parser returns duplicate sections / polluted reset text:
- `usage_parser.py` now looks for `Current session|Current week(?: \(all models\))?|Extra usage` and keeps the last valid section per label
- `_PERCENTAGE_RE` matches `(\d{1,3})%\s*used`
- `_RESET_PREFIX_RE` matches reset/refresh keywords; handles misspelled `Reses` and glued forms like `Resets1pm`
- `_RESET_VALUE_RE` bounds reset text to known date/time shapes; this prevents trailing non-usage text from leaking when Claude omits the Stats/Extra block
- Claude can clip the leading `Re` from a rerendered weekly reset (`70%usedset Apr 24...`); the parser treats `set`/`sets` as a reset prefix and normalizes it back to `Resets`
- If Claude appends `Stats` copy after the usage blocks, the parser trims it using the same boundary list that excludes `Esc to cancel`, `Refreshing`, `Scanning local sessions`, and `What's contributing to your limits usage?`
- `/status` should still parse the same way as before; this pattern is only about `/usage`
- `_capture_usage()` now waits for `USAGE_CAPTURE_SETTLE_S` of silence after the first usage header, capped by `USAGE_CAPTURE_MAX_AFTER_HEADER_S`, so an early return should no longer drop the trailing `Extra usage` block

Add a temporary `print()` in `parse_usage()` or run it directly against the captured `raw_text` from the DB to see what the parser sees.

### 5. Check the resize trick / re-render bleed

If `/usage` returns garbled content (banner + status text, zero usage headers), the re-render output from the resize trick bled into the `/usage` capture buffer.

- The resize forces a full screen re-render. Fixed `time.sleep()` after resize isn't enough — if the terminal is slow, re-render output arrives after `/usage\r` is sent.
- **Fix in place (v1.13+):** `_drain_until_silent()` replaces all fixed sleeps in `query_usage()`. It polls until 0.3s of silence before sending `/usage\r`, ensuring re-render output is fully consumed first.
- A garbage guard in `_capture_usage()` also rejects buffers with no usage headers (returns `""` → increments `_consecutive_failures` → triggers auto-respawn after 3 failures).
- If bleed still happens: increase the `silence` threshold in the `_drain_until_silent()` call after the resize trick (currently 0.3s).

### 6. Check account change handling

If usage shows the wrong account's data:
- On account change, `force_restart_session()` is called and a fresh `/status` + `/usage` cycle begins.
- Check `_active_email` in `ClaudeUsageTray` — if it's stale, the comparison `prev != email` may not trigger.

## Common Error States

| Symptom | Likely cause |
|---|---|
| "Could not identify account from /status output" | `/status` returned no email-like string |
| "Empty output from Claude Code" | PTY returned nothing from `/usage`; resize trick failed or re-render bleed (see §5) |
| "Could not parse usage data — unexpected format" | No section headers found; CLI output format changed |
| "Could not extract any usage sections" | Headers found but no `X% used` matched, or the capture only contains stats noise |
| Duplicate `Current session` / `Current week` sections | Claude rendered `/usage` twice; parser should now keep the later valid render |
| `reset_info` contains `What's contributing...` | New Claude Stats text leaked past the old section boundary; update the boundary list |
| Current week percentage updates but reset is blank | Latest rerender may contain a clipped prefix like `usedset Apr 24`; update reset-prefix/value parsing |
| `Extra usage` disappears intermittently | `/usage` capture returned before the tail of the render; check `_capture_usage()` settle timing |
| Old account had `Extra usage`, new `/usage` drops it, and the raw text does not say `not enabled` / `unavailable` / `disabled` | The missing-extra guard should reject the refresh once, retry in a fresh PTY, then keep the previous stored account data if the retry still omits Extra |
| App stuck on loading icon | PTY timeout; CLI unresponsive; check debug log |
| `[PTY] Empty output (N/3)` in console | PTY alive but hung; auto-respawn will trigger at N=3 |
| `[PTY] Unresponsive after 3 consecutive failures — forcing respawn` | Auto-respawn fired; next refresh should succeed |

## Update Scaffold

- [ ] If a new failure mode was discovered, add it to the table above
- [ ] If a regex needed updating, document the change in `context/pty-runner.md`
- [ ] Update `.mex/ROUTER.md` "Known Issues" if the issue is ongoing
