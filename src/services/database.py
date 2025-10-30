# Purpose: centralize SQLite schema management and connection helpers.
# Author: Codex with Lauren Parlett
# Date: 2025-10-30
# Related tests: TBD (planned)

"""SQLite helpers for codex_sessions_tool."""

from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    ingested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL UNIQUE REFERENCES files(id) ON DELETE CASCADE,
    session_id TEXT,
    session_timestamp TEXT,
    cwd TEXT,
    approval_policy TEXT,
    sandbox_mode TEXT,
    network_access TEXT,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    prompt_index INTEGER NOT NULL,
    timestamp TEXT,
    message TEXT,
    active_file TEXT,
    open_tabs TEXT,
    my_request TEXT,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS token_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id INTEGER NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    timestamp TEXT,
    primary_used_percent REAL,
    primary_window_minutes INTEGER,
    primary_resets TEXT,
    secondary_used_percent REAL,
    secondary_window_minutes INTEGER,
    secondary_resets TEXT,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS turn_context_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id INTEGER NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    timestamp TEXT,
    cwd TEXT,
    approval_policy TEXT,
    sandbox_mode TEXT,
    network_access TEXT,
    writable_roots TEXT,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS agent_reasoning_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id INTEGER NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    timestamp TEXT,
    source TEXT,
    text TEXT,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS function_plan_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id INTEGER NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    timestamp TEXT,
    name TEXT,
    arguments TEXT,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS function_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id INTEGER NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    call_timestamp TEXT,
    output_timestamp TEXT,
    name TEXT,
    call_id TEXT,
    arguments TEXT,
    output TEXT,
    raw_call_json TEXT,
    raw_output_json TEXT
);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Return SQLite connection with foreign keys enabled."""

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Apply base schema if tables do not exist."""

    conn.executescript(SCHEMA)
