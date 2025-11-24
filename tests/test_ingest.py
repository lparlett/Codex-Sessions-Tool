"""Tests for session ingestion functionality."""

# pylint: disable=import-error,protected-access

from __future__ import annotations

import json
import logging
import sqlite3
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from pytest import raises

from src.parsers.handlers.db_utils import insert_prompt
from src.services import ingest
from src.services.ingest import (
    ErrorSeverity,
    ProcessingError,
    ProcessingErrorAction,
    SanitizationError,
    SessionIngester,
    _build_prompt_insert,
    _prepare_events,
    _process_events,
    ingest_session_file,
    sanitize_json_for_storage,
)

TC = unittest.TestCase()


@pytest.fixture(name="sample_session_file")
def fixture_sample_session_file(tmp_path: Path) -> Path:
    """Create a temporary copy of the sample session file."""
    source = Path("tests/fixtures/codex_sample_session.jsonl")
    dest = tmp_path / "test_session.jsonl"
    dest.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


@pytest.fixture(name="codex_updates_file")
def fixture_codex_updates_file(tmp_path: Path) -> Path:
    """Create a temporary copy of the Codex updates session file."""
    source = Path("tests/fixtures/codex_file_updates.jsonl")
    dest = tmp_path / "codex_file_updates.jsonl"
    dest.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


