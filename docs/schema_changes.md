# Schema Changes and Configuration Surface

## 2025-11-27 - Added redactions table (v0.6.0 / issue #5)

- Added `redactions` table tracking scope (`prompt`, `field`, `global`), optional prompt linkage, field paths, replacement text, actor, reason, and timestamps.
- Created index `idx_redactions_prompt_scope` to speed filtered lookups.
- Introduced `src/services/redactions.py` CRUD helpers for creating, listing, updating, and deleting redactions.

## 2025-11-24 - Configured database/output paths

- Added `[ingest].db_path` and `[outputs].reports_dir` to `user/config.toml` (example updated).
- Config loader now validates that the database parent directory exists and is writable, and that `outputs.reports_dir` exists and is writable.
- `cli.ingest_session` defaults to `[ingest].db_path` when `--database` is not supplied.
- `cli.group_session` writes grouped output to `[outputs].reports_dir/session.txt` by default (overridable via `-o`).
