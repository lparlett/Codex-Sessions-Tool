"""Test fixtures and configuration."""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

import pytest

from src.core.models.event_data import BaseEventData, EventCategory, EventPriority
from src.agents.codex.models import CodexMessage
from src.services.database import ensure_schema

# Add the project root directory to the Python path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))


@pytest.fixture
def sample_timestamp() -> datetime:
    """Get a fixed timestamp for testing."""
    return datetime(2025, 10, 31, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def sample_event_data(sample_timestamp: datetime) -> BaseEventData:  # pylint: disable=redefined-outer-name
    """Create a sample BaseEventData for testing."""
    return BaseEventData(
        agent_type="codex",
        timestamp=sample_timestamp,
        event_type="test.event",
        event_category=EventCategory.SYSTEM,
        priority=EventPriority.MEDIUM,
        session_id="test-session-001",
        raw_data={"test": "data"}
    )


@pytest.fixture
def sample_codex_message(sample_timestamp: datetime) -> CodexMessage:  # pylint: disable=redefined-outer-name
    """Create a sample CodexMessage for testing."""
    return CodexMessage(
        timestamp=sample_timestamp,
        content="Test message",
        is_user=True,
        session_id="test-session-001",
        raw_data={"test": "data"}
    )


@pytest.fixture
def sample_session_file(tmp_path: Path) -> Path:
    """Create a temporary copy of the sample session file."""
    source = Path("tests/fixtures/sample_session.jsonl")
    dest = tmp_path / "test_session.jsonl"
    dest.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


@pytest.fixture
def db_connection(tmp_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Create a temporary SQLite database with schema."""
    db_path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(db_path)
    ensure_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def sample_raw_event() -> dict[str, Any]:
    """Create a sample raw event dictionary."""
    return {
        "type": "event_msg",
        "timestamp": "2025-10-31T10:00:00Z",
        "payload": {
            "type": "user_message",
            "message": "Test message"
        }
    }
