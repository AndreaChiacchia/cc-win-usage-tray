---
name: add-setting
description: Adding a new per-account or global user setting — persistence in settings.py and optional UI control in SettingsMixin.
triggers:
  - "add setting"
  - "new setting"
  - "user preference"
  - "per-account"
  - "global setting"
  - "settings.py"
edges:
  - target: context/conventions.md
    condition: always — settings pattern and Verify Checklist
  - target: patterns/add-ui-feature.md
    condition: when the setting needs a UI toggle or dialog control
last_updated: 2026-03-30
---

# Add Setting

## Context

Settings are persisted as JSON in `~/.ccwinusage/user_settings.json` via `settings.py`. The file structure is:
```json
{
  "user@example.com": {
    "refresh_interval_minutes": 5,
    "notification_thresholds": { "Current session": 10 },
    "notifications_enabled": true,
    ...
  },
  "_global": {
    "theme": "Claude Code",
    "always_on_top": true,
    "popup_position": [100, 200],
    ...
  }
}
```

**Per-account settings** → stored under `settings[email]`. Use when the setting should differ per Claude account.
**Global settings** → stored under `settings["_global"]`. Use when the setting applies regardless of which account is active (theme, window position, always-on-top).

## Steps

1. **Add `get_X()` and `set_X()` functions** to `settings.py` following the existing pattern:
```python
def get_some_feature_enabled(email: str) -> bool:
    s = load_settings()
    return s.get(email, {}).get("some_feature_enabled", True)  # True = default

def set_some_feature_enabled(email: str, val: bool):
    s = load_settings()
    s.setdefault(email, {})["some_feature_enabled"] = val
    save_settings(s)
```

2. **Add a default constant** in `config.py` if the default value is non-trivial.

3. **Wire the setting** wherever it is consumed (e.g., in `ui_popup.py`, `notifier.py`, `claude_runner.py`).

4. **Add a UI control** if the user should toggle it — in `SettingsMixin` (ui_settings.py), following the pattern of existing toggles (checkbuttons, spinboxes). Call `settings_mod.set_X()` in the control's command callback.

## Gotchas

- **`load_settings()` reads from disk every call** — no in-memory caching. This is intentional. Don't add a cache.
- **`_global` key is for cross-account settings only.** Don't add per-account data under `_global`.
- **Default values are defined in the getter, not in the JSON file.** A missing key means "use the default" — don't pre-populate the file with defaults.
- **Avoid storing large or binary data** in settings JSON — it's a small human-readable config file.

## Verify

- [ ] `get_X` and `set_X` follow the `load → modify → save` pattern
- [ ] Default value is defined in the `get_X` function (`s.get(..., DEFAULT)`)
- [ ] Per-account settings use `s.get(email, {})`, global settings use `s.get("_global", {})`
- [ ] `setdefault` is used in `set_X` to safely create the email/global key if absent

## Update Scaffold

- [ ] Update `.mex/ROUTER.md` "Current Project State" if significant
- [ ] Update `context/conventions.md` if the setting introduces a new pattern
- [ ] If this is a new task type without a pattern, create one in `.mex/patterns/` and add to `INDEX.md`
