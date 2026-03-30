---
name: data-layer
description: SQLite schema, migration chain, and storage patterns. Load when adding tables, columns, or working with storage.py / db.py / usage_history.py / token_history.py.
triggers:
  - "database"
  - "SQLite"
  - "migration"
  - "schema"
  - "storage"
  - "db.py"
  - "token_history"
  - "usage_history"
edges:
  - target: context/architecture.md
    condition: when understanding how the data layer fits into the overall system
  - target: context/conventions.md
    condition: when writing new DB access code or following the migration pattern
last_updated: 2026-03-30
---

# Data Layer

## Connection Model

`db.get_connection()` returns a single `sqlite3.Connection` shared across all threads. WAL mode + `check_same_thread=False` allows concurrent reads; sqlite3 serializes writes. All modules call `db.get_connection()` — no module opens its own connection.

## Schema (tables in `db.py._SCHEMA`)

| Table | Purpose |
|---|---|
| `accounts` | One row per email; stores `last_updated`, `is_active`, `raw_text`, `error` |
| `account_sections` | Per-account section data (`label`, `percentage`, `reset_info`, `spent_info`). PK: `(email, label)` |
| `usage_snapshots` | Time-series history; one row per `(email, ts, label)` with `pct` and `spent` |
| `token_entries` | Raw token counts from JSONL scans; `(ts, input, output, cache_read, cache_creation, source_file, email)` |
| `jsonl_processed` | Tracks which JSONL files have been scanned; `(path, mtime, file_size, last_offset, email)` for incremental scan |
| `meta` | Key-value store; used for `schema_version` and migration flags |

## Migration Chain

Migrations live in `_apply_migrations(conn)` in `db.py`. Each block is guarded by `version < N`:

| Version | Change |
|---|---|
| 1 | Initial JSON→SQLite migration on first run |
| 2 | `token_entries` + `jsonl_processed` tables |
| 3 | `last_offset` column on `jsonl_processed` for append-only seek |
| 4 | `email` column on `token_entries`; clears existing untagged rows + `jsonl_processed` |
| 5 | `email` column on `jsonl_processed` |
| (flag) | `token_tz_migrated` — one-time clear of UTC-timestamped token_entries |

**Adding a new migration:** increment N, add a block in `_apply_migrations()`, update `_SCHEMA` with `IF NOT EXISTS` for the new column/table. The `try/except` around `ALTER TABLE` is intentional — new DBs created from the updated `_SCHEMA` already have the column.

## Storage Pattern

`storage.py` is the only module that reads/writes `accounts` and `account_sections`. It uses `_upsert_account()` which:
1. Upserts the `accounts` row
2. Deletes all `account_sections` rows for that email
3. Re-inserts current sections

This is a replace-all pattern, not a diff. Sections are always fully replaced per account.

## History Modules

- **`usage_history.py`** — calls `record_snapshot(email, sections)` after each successful parse; inserts into `usage_snapshots`
- **`token_history.py`** — `scan_blocking(email)` runs synchronously (called during refresh); `scan_incremental(email)` is non-blocking. Uses `jsonl_processed` to skip unchanged files and `last_offset` to seek to the last-read position in append-only files.

## Legacy JSON Files

On first run (when `usage.db` doesn't exist), `_migrate_from_json()` reads `accounts_usage.json` and `usage_history.json` from the data dir and bulk-inserts into SQLite. After migration, the JSON files are renamed to `.bak`. These `.bak` files are safe to delete.