def test_sanitize_json_for_storage_validates_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that sanitize_json_for_storage properly validates its input."""
    test_case = unittest.TestCase()

    with test_case.assertRaises(TypeError):
        sanitize_json_for_storage("not a dict")  # type: ignore

    with test_case.assertRaises(SanitizationError):
        # Mock the sanitize_json function to return a non-dict
        def mock_sanitize(_data: dict[str, Any]) -> str:
            return "invalid"

        monkeypatch.setattr(ingest, "sanitize_json", mock_sanitize)
        sanitize_json_for_storage({"test": "data"})


def test_prepare_events_batch_processing(
    sample_session_file: Path, sample_timestamp: datetime
) -> None:
    """Test that _prepare_events correctly processes events in batches."""
    test_case = unittest.TestCase()

    # Create test event data
    test_event = {
        "type": "event_msg",
        "timestamp": sample_timestamp.isoformat(),
        "payload": {"type": "user_message", "message": "Test message"},
    }

    events = [test_event, test_event]  # Two identical events
    errors: list[ProcessingError] = []
    prepared = _prepare_events(events, sample_session_file, errors, batch_size=1)

    test_case.assertEqual(
        len(prepared), len(events), "All valid events should be processed"
    )
    test_case.assertEqual(
        len(errors), 0, "No errors should be reported for valid events"
    )

    # Check structure of prepared events
    for event in prepared:
        test_case.assertIsInstance(event, dict)
        test_case.assertIn("type", event)
        test_case.assertIn("timestamp", event)
        test_case.assertIn("payload", event)


def test_session_ingester_processes_session(
    db_connection: sqlite3.Connection,
    sample_session_file: Path,
) -> None:
    """Test that SessionIngester correctly processes a complete session."""
    test_case = unittest.TestCase()
    ingester = SessionIngester(
        conn=db_connection,
        session_file=sample_session_file,
        batch_size=2,
        verbose=False,
        errors=[],
    )

    summary = ingester.process_session()

    # Validate summary contains expected counts
    test_case.assertIsInstance(summary, dict)
    test_case.assertIn("prompts", summary)
    test_case.assertGreaterEqual(summary["prompts"], 0)

    # Check database has expected records
    cursor = db_connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM sessions")
    session_count = cursor.fetchone()[0]
    test_case.assertGreater(session_count, 0, "Expected at least one session record")

    cursor.execute("SELECT COUNT(*) FROM events")
    event_count = cursor.fetchone()[0]
    test_case.assertGreater(event_count, 0, "Expected at least one event record")
    test_case.assertEqual(
        summary["agent_reasoning_messages"], 1, "Expected one agent reasoning message"
    )
    test_case.assertFalse(summary["errors"], "Expected no errors")

    # Verify data was persisted
    cursor = db_connection.cursor()

    cursor.execute("SELECT COUNT(*) FROM files")
    test_case.assertEqual(cursor.fetchone()[0], 1, "Expected one file record")

    cursor.execute("SELECT COUNT(*) FROM prompts")
    test_case.assertEqual(cursor.fetchone()[0], 1, "Expected one prompt record")

    cursor.execute("SELECT COUNT(*) FROM sessions")
    test_case.assertEqual(cursor.fetchone()[0], 1, "Expected one session record")


def test_session_ingester_handles_function_calls_and_prelude_turn_context(
    db_connection: sqlite3.Connection,
    codex_updates_file: Path,
) -> None:
    """Ensure ingestion processes function calls and preserves prelude events."""
    test_case = unittest.TestCase()
    ingester = SessionIngester(
        conn=db_connection,
        session_file=codex_updates_file,
        batch_size=4,
        verbose=False,
        errors=[],
    )

    summary = ingester.process_session()

    test_case.assertEqual(summary["prompts"], 1, "Expected single prompt")
    test_case.assertEqual(summary["function_calls"], 1, "Expected one function call")
    test_case.assertEqual(summary["agent_reasoning_messages"], 2)
    test_case.assertEqual(summary["token_messages"], 1)
    # turn_context appears in prelude, not grouped counts
    test_case.assertEqual(summary["turn_context_messages"], 0)
    test_case.assertFalse(
        summary["errors"], "Expected no errors for sanitized fixtures"
    )

    session_row = db_connection.execute(
        "SELECT raw_json FROM sessions WHERE file_id = ?",
        (summary["file_id"],),
    ).fetchone()
    test_case.assertIsNotNone(session_row)
    prelude_events = json.loads(session_row[0]).get("events", [])
    test_case.assertTrue(prelude_events)
    test_case.assertTrue(
        any(event.get("type") == "turn_context" for event in prelude_events),
        "Expected turn_context to be preserved in prelude events",
    )

    function_row = db_connection.execute(
        "SELECT call_id, output FROM function_calls ORDER BY id ASC"
    ).fetchone()
    test_case.assertEqual(function_row[0], "call_placeholder")
    test_case.assertEqual(function_row[1], "diff count 1")


def test_ingest_session_file_handles_errors(tmp_path: Path) -> None:
    """Test that ingest_session_file properly handles and reports errors."""
    invalid_file = tmp_path / "invalid.jsonl"
    invalid_file.write_text("invalid json\n{", encoding="utf-8")
    db_path = tmp_path / "test.sqlite"

    with raises(ValueError, match="Failed to parse JSON"):
        ingest_session_file(invalid_file, db_path)


def test_process_events_in_batches_limits_size() -> None:
    """Ensure batches are emitted with the requested size."""
    events = ({"type": "event_msg", "payload": {}} for _ in range(5))
    batches = list(ingest.process_events_in_batches(events, batch_size=2))
    TC.assertEqual([len(batch) for batch in batches], [2, 2, 1])


def test_prepare_events_filters_invalid(sample_session_file: Path) -> None:
    """Invalid events should be recorded as processing errors and skipped."""
    raw_events = [
        {"type": "event_msg", "payload": {}},  # valid
        {"type": "event_msg", "payload": "bad"},  # invalid payload type
    ]
    errors: list[ProcessingError] = []
    prepared = _prepare_events(
        raw_events,  # type: ignore[arg-type]
        sample_session_file,
        errors,
        batch_size=1,
    )
    TC.assertEqual(len(prepared), 1)
    TC.assertTrue(errors)
    TC.assertEqual(errors[0].code, "invalid_event")


def test_ensure_file_row_resets_existing(tmp_path: Path) -> None:
    """_ensure_file_row should reuse file id and clear prior prompt/session rows."""
    conn = ingest.get_connection(tmp_path / "db.sqlite")
    ingest.ensure_schema(conn)
    session_file = tmp_path / "session.jsonl"
    session_file.write_text("{}", encoding="utf-8")

    file_id = ingest._ensure_file_row(  # pylint: disable=protected-access
        conn, session_file
    )
    conn.execute(
        "INSERT INTO prompts (file_id, prompt_index) VALUES (?, ?)",
        (file_id, 1),
    )
    conn.execute(
        "INSERT INTO sessions (file_id) VALUES (?)",
        (file_id,),
    )
    reused_id = ingest._ensure_file_row(  # pylint: disable=protected-access
        conn, session_file
    )
    TC.assertEqual(reused_id, file_id)
    TC.assertEqual(conn.execute("SELECT COUNT(*) FROM prompts").fetchone()[0], 0)
    TC.assertEqual(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0)
    conn.close()


def test_ingest_single_session_rolls_back_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_ingest_single_session should roll back inserts when processing fails."""
    conn = ingest.get_connection(tmp_path / "rollback.sqlite")
    ingest.ensure_schema(conn)
    session_file = tmp_path / "bad.jsonl"
    session_file.write_text('{"type": "event_msg", "payload": {}}', encoding="utf-8")

    def _raise(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(ingest.SessionIngester, "process_session", _raise)
    with pytest.raises(RuntimeError):
        ingest._ingest_single_session(  # pylint: disable=protected-access
            conn,
            session_file,
        )
    TC.assertEqual(conn.execute("SELECT COUNT(*) FROM files").fetchone()[0], 0)
    conn.close()


def test_ingest_sessions_in_directory_handles_limits(
    tmp_path: Path, sample_session_file: Path
) -> None:
    """ingest_sessions_in_directory should respect limit and iterate by date."""
    root = tmp_path / "2025" / "11" / "23"
    root.mkdir(parents=True)
    target = root / "a.jsonl"
    target.write_text(sample_session_file.read_text(encoding="utf-8"), encoding="utf-8")
    db_path = tmp_path / "test.sqlite"
    summaries = list(
        ingest.ingest_sessions_in_directory(
            tmp_path,
            db_path,
            limit=1,
            verbose=False,
            batch_size=2,
        )
    )
    TC.assertEqual(len(summaries), 1)


def test_ingest_sessions_in_directory_raises_on_empty(tmp_path: Path) -> None:
    """ingest_sessions_in_directory should raise when no files are found."""
    db_path = tmp_path / "test.sqlite"
    empty_root = tmp_path / "missing"
    empty_root.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ingest.SessionDiscoveryError):
        list(
            ingest.ingest_sessions_in_directory(
                empty_root,
                db_path,
            )
        )


