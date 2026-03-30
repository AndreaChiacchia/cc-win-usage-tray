---
name: add-ui-feature
description: Adding a new feature or control to the usage popup. Covers widget placement, theming, animation, and thread-safety requirements.
triggers:
  - "add UI"
  - "new feature popup"
  - "new widget"
  - "new button"
  - "new panel"
  - "popup feature"
edges:
  - target: context/conventions.md
    condition: always — check Verify Checklist before presenting code
  - target: context/architecture.md
    condition: when unsure which mixin or file owns the new feature
  - target: context/impeccable.md
    condition: always — read for design intent, brand personality, design tokens, and animation guidelines before writing any UI code
last_updated: 2026-03-30
---

# Add UI Feature

## Context

> **Design intent:** Before writing any UI code, read `context/impeccable.md`. It defines the brand personality, design tokens, animation guidelines, and aesthetic principles for the app. All UI work must be consistent with it.

`UsagePopup` (ui_popup.py) is composed via four mixins:
- `AnimationsMixin` — progress bar fill/shimmer animations
- `ScrollMixin` — vertical scrolling for multi-account view
- `MonitorMixin` — multi-monitor positioning, always-on-top, drag
- `SettingsMixin` — settings dialogs (per-account toggles, theme selector, peak times, about)

New sub-features belong in a mixin, not in `UsagePopup.__init__` directly. If the feature is a dialog or settings control, add it to `SettingsMixin`. If it's a new animation, add it to `AnimationsMixin`.

Theme colors are accessed via `theme_mod.current()` which returns a theme object with `.bg`, `.fg`, `.bar_green`, `.bar_yellow`, `.bar_red`, `.button_bg`, `.button_fg`, etc. Do not hardcode hex values from `config.py` in UI code — always go through the theme.

## Steps

1. **Decide which mixin owns it** — check the mixin files listed above. If none fits, create a new mixin file and add it to `UsagePopup`'s base class list.
2. **Add the widget** — create it as an attribute in the mixin's `__init__` or in the method that builds the relevant UI section. Use `theme_mod.current()` for colors.
3. **Add any new constants** to `config.py` (dimensions, durations, thresholds).
4. **Add settings persistence** if the feature has a user toggle — follow the `get_X / set_X` pattern in `settings.py` under the appropriate key (`email` or `"_global"`).
5. **Wire callbacks** — if the feature triggers a refresh or other action, set callbacks via `set_X_callback()` methods on `UsagePopup`, not by importing `main.py` from the mixin.
6. **Thread safety** — any callback that updates the UI must be dispatched via `self.root.after(0, ...)` if it can be called from a background thread.

## Gotchas

- **Never import `main.py` from a mixin or `ui_popup.py`** — this creates a circular dependency. Use callbacks registered from `main.py` instead.
- **`root.after()` is required for any UI update from a non-Tkinter thread.** pystray menu callbacks, `run_usage_threaded()` callbacks, and `token_history` threads are all non-Tkinter.
- **Theming:** if you add a new widget color, also update `theme.py` so all themes cover it. Check that the `"Claude Code"` default theme and at least one other theme define the new property.
- **`overrideredirect(True)`** means the popup has no title bar — standard window decorations and keyboard events may not behave as expected. Test focus and escape key behavior explicitly.
- **Multi-account layout:** the popup scrolls vertically for 3+ accounts (`POPUP_MAX_CONTENT_HEIGHT`). Ensure new widgets handle variable account count gracefully.

## Verify

- [ ] Widget colors come from `theme_mod.current()`, not hardcoded hex
- [ ] New constants are in `config.py`
- [ ] New settings follow `get_X / set_X` pattern in `settings.py`
- [ ] UI updates from callbacks use `root.after(0, ...)`
- [ ] No `import main` in any mixin or popup file
- [ ] Feature tested with 1 account and with 2+ accounts (scroll behavior)

## Debug

If the widget doesn't appear: check that the mixin's `__init__` is called (MRO order in `UsagePopup`'s base class list). If colors are wrong after theme change, check that the feature's widget references `theme_mod.current()` at render time, not at `__init__` time.

## Update Scaffold

- [ ] Update `.mex/ROUTER.md` "Current Project State" if a new feature is now working
- [ ] Update `context/architecture.md` Key Components if a new mixin was created
- [ ] If this is a new task type without a pattern, create one in `.mex/patterns/` and add to `INDEX.md`
