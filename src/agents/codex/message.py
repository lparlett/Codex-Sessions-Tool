"""Codex message event models.

Purpose: Define message event structures for the Codex agent.
Author: Codex + user
Date: 2025-10-30
Related tests: tests/conftest.py

AI-assisted code: Portions generated with AI support.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ...core.models.base_event import BaseEvent, EventCategory, EventPriority


@dataclass(frozen=True)
class CodexMessageData:
    """Immutable container for Codex message attributes."""

    content: str
    is_user: bool
    session_id: str
    timestamp: datetime
    raw_data: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        """Return event type derived from author."""
        return "user_message" if self.is_user else "ai_response"

    @property
    def category(self) -> EventCategory:
        """Return event category derived from author."""
        return (
            EventCategory.USER_INPUT if self.is_user else EventCategory.AGENT_RESPONSE
        )


class Message(BaseEvent):
    """Represents a message (user input or AI response) in a Codex session."""

    def __init__(
        self,
        content: str,
        is_user: bool,
        session_id: str,
        timestamp: datetime | None = None,
        raw_data: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a Codex message event."""
        resolved_timestamp = timestamp or datetime.now()
        event_category = (
            EventCategory.USER_INPUT if is_user else EventCategory.AGENT_RESPONSE
        )

        super().__init__(
            agent_type="codex",
            timestamp=resolved_timestamp,
            event_type="user_message" if is_user else "ai_response",
            event_category=event_category,
            priority=EventPriority.HIGH,
            session_id=session_id,
            raw_data=raw_data,
        )

        self._content = content
        self._is_user = is_user

    @property
    def content(self) -> str:
        """Get the message content."""
        return self._content

    @property
    def is_user(self) -> bool:
        """Get whether this is a user message."""
        return self._is_user

    def to_dict(self) -> dict[str, Any]:
        """Convert message to dictionary for storage."""
        return {
            "agent_type": self.agent_type,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "event_category": self.event_category.value,
            "priority": self.priority.value,
            "session_id": self.session_id,
            "content": self.content,
            "is_user": self.is_user,
            "raw_data": self.raw_data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        """Create a message from a dictionary."""
        return cls(
            content=data["content"],
            is_user=data["is_user"],
            session_id=data["session_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            raw_data=data.get("raw_data"),
        )


class CodexMessage(BaseEvent):
    """Represents a message (user input or AI response) in a Codex session."""

    def __init__(self, data: CodexMessageData) -> None:
        """Initialize a Codex message event with structured data."""
        super().__init__(
            agent_type="codex",
            timestamp=data.timestamp,
            event_type=data.event_type,
            event_category=data.category,
            priority=EventPriority.HIGH,
            session_id=data.session_id,
            raw_data=data.raw_data,
        )
        self._message_data = data

    @property
    def content(self) -> str:
        """Get the message content."""
        return self._message_data.content

    @property
    def is_user(self) -> bool:
        """Whether this is a user message."""
        return self._message_data.is_user

    @property
    def raw_session_id(self) -> str:
        """Get the original session ID."""
        return self._message_data.session_id

    def to_dict(self) -> dict[str, Any]:
        """Convert message to a dictionary for storage."""
        return {
            "agent_type": self.agent_type,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "content": self.content,
            "is_user": self.is_user,
            "session_id": self.session_id,
            "raw_data": self.raw_data,
        }

    @classmethod
    def create(
        cls,
        content: str,
        timestamp: datetime,
        is_user: bool,
        session_id: str,
        raw_data: dict[str, Any] | None = None,
    ) -> CodexMessage:
        """Create a new message instance from primitive values."""
        data = CodexMessageData(
            content=content,
            is_user=is_user,
            session_id=session_id,
            timestamp=timestamp,
            raw_data=raw_data,
        )
        return cls(data)

    @classmethod
    def from_data(cls, data: CodexMessageData) -> CodexMessage:
        """Create a message instance from message data."""
        return cls(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CodexMessage:
        """Create a message from a dictionary."""
        message_data = CodexMessageData(
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            is_user=data["is_user"],
            session_id=data["session_id"],
            raw_data=data.get("raw_data", {}),
        )
        return cls.from_data(message_data)
