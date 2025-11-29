"""CLI export tests to ensure redactions apply by default (AI-assisted by Codex GPT-5)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from pytest import MonkeyPatch

import cli.export_session as export_cli
from src.services.config import DatabaseConfig, OutputPaths, SessionsConfig
from src.services.database import ensure_schema, get_connection


def _fake_config(tmp_path: Path) -> SessionsConfig:
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return SessionsConfig(
        sessions_root=tmp_path / "sessions",
        ingest_batch_size=10,
        database=DatabaseConfig(sqlite_path=tmp_path / "db.sqlite"),
        outputs=OutputPaths(reports_dir=reports_dir),
    )


def _connection_factory(db_path: Path) -> Callable[[DatabaseConfig], Any]:
    def _factory(_config: DatabaseConfig) -> Any:
        conn = get_connection(db_path)
        ensure_schema(conn)
        return conn

    return _factory


def _write_session(tmp_path: Path) -> None:
    session_root = tmp_path / "sessions" / "2025" / "01" / "01"
    session_root.mkdir(parents=True, exist_ok=True)
    events = [
        {
            "type": "event_msg",
            "timestamp": "t0",
            "payload": {"type": "user_message", "message": "secret prompt text"},
        },
        {
            "type": "event_msg",
            "timestamp": "t1",
            "payload": {"type": "agent_reasoning", "text": "shows secret content"},
        },
    ]
    lines = "\n".join(json.dumps(event) for event in events)
    (session_root / "session.jsonl").write_text(lines + "\n", encoding="utf-8")


def _write_rules(tmp_path: Path) -> Path:
    rules_file = tmp_path / "rules.json"
    rules = [
        {
            "id": "mask-secret",
            "type": "literal",
            "pattern": "secret",
            "scope": "global",
            "replacement": "<REDACTED>",
        }
    ]
    rules_file.write_text(json.dumps(rules), encoding="utf-8")
    return rules_file


def test_export_applies_redactions(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Export should apply redactions by default."""

    _write_session(tmp_path)
    rules_file = _write_rules(tmp_path)
    config = _fake_config(tmp_path)
    conn_factory = _connection_factory(config.database.sqlite_path)

    monkeypatch.setattr(export_cli, "load_config", lambda: config)
    monkeypatch.setattr(export_cli, "get_connection_for_config", conn_factory)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--rules-file",
            str(rules_file),
        ],
    )

    export_cli.main()
    export_path = config.outputs.reports_dir / "export.txt"
    contents = export_path.read_text(encoding="utf-8")
    assert "<REDACTED>" in contents
    assert "secret prompt text" not in contents
    assert "secret content" not in contents
