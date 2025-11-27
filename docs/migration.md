<!-- 
 Author: Codex with Lauren Parlett
 Date: 2025-11-24
 AI-assisted: Codex (GPT-5) -->

# Migration: SQLite -> Postgres

This guide documents how to lift data from the default SQLite database into Postgres, plus rollback steps if you need to revert.

## When to use Postgres

- Team access or concurrent ingest/review.
- Larger datasets that push past SQLite locking/performance limits.
- Tighter access controls and easier backups on managed Postgres.

SQLite remains the default for single-user/local workflows.

## Prerequisites

- Postgres 17.7+ reachable from your machine.
- A DSN with credentials (not logged by the tool), e.g.  
  `postgresql://postgres:<password>@localhost:5432/ai_log_trail`
- Install the optional driver: `pip install ".[postgres]"` (or `pip install psycopg2-binary`).

## Migration flow (two steps)

1) **Dry-run (required):** checks connectivity and table counts; does not copy data.

   ```bash
   python -m cli.migrate_sqlite_to_postgres \
     --sqlite reports/session_data.sqlite \
     --postgres-dsn "postgresql://USER:PASS@HOST:PORT/DB"
   ```

   - Source counts should reflect your SQLite data.
   - Target counts should be zero on a fresh database. If non-zero, clear the target first.

2) **Execute (copies data):**

   ```bash
   python -m cli.migrate_sqlite_to_postgres \
     --sqlite reports/session_data.sqlite \
     --postgres-dsn "postgresql://USER:PASS@HOST:PORT/DB" \
     --execute
   ```

   - The command creates the schema, copies all tables, and advances identity sequences.

## Rollback strategy

- Keep your SQLite file as a backup until you trust the Postgres copy.
- If a migration fails mid-way, the target may be partially populated. Clear it and re-run:
  - Drop/recreate the Postgres database **or**
  - Truncate all tables in this order: `events`, `function_calls`, `function_plan_messages`, `agent_reasoning_messages`, `turn_context_messages`, `token_messages`, `prompts`, `sessions`, `files`.
- You can always fall back to SQLite by keeping `backend = "sqlite"` in `user/config.toml`.

## Switch ingestion to Postgres (optional)

In `user/config.toml`:

```toml
[database]
backend = "postgres"
postgres_dsn = "postgresql://USER:PASS@HOST:PORT/DB"
```

Leave `ingest.db_path` untouched for SQLite; it’s ignored when `backend=postgres`.

## Verification checklist

- Row counts match between SQLite and Postgres (`files`, `sessions`, `prompts`, `events`).
- Spot-check a few `raw_json` columns in Postgres (e.g., `sessions.raw_json`, `prompts.raw_json`).
- Run a fresh ingest pointing at Postgres and confirm summaries look correct.
