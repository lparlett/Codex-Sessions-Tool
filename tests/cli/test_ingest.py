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
from src.parsers.session_parser import SessionDiscoveryError
from src.services import ingest
from src.services.database import get_connection, ensure_schema
from src.services.ingest import (
    ErrorSeverity,
    ProcessingError,
    ProcessingErrorAction,
    SanitizationError,
    SessionIngester,
    _apply_rule_applications_for_event,
    _apply_rule_applications_for_prompt,
    _apply_rule_applications_for_text,
    _apply_rule_applications_pre_prompt,
    _build_prompt_insert,
    _create_empty_summary,
    _ensure_file_row,
    _load_rules_safely,
    _log_processing_error,
    _prepare_events,
    _process_events,
    ingest_session_file,
    ingest_sessions_in_directory,
    process_events_in_batches,
    sanitize_json_for_storage,
    serialize_processing_error,
)
from src.services.redaction_rules import RedactionRule

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

    def _raise(*_args: Any, **_kwargs: Any) -> None:  # pylint: disable=unused-argument
        raise RuntimeError("boom")

    monkeypatch.setattr(ingest.SessionIngester, "process_session", _raise)
    with pytest.raises(RuntimeError):
        ingest._ingest_single_session(  # pylint: disable=protected-access
            conn,
            session_file,
        )
    TC.assertEqual(conn.execute("SELECT COUNT(*) FROM files").fetchone()[0], 0)
    conn.close()


def test_ingest_session_file_rollback_on_db_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ingest_session_file should rollback and re-raise on DB errors."""

    session_file = tmp_path / "sess.jsonl"
    session_file.write_text('{"type": "event_msg", "payload": {}}', encoding="utf-8")
    db_path = tmp_path / "db.sqlite"

    class _BrokenConn(sqlite3.Connection):  # pylint: disable=too-few-public-methods
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.executed = False

        def execute(self, *args: Any, **kwargs: Any) -> Any:
            """Simulate a failing execute call for rollback testing."""
            _ = args
            _ = kwargs
            self.executed = True
            raise sqlite3.DatabaseError("boom")

    def _broken_get_connection(path: Path) -> sqlite3.Connection:
        return _BrokenConn(path)

    monkeypatch.setattr(ingest, "get_connection", _broken_get_connection)
    with pytest.raises(sqlite3.DatabaseError):
        ingest_session_file(session_file, db_path)


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


def test_ingest_sessions_in_directory_returns_iterator(tmp_path: Path) -> None:
    """ingest_sessions_in_directory should return iterator even before iteration."""

    root = tmp_path / "2025" / "11" / "23"
    root.mkdir(parents=True)
    (root / "a.jsonl").write_text("{}", encoding="utf-8")
    db_path = tmp_path / "db.sqlite"
    iterator = ingest.ingest_sessions_in_directory(root, db_path, limit=None)
    TC.assertTrue(hasattr(iterator, "__iter__"))


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


def test_ingest_sessions_in_directory_propagates_non_discovery_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unexpected errors inside ingest_sessions_in_directory should propagate."""

    def _boom(_root: Path) -> list[Path]:  # pylint: disable=unused-argument
        raise RuntimeError("explode")

    monkeypatch.setattr(ingest, "iter_session_files", _boom)
    with pytest.raises(RuntimeError):
        list(
            ingest.ingest_sessions_in_directory(
                tmp_path,
                tmp_path / "db.sqlite",
            )
        )


