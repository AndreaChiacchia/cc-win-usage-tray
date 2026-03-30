# Claude Usage Tray

## What This Is

A Windows system tray application that tracks Claude Code CLI token usage (session, weekly, extra) across one or more accounts and surfaces it via an animated popup, toast notifications, and a historical stats panel.

## Non-Negotiables

- Never hardcode hex color values in UI code — always read colors from `theme_mod.current()`
- Never call Tkinter methods directly from a non-Tkinter thread — always dispatch via `self.root.after(0, ...)`
- Never import `main.py` from a mixin or `ui_popup.py` — use callbacks registered from `main.py`
- Never open a raw `sqlite3.connect()` — all DB access goes through `db.get_connection()`
- Never write persistent data outside `~/.ccwinusage/` — paths are the single source of truth in `paths.py`
- New UI elements must have corresponding theme keys in `theme.py` so custom themes can override them

## Commands

- **Run from source:** `cd src && python main.py`
- **Build exe:** `cd src && pyinstaller ../ClaudeUsageTray.spec` → `dist/ClaudeUsageTray.exe`
- **Debug log (PTY output):** `~/.ccwinusage/logs/usage_output_debug.txt`
- **Notifier log:** `~/.ccwinusage/logs/notifier_debug.log`

## After Every Task

After completing any task: update `.mex/ROUTER.md` project state and any `.mex/` files that are now out of date. If no pattern existed for the task you just completed, create one in `.mex/patterns/`.

## Navigation

At the start of every session, read `.mex/ROUTER.md` before doing anything else.
For full project context, patterns, and task guidance — everything is there.

For UI work, also read `.mex/context/impeccable.md` — it defines design tokens, brand personality, animation guidelines, and aesthetic principles.
