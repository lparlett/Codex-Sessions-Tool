"""Unit tests for session ingestion functionality."""

from __future__ import annotations

import json
import sqlite3
import unittest
from pathlib import Path
from typing import Any, Iterator, cast

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
from src.services.database import ensure_schema


@pytest.fixture(name="sample_session_file")
def fixture_sample_session_file(tmp_path: Path) -> Path:
    """Create a temporary copy of the sample session file."""
    source = Path("tests/fixtures/sample_session.jsonl")
    dest = tmp_path / "test_session.jsonl"
    dest.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


@pytest.fixture(name="db_connection")
def fixture_db_connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """Create a temporary SQLite database with schema."""
    db_path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(db_path)
    ensure_schema(conn)
    yield conn
    conn.close()


def test_sanitize_json_for_storage_validates_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that sanitize_json_for_storage properly validates its input."""
    with raises(TypeError, match="Event must be a dictionary"):
        sanitize_json_for_storage(cast(Any, "not a dict"))

    with raises(SanitizationError, match="expected dict"):
        # Mock the sanitize_json function to return a non-dict
        def mock_sanitize(_data: dict[str, Any]) -> str:
            return "invalid"

        monkeypatch.setattr(ingest, "sanitize_json", mock_sanitize)
        sanitize_json_for_storage({"test": "data"})


def test_prepare_events_batch_processing(sample_session_file: Path) -> None:
    """Test that _prepare_events correctly processes events in batches."""
    with sample_session_file.open() as f:
        events = [json.loads(line) for line in f]

    errors: list[ProcessingError] = []
    prepared = _prepare_events(events, sample_session_file, errors, batch_size=2)

    # Use unittest assertions for better error messages
    unittest.TestCase().assertEqual(
        len(prepared), len(events), "All valid events should be processed"
    )
    unittest.TestCase().assertFalse(
        errors, "No errors should be reported for valid events"
    )
    unittest.TestCase().assertTrue(
        all(isinstance(event, dict) for event in prepared),
        "All prepared events should be dictionaries",
    )


def test_session_ingester_processes_session(
    db_connection: sqlite3.Connection, sample_session_file: Path
) -> None:
    """Test that SessionIngester correctly processes a complete session."""
    test_case = unittest.TestCase()
    ingester = SessionIngester(
        conn=db_connection,
        session_file=sample_session_file,
        batch_size=1000,
        verbose=False,
        errors=[],
    )

    summary = ingester.process_session()

    # Check summary counts
    test_case.assertEqual(summary["prompts"], 1, "Expected one prompt")
    test_case.assertEqual(summary["token_messages"], 1, "Expected one token message")
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
