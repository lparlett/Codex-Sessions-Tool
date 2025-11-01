"""Tests for session ingestion functionality."""

from __future__ import annotations

import sqlite3
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from pytest import raises

from src.services import ingest
from src.services.ingest import (
    ProcessingError,
    SessionIngester,
    _prepare_events,
    ingest_session_file,
    sanitize_json_for_storage,
    SanitizationError,
)


@pytest.fixture(name="sample_session_file")
def fixture_sample_session_file(tmp_path: Path) -> Path:
    """Create a temporary copy of the sample session file."""
    source = Path("tests/fixtures/sample_session.jsonl")
    dest = tmp_path / "test_session.jsonl"
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
        "payload": {
            "type": "user_message",
            "message": "Test message"
        }
    }

    events = [test_event, test_event]  # Two identical events
    errors: list[ProcessingError] = []
    prepared = _prepare_events(events, sample_session_file, errors, batch_size=1)

    test_case.assertEqual(len(prepared), len(events),
                         "All valid events should be processed")
    test_case.assertEqual(len(errors), 0,
                         "No errors should be reported for valid events")
    
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


def test_ingest_session_file_handles_errors(tmp_path: Path) -> None:
    """Test that ingest_session_file properly handles and reports errors."""
    invalid_file = tmp_path / "invalid.jsonl"
    invalid_file.write_text("invalid json\n{", encoding="utf-8")
    db_path = tmp_path / "test.sqlite"

    with raises(ValueError, match="Failed to parse JSON"):
        ingest_session_file(invalid_file, db_path)
