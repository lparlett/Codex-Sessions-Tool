"""Tests for syncing redaction rules into the database (AI-assisted by Codex GPT-5)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.services.database import ensure_schema, get_connection
from src.services.redaction_rules import (
    RedactionRule,
    RuleOptions,
    load_rules_from_db,
    sync_rules_to_db,
)


def _make_conn(tmp_path: Path) -> sqlite3.Connection:
    conn = get_connection(tmp_path / "sync.sqlite")
    ensure_schema(conn)
    return conn


def _seed_prompt(conn: sqlite3.Connection) -> int:
    file_id = conn.execute(
        "INSERT INTO files (path) VALUES ('/tmp/test.jsonl')"
    ).lastrowid
    assert file_id is not None
    prompt_insert = """
        INSERT INTO prompts (file_id, prompt_index, timestamp, message, raw_json)
        VALUES (?, 1, 't', 'msg', '{}')
    """
    prompt_id = conn.execute(prompt_insert, (int(file_id),)).lastrowid
    assert prompt_id is not None
    return int(prompt_id)


def test_sync_rules_soft_disables_missing_and_redactions(tmp_path: Path) -> None:
    """Rules missing from the file should be disabled and linked redactions inactivated."""

    conn = _make_conn(tmp_path)
    prompt_id = _seed_prompt(conn)
    conn.execute(
        """
        INSERT INTO redaction_rules (id, type, pattern, scope, replacement_text, enabled)
        VALUES ('old', 'regex', 'secret', 'prompt', '<X>', 1)
        """
    )
    conn.execute(
        """
        INSERT INTO redactions (prompt_id, rule_id, scope, replacement_text, active)
        VALUES (?, 'old', 'prompt', '<X>', 1)
        """,
        (prompt_id,),
    )

    new_rule = RedactionRule(
        id="new",
        type="literal",
        pattern="token",
        options=RuleOptions(scope="prompt", replacement="<R>"),
    )
    sync_rules_to_db(conn, [new_rule])

    rules = load_rules_from_db(conn, include_disabled=True)
    rule_states = {rule.id: rule.enabled for rule in rules}
    assert rule_states["new"] is True
    assert rule_states["old"] is False

    redaction_row = conn.execute(
        "SELECT active FROM redactions WHERE rule_id = 'old'"
    ).fetchone()
    assert redaction_row is not None
    assert redaction_row[0] == 0

    conn.close()
