"""Tests for parser interface definitions (AI-assisted by Codex GPT-5)."""

# pylint: disable=import-error,too-few-public-methods

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Iterator

import pytest

from src.core.interfaces.parser import AgentLogMetadata, ILogParser
from src.core.models.base_event import BaseEvent
from src.core.models.event_data import BaseEventData, EventCategory, EventPriority


class DummyEvent(BaseEvent):
    """Minimal concrete event for testing."""

    def to_dict(self) -> dict[str, Any]:
        return self.raw_data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaseEvent:
        event_data = BaseEventData(
            agent_type=data.get("agent_type", "dummy"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            event_type=data.get("event_type", "dummy"),
            event_category=EventCategory.SYSTEM,
            priority=EventPriority.MEDIUM,
            session_id=data.get("session_id"),
            raw_data=data,
        )
        return cls(event_data)


class DummyParser(ILogParser):
    """Concrete parser implementation used for interface tests."""

    @property
    def agent_type(self) -> str:
        return "dummy"

    def get_metadata(self, file_path: Path) -> AgentLogMetadata:
        return AgentLogMetadata(
            agent_type=self.agent_type,
            session_id=file_path.stem,
            timestamp=datetime(2025, 11, 23, tzinfo=timezone.utc),
            workspace_path=str(file_path.parent),
        )

    def parse_file(self, file_path: Path) -> Iterator[BaseEvent]:
        data = BaseEventData(
            agent_type=self.agent_type,
            timestamp=datetime(2025, 11, 23, tzinfo=timezone.utc),
            event_type="parsed",
            event_category=EventCategory.SYSTEM,
            priority=EventPriority.MEDIUM,
            session_id=file_path.stem,
            raw_data={"path": str(file_path)},
        )
        yield DummyEvent(data)

    def find_log_files(self, root_path: Path) -> Generator[Path, None, None]:
        yield from sorted(root_path.glob("*.jsonl"))

    def validate_event(self, event_data: dict[str, Any]) -> bool:
        return bool(event_data.get("valid"))

    def get_agent_type(self) -> str:
        return self.agent_type


def test_agent_log_metadata_frozen() -> None:
    """AgentLogMetadata should be immutable and carry optional fields."""
    meta = AgentLogMetadata(
        agent_type="dummy",
        session_id="abc",
        timestamp=datetime(2025, 11, 23, tzinfo=timezone.utc),
    )
    with pytest.raises(FrozenInstanceError):
        meta.agent_type = "changed"  # type: ignore[misc]


def test_ilogparser_requires_abstracts() -> None:
    """Instantiating ILogParser without implementations should fail."""

    class PartialParser(ILogParser):  # pylint: disable=abstract-method
        @property
        def agent_type(self) -> str:  # pragma: no cover - abstract enforcement
            return "partial"

    with pytest.raises(TypeError):
        PartialParser()  # type: ignore[abstract]  # pylint: disable=abstract-class-instantiated


def test_dummy_parser_metadata_and_agent_type(tmp_path: Path) -> None:
    """Verify metadata extraction and agent type helpers."""
    parser = DummyParser()
    file_path = tmp_path / "session-1.jsonl"
    file_path.write_text("{}", encoding="utf-8")
    meta = parser.get_metadata(file_path)
    assert meta.agent_type == "dummy"
    assert meta.session_id == "session-1"
    assert parser.agent_type == parser.get_agent_type()


def test_dummy_parser_parse_and_validation(tmp_path: Path) -> None:
    """Ensure parse_file yields BaseEvent and validate_event respects flag."""
    parser = DummyParser()
    file_path = tmp_path / "session-2.jsonl"
    file_path.write_text("{}", encoding="utf-8")
    events = list(parser.parse_file(file_path))
    assert len(events) == 1
    assert isinstance(events[0], BaseEvent)
    assert parser.validate_event({"valid": True})
    assert not parser.validate_event({})


def test_dummy_parser_find_log_files_sorted(tmp_path: Path) -> None:
    """find_log_files should yield JSONL files in sorted order."""
    file_b = tmp_path / "b.jsonl"
    file_a = tmp_path / "a.jsonl"
    file_a.write_text("a", encoding="utf-8")
    file_b.write_text("b", encoding="utf-8")
    parser = DummyParser()
    found = list(parser.find_log_files(tmp_path))
    assert found == [file_a, file_b]