def test_ingest_single_session_propagates_unexpected_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_ingest_single_session should re-raise unexpected exceptions."""

    conn = ingest.get_connection(tmp_path / "err.sqlite")
    ingest.ensure_schema(conn)
    session_file = tmp_path / "session.jsonl"
    session_file.write_text("{}", encoding="utf-8")

    def _boom(*_args: Any, **_kwargs: Any) -> None:  # pylint: disable=unused-argument
        raise RuntimeError("explode")

    monkeypatch.setattr(ingest, "load_session_events", _boom)
    with pytest.raises(RuntimeError):
        ingest._ingest_single_session(  # pylint: disable=protected-access
            conn,
            session_file,
        )
    conn.close()


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
        int(file_id),
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


# ============================================================================
# ErrorSeverity and Error Logging Tests
# ============================================================================


class TestErrorSeverityBranches:
    """Test all ErrorSeverity logging branches in _log_processing_error."""

    def test_log_processing_error_warning_severity(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test WARNING severity branch in _log_processing_error."""
        error = ProcessingError(
            severity=ErrorSeverity.WARNING,
            code="test_warning",
            message="This is a warning",
            recommended_action=ProcessingErrorAction.CONTINUE,
            file_path=Path("test.jsonl"),
            line_number=10,
            context=None,
        )
        with caplog.at_level(logging.WARNING):
            _log_processing_error(error)
        TC.assertIn("test_warning", caplog.text)
        TC.assertIn("This is a warning", caplog.text)

    def test_log_processing_error_error_severity(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test ERROR severity branch in _log_processing_error."""
        error = ProcessingError(
            severity=ErrorSeverity.ERROR,
            code="test_error",
            message="This is an error",
            recommended_action=ProcessingErrorAction.RETRY,
            file_path=Path("test.jsonl"),
            line_number=20,
            context=None,
        )
        with caplog.at_level(logging.ERROR):
            _log_processing_error(error)
        TC.assertIn("test_error", caplog.text)
        TC.assertIn("This is an error", caplog.text)

    def test_log_processing_error_critical_severity(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test CRITICAL severity branch in _log_processing_error."""
        error = ProcessingError(
            severity=ErrorSeverity.CRITICAL,
            code="test_critical",
            message="This is critical",
            recommended_action=ProcessingErrorAction.ABORT,
            file_path=Path("critical.jsonl"),
            line_number=999,
            context=None,
        )
        with caplog.at_level(logging.CRITICAL):
            _log_processing_error(error)
        TC.assertIn("test_critical", caplog.text)
        TC.assertIn("This is critical", caplog.text)

    def test_log_processing_error_with_no_file_path(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test error logging when file_path is None."""
        error = ProcessingError(
            severity=ErrorSeverity.WARNING,
            code="no_file",
            message="No file path",
            recommended_action=ProcessingErrorAction.CONTINUE,
            file_path=None,
            line_number=None,
            context=None,
        )
        with caplog.at_level(logging.WARNING):
            _log_processing_error(error)
        TC.assertIn("no_file", caplog.text)
        TC.assertIn("No file path", caplog.text)

    def test_log_processing_error_with_file_but_no_line(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test error logging when file_path exists but line_number is None."""
        error = ProcessingError(
            severity=ErrorSeverity.ERROR,
            code="no_line",
            message="File but no line",
            recommended_action=ProcessingErrorAction.RETRY,
            file_path=Path("test.jsonl"),
            line_number=None,
            context=None,
        )
        with caplog.at_level(logging.ERROR):
            _log_processing_error(error)
        TC.assertIn("no_line", caplog.text)
        TC.assertIn("test.jsonl", caplog.text)
        TC.assertNotIn(":None", caplog.text)

    def test_log_processing_error_with_context(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test error logging when context data is present."""
        error = ProcessingError(
            severity=ErrorSeverity.WARNING,
            code="with_context",
            message="Has context",
            recommended_action=ProcessingErrorAction.CONTINUE,
            file_path=Path("test.jsonl"),
            line_number=5,
            context={"key": "value", "nested": {"data": "here"}},
        )
        with caplog.at_level(logging.WARNING):
            _log_processing_error(error)
        TC.assertIn("with_context", caplog.text)
        TC.assertIn("context=", caplog.text)


class TestErrorSerializationBranches:
    """Test optional field handling in serialize_processing_error."""

    def test_serialize_error_with_all_fields(self, tmp_path: Path) -> None:
        """Serialize error with all fields populated."""
        error = ProcessingError(
            severity=ErrorSeverity.ERROR,
            code="full_error",
            message="Full error message",
            recommended_action=ProcessingErrorAction.RETRY,
            file_path=tmp_path / "test.jsonl",
            line_number=42,
            context={"data": "test_value"},
        )
        serialized = serialize_processing_error(error)
        TC.assertEqual(serialized["severity"], "ERROR")
        TC.assertEqual(serialized["code"], "full_error")
        TC.assertEqual(serialized["message"], "Full error message")
        TC.assertEqual(serialized["recommended_action"], "RETRY")
        TC.assertTrue(serialized["file_path"].endswith("test.jsonl"))
        TC.assertEqual(serialized["line_number"], 42)
        TC.assertIsNotNone(serialized["context"])

    def test_serialize_error_with_no_file_path(self) -> None:
        """Serialize error when file_path is None."""
        error = ProcessingError(
            severity=ErrorSeverity.WARNING,
            code="no_file",
            message="No file",
            recommended_action=ProcessingErrorAction.CONTINUE,
            file_path=None,
            line_number=None,
            context=None,
        )
        serialized = serialize_processing_error(error)
        TC.assertIsNone(serialized["file_path"])
        TC.assertIsNone(serialized["line_number"])
        TC.assertIsNone(serialized["context"])

    def test_serialize_error_with_no_context(self, tmp_path: Path) -> None:
        """Serialize error when context is None."""
        error = ProcessingError(
            severity=ErrorSeverity.CRITICAL,
            code="no_context",
            message="Context-less",
            recommended_action=ProcessingErrorAction.ABORT,
            file_path=tmp_path / "test.jsonl",
            line_number=10,
            context=None,
        )
        serialized = serialize_processing_error(error)
        TC.assertIsNone(serialized["context"])
        TC.assertEqual(serialized["code"], "no_context")


# ============================================================================
# Rule Loading Tests
# ============================================================================


class TestRuleLoadingBranches:
    """Test error handling in _load_rules_safely."""

    def test_load_rules_safely_missing_file_verbose_false(self, tmp_path: Path) -> None:
        """Test _load_rules_safely when rules file is missing and verbose=False."""
        nonexistent = tmp_path / "nonexistent_rules.yml"
        result = _load_rules_safely(nonexistent, verbose=False)
        TC.assertIsNone(result)

    def test_load_rules_safely_missing_file_verbose_true(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test _load_rules_safely when rules file is missing and verbose=True."""
        nonexistent = tmp_path / "nonexistent_rules.yml"
        with caplog.at_level(logging.WARNING):
            result = _load_rules_safely(nonexistent, verbose=True)
        TC.assertIsNone(result)
        TC.assertIn("Failed to load rules", caplog.text)
        TC.assertIn("continuing ingest without rule logging", caplog.text)

    def test_load_rules_safely_invalid_yaml_verbose_true(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test _load_rules_safely with invalid YAML and verbose=True."""
        invalid_rules = tmp_path / "invalid_rules.yml"
        invalid_rules.write_text("{ invalid yaml content: [", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = _load_rules_safely(invalid_rules, verbose=True)
        TC.assertIsNone(result)
        TC.assertIn("Failed to load rules", caplog.text)


# ============================================================================
# Event Payload Type Tests
# ============================================================================


class TestEventPayloadTypeBranches:
    """Test payload type checking branches in event processing."""

    def test_prepare_events_with_non_dict_payload(self, tmp_path: Path) -> None:
        """Test _prepare_events skips events with non-dict payloads."""
        raw_events: list[dict[str, Any]] = [
            {"type": "event_msg", "payload": None},
            {"type": "event_msg", "payload": "string"},
            {"type": "event_msg", "payload": 123},
            {"type": "event_msg", "payload": []},
            {
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "valid"},
            },
        ]
        test_file = tmp_path / "test.jsonl"
        test_file.write_text("", encoding="utf-8")
        errors: list[ProcessingError] = []

        prepared = _prepare_events(raw_events, test_file, errors, batch_size=10)

        TC.assertGreater(len(errors), 0)
        TC.assertGreaterEqual(len(prepared), 1)

    def test_build_prompt_insert_with_non_dict_payload(self, tmp_path: Path) -> None:
        """Test _build_prompt_insert handles non-dict payloads gracefully."""
        conn = get_connection(tmp_path / "test.sqlite")
        ensure_schema(conn)

        # Insert a file
        cursor = conn.execute("INSERT INTO files (path) VALUES (?)", ("test.jsonl",))
        file_id = int(cursor.lastrowid or 0)

        # Test with None payload
        prompt_event_none = {
            "type": "user_message",
            "timestamp": "2025-01-01T00:00:00Z",
            "payload": None,
        }
        result = _build_prompt_insert(conn, file_id, 1, prompt_event_none)
        TC.assertEqual(result.message, "")

        # Test with string payload
        prompt_event_str = {
            "type": "user_message",
            "timestamp": "2025-01-01T00:00:00Z",
            "payload": "not a dict",
        }
        result = _build_prompt_insert(conn, file_id, 2, prompt_event_str)
        TC.assertEqual(result.message, "")

        # Test with dict but missing message
        prompt_event_no_msg = {
            "type": "user_message",
            "timestamp": "2025-01-01T00:00:00Z",
            "payload": {"other_field": "value"},
        }
        result = _build_prompt_insert(conn, file_id, 3, prompt_event_no_msg)
        TC.assertEqual(result.message, "")

        # Test with None message value
        prompt_event_none_msg = {
            "type": "user_message",
            "timestamp": "2025-01-01T00:00:00Z",
            "payload": {"message": None},
        }
        result = _build_prompt_insert(conn, file_id, 4, prompt_event_none_msg)
        TC.assertEqual(result.message, "")

        conn.close()


# ============================================================================
# Event Processing Tests
# ============================================================================


class TestEventProcessingBranches:
    """Test conditional branches in event type handling."""

    def test_process_events_with_unknown_event_type(self, tmp_path: Path) -> None:
        """Test _process_events ignores unknown event types."""
        conn = get_connection(tmp_path / "test.sqlite")
        ensure_schema(conn)

        # Set up file and prompt
        cursor = conn.execute("INSERT INTO files (path) VALUES (?)", ("test.jsonl",))
        file_id = int(cursor.lastrowid or 0)
        cursor = conn.execute(
            "INSERT INTO sessions (file_id, session_id, session_timestamp) "
            "VALUES (?, ?, ?)",
            (file_id, "sess1", "2025-01-01T00:00:00Z"),
        )
        cursor = conn.execute(
            "INSERT INTO prompts (file_id, prompt_index, timestamp, message) "
            "VALUES (?, ?, ?, ?)",
            (file_id, 1, "2025-01-01T00:00:00Z", "Test"),
        )
        prompt_id = int(cursor.lastrowid or 0)

        # Unknown event type should be silently ignored
        events = [
            {
                "type": "unknown_event_type",
                "payload": {"data": "test"},
                "timestamp": "2025-01-01T00:00:00Z",
            },
        ]

        counts = _process_events(conn, file_id, prompt_id, events)

        TC.assertEqual(counts["token_messages"], 0)
        TC.assertEqual(counts["turn_context_messages"], 0)
        TC.assertEqual(counts["function_calls"], 0)

        conn.close()

    def test_process_events_skips_non_dict_payloads(self, tmp_path: Path) -> None:
        """Test _process_events skips events with non-dict payloads."""
        conn = get_connection(tmp_path / "test.sqlite")
        ensure_schema(conn)

        # Set up file and prompt
        cursor = conn.execute("INSERT INTO files (path) VALUES (?)", ("test.jsonl",))
        file_id = int(cursor.lastrowid or 0)
        cursor = conn.execute(
            "INSERT INTO sessions (file_id, session_id, session_timestamp) "
            "VALUES (?, ?, ?)",
            (file_id, "sess1", "2025-01-01T00:00:00Z"),
        )
        cursor = conn.execute(
            "INSERT INTO prompts (file_id, prompt_index, timestamp, message) "
            "VALUES (?, ?, ?, ?)",
            (file_id, 1, "2025-01-01T00:00:00Z", "Test"),
        )
        prompt_id = int(cursor.lastrowid or 0)

        # Event with non-dict payload should be skipped
        events: list[dict[str, Any]] = [
            {"type": "event_msg", "payload": None},
            {"type": "event_msg", "payload": "string"},
            {"type": "turn_context", "payload": []},
        ]

        counts = _process_events(conn, file_id, prompt_id, events)

        TC.assertEqual(sum(counts.values()), 0)

        conn.close()


# ============================================================================
# Batch Processing Tests
# ============================================================================


class TestProcessEventsInBatches:
    """Test batch processing of events."""

    def test_process_events_in_batches_exact_batch_size(self) -> None:
        """Batches should be emitted at exact batch_size boundary."""
        from src.services.ingest import process_events_in_batches

        events = [{"id": i} for i in range(10)]
        batches = list(process_events_in_batches(iter(events), batch_size=5))

        TC.assertEqual(len(batches), 2)
        TC.assertEqual(len(batches[0]), 5)
        TC.assertEqual(len(batches[1]), 5)

    def test_process_events_in_batches_partial_final_batch(self) -> None:
        """Final batch can be smaller than batch_size."""
        from src.services.ingest import process_events_in_batches

        events = [{"id": i} for i in range(7)]
        batches = list(process_events_in_batches(iter(events), batch_size=5))

        TC.assertEqual(len(batches), 2)
        TC.assertEqual(len(batches[0]), 5)
        TC.assertEqual(len(batches[1]), 2)

    def test_process_events_in_batches_empty_iterator(self) -> None:
        """Empty iterator should yield no batches."""
        from src.services.ingest import process_events_in_batches

        events: list[dict[str, Any]] = []
        batches = list(process_events_in_batches(iter(events), batch_size=5))

        TC.assertEqual(len(batches), 0)

    def test_process_events_in_batches_single_item(self) -> None:
        """Single item should be in one batch."""
        from src.services.ingest import process_events_in_batches

        events = [{"id": 1}]
        batches = list(process_events_in_batches(iter(events), batch_size=5))

        TC.assertEqual(len(batches), 1)
        TC.assertEqual(len(batches[0]), 1)

    def test_process_events_in_batches_batch_size_one(self) -> None:
        """Batch size of 1 should yield individual batches."""
        from src.services.ingest import process_events_in_batches

        events = [{"id": i} for i in range(3)]
        batches = list(process_events_in_batches(iter(events), batch_size=1))

        TC.assertEqual(len(batches), 3)
        TC.assertTrue(all(len(batch) == 1 for batch in batches))


# ============================================================================
# File Row Management Tests
# ============================================================================


class TestEnsureFileRow:
    """Test file row creation and update logic."""

    def test_ensure_file_row_creates_new_file(self, tmp_path: Path) -> None:
        """_ensure_file_row should create a new file row if not exists."""
        from src.services.ingest import _ensure_file_row

        conn = get_connection(tmp_path / "test.sqlite")
        ensure_schema(conn)

        file_path = Path("new_session.jsonl")
        file_id = _ensure_file_row(conn, file_path)

        TC.assertIsNotNone(file_id)
        TC.assertGreater(file_id, 0)

        # Verify file was inserted
        cursor = conn.execute(
            "SELECT path FROM files WHERE id = ?",
            (file_id,),
        )
        result = cursor.fetchone()
        TC.assertIsNotNone(result)
        TC.assertEqual(result[0], str(file_path))
        conn.close()

    def test_ensure_file_row_returns_existing_file_id(self, tmp_path: Path) -> None:
        """_ensure_file_row should return existing file_id if file exists."""
        from src.services.ingest import _ensure_file_row

        conn = get_connection(tmp_path / "test.sqlite")
        ensure_schema(conn)

        file_path = Path("existing_session.jsonl")
        file_id_1 = _ensure_file_row(conn, file_path)
        file_id_2 = _ensure_file_row(conn, file_path)

        TC.assertEqual(file_id_1, file_id_2)

        # Should only have one file row
        cursor = conn.execute(
            "SELECT COUNT(*) FROM files WHERE path = ?",
            (str(file_path),),
        )
        count = cursor.fetchone()[0]
        TC.assertEqual(count, 1)
        conn.close()

    def test_ensure_file_row_clears_prompts_and_sessions(self, tmp_path: Path) -> None:
        """_ensure_file_row should delete existing prompts and sessions."""
        from src.services.ingest import _ensure_file_row

        conn = get_connection(tmp_path / "test.sqlite")
        ensure_schema(conn)

        file_path = Path("session_to_reset.jsonl")
        file_id = _ensure_file_row(conn, file_path)

        # Insert some prompt and session data
        conn.execute(
            "INSERT INTO prompts (file_id, prompt_index, timestamp, message) "
            "VALUES (?, ?, ?, ?)",
            (file_id, 1, "2025-01-01T00:00:00Z", "Test message"),
        )
        conn.execute(
            "INSERT INTO sessions (file_id, session_id, session_timestamp) "
            "VALUES (?, ?, ?)",
            (file_id, "test_session", "2025-01-01T00:00:00Z"),
        )
        conn.commit()

        # Verify data was inserted
        TC.assertEqual(conn.execute("SELECT COUNT(*) FROM prompts").fetchone()[0], 1)
        TC.assertEqual(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 1)

        # Call _ensure_file_row again
        file_id_2 = _ensure_file_row(conn, file_path)

        # Data should be cleared
        TC.assertEqual(file_id, file_id_2)
        TC.assertEqual(
            conn.execute(
                "SELECT COUNT(*) FROM prompts WHERE file_id = ?", (file_id,)
            ).fetchone()[0],
            0,
        )
        TC.assertEqual(
            conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE file_id = ?", (file_id,)
            ).fetchone()[0],
            0,
        )
        conn.close()


# ============================================================================
# Summary Creation and Update Tests
# ============================================================================


class TestCreateAndUpdateSummary:
    """Test summary creation and count updates."""

    def test_create_empty_summary(self, tmp_path: Path) -> None:
        """_create_empty_summary should initialize all fields."""
        session_file = tmp_path / "test.jsonl"
        file_id = 42

        summary = _create_empty_summary(session_file, file_id)

        TC.assertEqual(summary["session_file"], str(session_file))
        TC.assertEqual(summary["file_id"], file_id)
        TC.assertEqual(summary["prompts"], 0)
        TC.assertEqual(summary["token_messages"], 0)
        TC.assertEqual(summary["turn_context_messages"], 0)
        TC.assertEqual(summary["agent_reasoning_messages"], 0)
        TC.assertEqual(summary["function_plan_messages"], 0)
        TC.assertEqual(summary["function_calls"], 0)
        TC.assertEqual(summary["errors"], [])

    def test_update_summary_counts_increments_prompts(self, tmp_path: Path) -> None:
        """_update_summary_counts should increment prompts by 1."""
        from src.services.ingest import _update_summary_counts

        session_file = tmp_path / "test.jsonl"
        summary = _create_empty_summary(session_file, 1)
        counts: dict[str, int] = {
            "token_messages": 2,
            "turn_context_messages": 1,
            "agent_reasoning_messages": 0,
            "function_plan_messages": 0,
            "function_calls": 1,
        }

        _update_summary_counts(summary, counts)

        TC.assertEqual(summary["prompts"], 1)
        TC.assertEqual(summary["token_messages"], 2)
        TC.assertEqual(summary["turn_context_messages"], 1)
        TC.assertEqual(summary["function_calls"], 1)

    def test_update_summary_counts_multiple_calls(self, tmp_path: Path) -> None:
        """_update_summary_counts should accumulate across multiple calls."""
        from src.services.ingest import _update_summary_counts

        session_file = tmp_path / "test.jsonl"
        summary = _create_empty_summary(session_file, 1)

        counts1 = {
            "token_messages": 1,
            "turn_context_messages": 0,
            "agent_reasoning_messages": 0,
            "function_plan_messages": 0,
            "function_calls": 0,
        }
        counts2 = {
            "token_messages": 2,
            "turn_context_messages": 1,
            "agent_reasoning_messages": 1,
            "function_plan_messages": 0,
            "function_calls": 2,
        }

        _update_summary_counts(summary, counts1)
        _update_summary_counts(summary, counts2)

        TC.assertEqual(summary["prompts"], 2)
        TC.assertEqual(summary["token_messages"], 3)
        TC.assertEqual(summary["turn_context_messages"], 1)
        TC.assertEqual(summary["agent_reasoning_messages"], 1)
        TC.assertEqual(summary["function_calls"], 2)

    def test_update_summary_handles_missing_count_keys(self, tmp_path: Path) -> None:
        """_update_summary_counts should handle missing keys gracefully."""
        from src.services.ingest import _update_summary_counts

        session_file = tmp_path / "test.jsonl"
        summary = _create_empty_summary(session_file, 1)
        counts: dict[str, int] = {}  # Empty counts dict

        _update_summary_counts(summary, counts)

        TC.assertEqual(summary["prompts"], 1)
        TC.assertEqual(summary["token_messages"], 0)
        TC.assertEqual(summary["turn_context_messages"], 0)


# ============================================================================
# SessionIngester Verbose Mode Tests
# ============================================================================


class TestSessionIngesterVerboseMode:
    """Test SessionIngester verbose logging behavior."""

    def test_session_ingester_verbose_mode_logs_ingestion(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """SessionIngester with verbose=True should log ingestion start."""
        conn = get_connection(tmp_path / "test.sqlite")
        ensure_schema(conn)

        session_file = tmp_path / "session.jsonl"
        session_file.write_text(
            json.dumps({"type": "event_msg", "payload": {}}) + "\n",
            encoding="utf-8",
        )

        with caplog.at_level(logging.INFO):
            _ = SessionIngester(
                conn=conn,
                session_file=session_file,
                batch_size=10,
                verbose=True,
                errors=[],
                rules=None,
            )

        TC.assertIn("Ingesting", caplog.text)
        TC.assertIn(str(session_file), caplog.text)
        conn.close()

    def test_session_ingester_non_verbose_mode_no_log(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """SessionIngester with verbose=False should not log ingestion."""
        conn = get_connection(tmp_path / "test.sqlite")
        ensure_schema(conn)

        session_file = tmp_path / "session.jsonl"
        session_file.write_text(
            json.dumps({"type": "event_msg", "payload": {}}) + "\n",
            encoding="utf-8",
        )

        with caplog.at_level(logging.INFO):
            _ = SessionIngester(
                conn=conn,
                session_file=session_file,
                batch_size=10,
                verbose=False,
                errors=[],
                rules=None,
            )

        TC.assertNotIn("Ingesting", caplog.text)
        conn.close()


# ============================================================================
# Ingest Session File Integration Tests
# ============================================================================


class TestIngestSessionFileWithRules:
    """Test ingest_session_file with rule loading."""

    def test_ingest_session_file_with_missing_rules_path(self, tmp_path: Path) -> None:
        """ingest_session_file should handle missing rules gracefully."""
        session_file = tmp_path / "session.jsonl"
        session_file.write_text(
            json.dumps({"type": "event_msg", "payload": {}}) + "\n",
            encoding="utf-8",
        )
        db_path = tmp_path / "db.sqlite"

        summary = ingest_session_file(
            session_file,
            db_path,
            rules_path=tmp_path / "nonexistent_rules.yml",
            verbose=False,
        )

        TC.assertIsNotNone(summary)
        TC.assertIn("file_id", summary)
        TC.assertIn("errors", summary)

    def test_ingest_sessions_in_directory_with_single_file(
        self, tmp_path: Path
    ) -> None:
        """ingest_sessions_in_directory should ingest single file in directory."""
        from src.services.ingest import ingest_sessions_in_directory

        session_dir = tmp_path / "sessions" / "2025" / "01" / "01"
        session_dir.mkdir(parents=True, exist_ok=True)

        session_file = session_dir / "session.jsonl"
        session_file.write_text(
            json.dumps({"type": "event_msg", "payload": {}}) + "\n",
            encoding="utf-8",
        )

        db_path = tmp_path / "db.sqlite"

        summaries = list(
            ingest_sessions_in_directory(
                tmp_path / "sessions",
                db_path,
                limit=1,
                verbose=False,
            )
        )

        TC.assertEqual(len(summaries), 1)
        TC.assertIn("file_id", summaries[0])

    def test_ingest_sessions_in_directory_with_limit(self, tmp_path: Path) -> None:
        """ingest_sessions_in_directory should respect limit parameter."""
        from src.services.ingest import ingest_sessions_in_directory

        # Create multiple session files
        for i in range(3):
            session_dir = tmp_path / "sessions" / "2025" / f"0{i+1}" / "01"
            session_dir.mkdir(parents=True, exist_ok=True)
            session_file = session_dir / f"session_{i}.jsonl"
            session_file.write_text(
                json.dumps({"type": "event_msg", "payload": {}}) + "\n",
                encoding="utf-8",
            )

        db_path = tmp_path / "db.sqlite"

        summaries = list(
            ingest_sessions_in_directory(
                tmp_path / "sessions",
                db_path,
                limit=2,
                verbose=False,
            )
        )

        TC.assertEqual(len(summaries), 2)


# ============================================================================
# Rule Application Tests
# ============================================================================


class TestRuleApplicationFunctions:
    """Test rule application helper functions."""

    def test_apply_rule_applications_for_text_with_empty_text(
        self, tmp_path: Path
    ) -> None:
        """_apply_rule_applications_for_text should skip empty text."""
        db_path = tmp_path / "test.db"
        with get_connection(db_path) as conn:
            ensure_schema(conn)
            _apply_rule_applications_for_text(
                conn=conn,
                rules=[],
                file_id=1,
                prompt_id=1,
                session_file_path="test.jsonl",
                text="",
                scope="prompt",
                field_path="prompt.message",
            )

    def test_apply_rule_applications_for_event_with_unknown_event_type(
        self, tmp_path: Path
    ) -> None:
        """_apply_rule_applications_for_event should handle unknown event types."""
        conn = get_connection(tmp_path / "test.sqlite")
        ensure_schema(conn)

        cursor = conn.execute("INSERT INTO files (path) VALUES (?)", ("test.jsonl",))
        file_id = int(cursor.lastrowid or 0)

        event = {
            "type": "unknown_type",
            "payload": {"data": "test"},
        }

        rules: list[RedactionRule] = []

        _apply_rule_applications_for_event(
            conn=conn,
            rules=rules,
            file_id=file_id,
            prompt_id=1,
            session_file_path="test.jsonl",
            event=event,
        )

        conn.close()

    def test_apply_rule_applications_pre_prompt_with_empty_prelude(
        self, tmp_path: Path
    ) -> None:
        """_apply_rule_applications_pre_prompt should handle empty prelude."""
        conn = get_connection(tmp_path / "test.sqlite")
        ensure_schema(conn)

        cursor = conn.execute("INSERT INTO files (path) VALUES (?)", ("test.jsonl",))
        file_id = int(cursor.lastrowid or 0)

        rules: list[RedactionRule] = []
        prelude: list[dict[str, Any]] = []

        _apply_rule_applications_pre_prompt(
            conn=conn,
            rules=rules,
            file_id=file_id,
            session_file_path="test.jsonl",
            prelude=prelude,
        )

        conn.close()

    def test_apply_rule_applications_for_prompt_with_missing_payload(
        self, tmp_path: Path
    ) -> None:
        """_apply_rule_applications_for_prompt should handle missing payload."""
        conn = get_connection(tmp_path / "test.sqlite")
        ensure_schema(conn)

        cursor = conn.execute("INSERT INTO files (path) VALUES (?)", ("test.jsonl",))
        file_id = int(cursor.lastrowid or 0)

        prompt_event = {"type": "user_message", "payload": None}
        events: list[dict[str, Any]] = []
        rules: list[RedactionRule] = []

        _apply_rule_applications_for_prompt(
            conn=conn,
            rules=rules,
            file_id=file_id,
            prompt_id=1,
            session_file_path="test.jsonl",
            prompt_event=prompt_event,
            events=events,
        )

        conn.close()


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestIngestSessionFileEdgeCases:
    """Test edge cases in session file ingestion."""

    def test_ingest_session_file_with_verbose_enabled(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """ingest_session_file with verbose=True should log information."""
        session_file = tmp_path / "session.jsonl"
        session_file.write_text(
            json.dumps({"type": "event_msg", "payload": {}}) + "\n",
            encoding="utf-8",
        )
        db_path = tmp_path / "db.sqlite"

        with caplog.at_level(logging.INFO):
            summary = ingest_session_file(
                session_file,
                db_path,
                verbose=True,
            )

        TC.assertIsNotNone(summary)
        TC.assertIn("file_id", summary)

    def test_ingest_session_file_multiple_times_same_file(self, tmp_path: Path) -> None:
        """ingest_session_file should handle re-ingestion of same file."""
        session_file = tmp_path / "session.jsonl"
        session_file.write_text(
            json.dumps({"type": "event_msg", "payload": {}}) + "\n",
            encoding="utf-8",
        )
        db_path = tmp_path / "db.sqlite"

        summary1 = ingest_session_file(session_file, db_path)
        TC.assertIsNotNone(summary1)

        summary2 = ingest_session_file(session_file, db_path)
        TC.assertIsNotNone(summary2)

        conn = get_connection(db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM files WHERE path = ?",
            (str(session_file),),
        ).fetchone()[0]
        conn.close()

        TC.assertEqual(count, 1)

    def test_ingest_sessions_in_directory_empty_directory(self, tmp_path: Path) -> None:
        """ingest_sessions_in_directory should raise when no files found."""
        from src.services.ingest import ingest_sessions_in_directory
        from src.parsers.session_parser import SessionDiscoveryError

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir(parents=True, exist_ok=True)
        db_path = tmp_path / "db.sqlite"

        with pytest.raises(SessionDiscoveryError):
            list(ingest_sessions_in_directory(empty_dir, db_path, verbose=False))