def test_log_processing_error_and_serialization(
    sample_session_file: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Exercise logging and serialization of ProcessingError."""
    error = ProcessingError(
        severity=ErrorSeverity.ERROR,
        code="invalid_event",
        message="bad",
        recommended_action=ProcessingErrorAction.CONTINUE,
        file_path=sample_session_file,
        line_number=5,
        context={"event": {"payload": "bad"}},
    )
    with caplog.at_level(logging.ERROR):
        ingest._log_processing_error(error)  # pylint: disable=protected-access
    serialized = ingest.serialize_processing_error(error)
    TC.assertIn("invalid_event", caplog.text)
    TC.assertTrue(serialized["file_path"].endswith("test_session.jsonl"))
    TC.assertEqual(serialized["line_number"], 5)
    TC.assertEqual(serialized["context"]["event"]["payload"], "bad")


def test_build_prompt_insert_handles_missing_payload(tmp_path: Path) -> None:
    """_build_prompt_insert should tolerate non-dict payloads."""
    conn = ingest.get_connection(tmp_path / "prompt.sqlite")
    ingest.ensure_schema(conn)
    insert = _build_prompt_insert(  # pylint: disable=protected-access
        conn,
        1,
        1,
        {"timestamp": "t1", "payload": "not a dict"},
    )
    TC.assertEqual(insert.message, "")
    conn.close()


def test_process_events_covers_all_branches(tmp_path: Path) -> None:
    """_process_events should handle non-dict payloads and multiple event types."""
    conn = ingest.get_connection(tmp_path / "branches.sqlite")
    ingest.ensure_schema(conn)
    file_id = conn.execute(
        "INSERT INTO files (path) VALUES (?)", ("file.jsonl",)
    ).lastrowid
    if file_id is None:
        raise RuntimeError("Failed to insert file row")
    prompt_insert = _build_prompt_insert(  # pylint: disable=protected-access
        conn,
        int(file_id),
        1,
        {"timestamp": "t1", "payload": {"message": "Hi"}},
    )
    prompt_id = insert_prompt(prompt_insert)
    events = [
        {"type": "event_msg", "payload": "skip me"},
        {"type": "turn_context", "payload": {"sandbox_policy": {"mode": "r"}}},
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "update_plan",
                "arguments": "{}",
            },
        },
        {
            "type": "response_item",
            "payload": {"type": "function_call_output", "output": "ok"},
        },
    ]
    counts = _process_events(
        conn,
        prompt_id,
        events,  # type: ignore[arg-type]
    )  # pylint: disable=protected-access
    TC.assertEqual(counts["turn_context_messages"], 1)
    TC.assertEqual(counts["function_plan_messages"], 1)
    TC.assertEqual(counts["function_calls"], 1)
    conn.close()


def test_ingest_session_file_success(sample_session_file: Path, tmp_path: Path) -> None:
    """ingest_session_file should return summary on success."""
    db_path = tmp_path / "ok.sqlite"
    summary = ingest_session_file(sample_session_file, db_path, batch_size=2)
    TC.assertGreaterEqual(summary["prompts"], 0)
