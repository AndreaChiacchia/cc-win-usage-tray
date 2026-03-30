---
name: conventions
description: How code is written in this project — naming, structure, patterns, and style. Load when writing new code or reviewing existing code.
triggers:
  - "convention"
  - "pattern"
  - "naming"
  - "style"
  - "how should I"
  - "what's the right way"
edges:
  - target: context/architecture.md
    condition: when a convention depends on understanding the system structure
  - target: context/data-layer.md
    condition: when writing database access code or adding migrations
last_updated: 2026-03-30
---

# Conventions

## Naming

- **Files:** `snake_case.py` — e.g., `claude_runner.py`, `ui_popup.py`, `usage_parser.py`
- **Classes:** `PascalCase` — e.g., `ClaudeUsageTray`, `UsagePopup`, `ClaudePtySession`
- **Constants:** `SCREAMING_SNAKE_CASE` in `config.py` — e.g., `PTY_TIMEOUT_S`, `POPUP_WIDTH`
- **Private methods/functions:** leading underscore — e.g., `_trigger_refresh`, `_capture_status`, `_upsert_account`
- **Settings keys:** per-account settings stored under `settings[email]["key"]`; cross-account (global) settings under `settings["_global"]["key"]`
- **Dataclasses:** `PascalCase` defined in `usage_parser.py` — `UsageData`, `UsageSection`, `AccountUsage`

## Structure

- **All persistent data** lives in `~/.ccwinusage/` — never in the source or exe directory. Paths are the single source of truth in `paths.py`.
- **Cross-thread UI calls** MUST go through `self.root.after(0, lambda: ...)` — pystray and background threads must never call Tkinter directly.
- **Constants go in `config.py`**; per-account runtime settings go in `settings.py`; SQL schema and migrations go in `db.py`.
- **UI composition via mixins** — `UsagePopup` inherits from `AnimationsMixin`, `ScrollMixin`, `MonitorMixin`, `SettingsMixin`. New UI sub-features go in a mixin or the relevant existing mixin, not directly in `ui_popup.py`.
- **`db.get_connection()`** is the only entry point to SQLite — all modules (storage, usage_history, token_history) call it; none open their own connections.

## Patterns

**Thread-safe UI updates** — always dispatch to the Tkinter thread:
```python
# Correct — from a background thread or pystray callback
self.root.after(0, lambda: self.popup.show_usage(accounts))

# Wrong — direct call from a non-Tkinter thread
self.popup.show_usage(accounts)
```

**Settings read/write** — no caching; always reads from disk:
```python
# Correct
def get_some_setting(email: str) -> bool:
    s = load_settings()
    return s.get(email, {}).get("some_key", DEFAULT_VALUE)

def set_some_setting(email: str, val: bool):
    s = load_settings()
    s.setdefault(email, {})["some_key"] = val
    save_settings(s)

# Wrong — caching the settings dict in a module-level variable
```

**Database schema changes** — add a numbered migration block in `_apply_migrations()` in `db.py`:
```python
if version < N:
    try:
        conn.execute("ALTER TABLE foo ADD COLUMN bar TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass  # column already exists on new DBs created from updated _SCHEMA
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', 'N')")
    conn.commit()
```

## Verify Checklist

Before presenting any code:
- [ ] Cross-thread UI calls go through `root.after()`, not direct method calls
- [ ] New constants are in `config.py`, not hardcoded inline
- [ ] New persistent data paths are defined in `paths.py`, not constructed ad hoc
- [ ] New settings follow the `load → modify → save` pattern in `settings.py`
- [ ] New DB columns have a numbered migration block in `db.py._apply_migrations()`
- [ ] New `UsagePopup` sub-features are in a mixin, not directly in `UsagePopup.__init__`
- [ ] No direct `sqlite3.connect()` calls — all DB access via `db.get_connection()`
