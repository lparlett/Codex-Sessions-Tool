"""Tests for CodexParser implementation (AI-assisted by Codex GPT-5)."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

import pytest

from src.agents.codex.parser import CodexParser
from src.agents.codex.errors import InvalidEventError, InvalidMetadataError
from src.agents.codex.models import CodexAction, CodexMessage
from src.core.interfaces.parser import AgentLogMetadata

TC = unittest.TestCase()


class TestableCodexParser(CodexParser):
    """Concrete CodexParser for testing abstract requirements."""

    def find_log_files(self, root_path: Path) -> Generator[Path, None, None]:
        yield from root_path.glob("*.jsonl")

    def get_agent_type(self) -> str:
        return self.agent_type


def _write_lines(tmp_path: Path, *lines: str) -> Path:
    """Helper to write a JSONL file with provided lines."""

    file_path = tmp_path / "session.jsonl"
    file_path.write_text("\n".join(lines), encoding="utf-8")
    return file_path


def test_get_metadata_happy_path(tmp_path: Path) -> None:
    """Metadata should parse session_meta first line."""
    session_meta = (
        '{"type": "session_meta", "timestamp": "2025-11-23T10:00:00+00:00",'
        ' "payload": {"id": "sid-123", "cwd": "C:/repo"}}'
    )
    file_path = _write_lines(tmp_path, session_meta)
    meta = TestableCodexParser().get_metadata(file_path)
    TC.assertIsInstance(meta, AgentLogMetadata)
    TC.assertEqual(meta.session_id, "sid-123")
    TC.assertEqual(meta.workspace_path, "C:/repo")
    TC.assertEqual(meta.timestamp, datetime(2025, 11, 23, 10, 0, tzinfo=timezone.utc))


@pytest.mark.parametrize(
    "line, expected",
    [
        ("", "Empty log file"),
        ('{"not": "json"', "Invalid JSON"),
        (
            '{"type": "not_session_meta", "timestamp": "2025-11-23T10:00:00"}',
            "session_meta",
        ),
        (
            '{"type": "session_meta", "timestamp": "2025-11-23T10:00:00", "payload": "x"}',
            "payload",
        ),
        ('{"type": "session_meta", "timestamp": 123, "payload": {}}', "timestamp"),
        (
            '{"type": "session_meta", "timestamp": "not-a-date", "payload": {}}',
            "timestamp",
        ),
        (
            '{"type": "session_meta", "timestamp": "2025-11-23T10:00:00", "payload": {}}',
            "session ID",
        ),
    ],
)
def test_get_metadata_errors(tmp_path: Path, line: str, expected: str) -> None:
    """get_metadata should raise InvalidMetadataError on malformed first line."""
    file_path = _write_lines(tmp_path, line)
    with pytest.raises(InvalidMetadataError) as exc:
        TestableCodexParser().get_metadata(file_path)
    TC.assertIn(expected, str(exc.value))


def test_parse_file_yields_messages_and_actions(tmp_path: Path) -> None:
    """parse_file should emit CodexMessage and CodexAction events."""
    session_meta = (
        '{"type": "session_meta", "timestamp": "2025-11-23T10:00:00+00:00",'
        ' "payload": {"id": "sid-123", "cwd": "C:/repo"}}'
    )
    user_msg = (
        '{"type": "event_msg", "timestamp": "2025-11-23T10:00:01+00:00",'
        ' "payload": {"type": "user_message", "message": "Hi"}}'
    )
    ai_response = (
        '{"type": "event_msg", "timestamp": "2025-11-23T10:00:02+00:00",'
        ' "payload": {"type": "ai_response", "message": "Hello"}}'
    )
    tool_call = (
        '{"type": "event_msg", "timestamp": "2025-11-23T10:00:03+00:00",'
        ' "payload": {"type": "tool_call", "tool": {"name": "shell", "parameters": {"cmd": "ls"}}}}'
    )
    tool_result = (
        '{"type": "event_msg", "timestamp": "2025-11-23T10:00:04+00:00",'
        ' "payload": {"type": "tool_result", "tool": {"name": "shell"}, "result": "ok"}}'
    )
    file_path = _write_lines(
        tmp_path, session_meta, user_msg, ai_response, tool_call, tool_result
    )
    events = list(TestableCodexParser().parse_file(file_path))
    TC.assertEqual(len(events), 4)
    TC.assertEqual(sum(isinstance(e, CodexMessage) for e in events), 2)
    TC.assertEqual(sum(isinstance(e, CodexAction) for e in events), 2)


def test_parse_file_invalid_event_raises(tmp_path: Path) -> None:
    """Invalid event should raise InvalidEventError with line context."""
    session_meta = (
        '{"type": "session_meta", "timestamp": "2025-11-23T10:00:00+00:00",'
        ' "payload": {"id": "sid-123"}}'
    )
    bad_event = (
        '{"type": "event_msg", "timestamp": "2025-11-23T10:00:01+00:00",'
        ' "payload": {"type": "unknown"}}'
    )
    file_path = _write_lines(tmp_path, session_meta, bad_event)
    with pytest.raises(InvalidEventError) as exc:
        list(TestableCodexParser().parse_file(file_path))
    TC.assertIn("Line: 2", str(exc.value))


def test_parse_file_invalid_json_raises(tmp_path: Path) -> None:
    """Malformed JSON lines should raise InvalidEventError."""
    session_meta = (
        '{"type": "session_meta", "timestamp": "2025-11-23T10:00:00+00:00",'
        ' "payload": {"id": "sid-123"}}'
    )
    file_path = _write_lines(tmp_path, session_meta, '{"invalid": ')
    with pytest.raises(InvalidEventError):
        list(TestableCodexParser().parse_file(file_path))


def test_validate_event_branches() -> None:
    """Cover validation helper branches."""
    parser = TestableCodexParser()
    base: dict[str, Any] = {
        "type": "event_msg",
        "timestamp": "2025-11-23T10:00:00",
        "payload": {"type": "user_message", "message": "ok"},
    }
    TC.assertTrue(parser.validate_event(base))
    TC.assertFalse(parser.validate_event({"timestamp": "2025-11-23"}))  # missing type
    TC.assertFalse(
        parser.validate_event({"type": "event_msg", "timestamp": 123, "payload": {}})
    )
    TC.assertFalse(
        parser.validate_event(
            {
                "type": "event_msg",
                "timestamp": "2025-11-23",
                "payload": {"type": "user_message"},
            }
        )
    )
    TC.assertTrue(
        parser.validate_event(
            {
                "type": "event_msg",
                "timestamp": "2025-11-23",
                "payload": {"type": "tool_call", "tool": {"name": "x"}},
            }
        )
    )
    TC.assertFalse(
        parser._validate_base_structure(
            {"type": "event_msg"}
        )  # pylint: disable=protected-access
    )
    TC.assertFalse(
        parser._validate_message_event(  # pylint: disable=protected-access
            {"type": "tool_call", "tool": "bad"}
        )
    )
