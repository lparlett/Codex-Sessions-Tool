# Schema Changes and Configuration Surface

## 2025-11-24 — Configured database/output paths

- Added `[ingest].db_path` and `[outputs].reports_dir` to `user/config.toml` (example updated).
- Config loader now validates that the database parent directory exists and is writable, and that `outputs.reports_dir` exists and is writable.
- `cli.ingest_session` defaults to `[ingest].db_path` when `--database` is not supplied.
- `cli.group_session` writes grouped output to `[outputs].reports_dir/session.txt` by default (overridable via `-o`).
