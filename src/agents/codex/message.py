"""Codex-specific event models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ...core.models.base_event import BaseEvent, EventCategory, EventPriority


@dataclass
class CodexMessageData:
    """Data container for Codex message attributes."""

    content: str
    timestamp: datetime
    is_user: bool
    session_id: str
    raw_data: dict[str, Any] | None = None


class CodexMessage(BaseEvent):
    """Represents a message (user input or AI response) in a Codex session."""

    @classmethod
    def from_data(cls, data: CodexMessageData) -> CodexMessage:
        """Create a message from message data.

        Args:
            data: Message data container

        Returns:
            New message instance
        """
        instance = cls.__new__(cls)
        instance._data = data
        instance._init_base_event()
        return instance

    def _init_base_event(self) -> None:
        """Initialize base event attributes."""
        super().__init__(
            agent_type="codex",
            timestamp=self._data.timestamp,
            event_type="user_message" if self._data.is_user else "ai_response",
            event_category=(
                EventCategory.USER_INPUT
                if self._data.is_user
                else EventCategory.AGENT_RESPONSE
            ),
            priority=EventPriority.HIGH,
            session_id=self._data.session_id,
            raw_data=self._data.raw_data,
        )

    def __init__(
        self,
        content: str,
        timestamp: datetime,
        is_user: bool,
        session_id: str,
        raw_data: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a Codex message event.

        Creates a new message instance using the provided attributes. For creating
        a message from existing data, use the from_data or from_dict class methods.

        Args:
            content: The message text content
            timestamp: When the message was sent/received
            is_user: True if from user, False if from AI
            session_id: Unique identifier for the chat session
            raw_data: Original event data for audit/debugging
        """
        super().__init__(
            agent_type="codex",
            timestamp=timestamp,
            event_type="user_message" if is_user else "ai_response",
            event_category=(
                EventCategory.USER_INPUT if is_user else EventCategory.AGENT_RESPONSE
            ),
            priority=EventPriority.HIGH,
            session_id=session_id,
            raw_data=raw_data,
        )
        self._data = CodexMessageData(
            content=content,
            timestamp=timestamp,
            is_user=is_user,
            session_id=session_id,
            raw_data=raw_data,
        )

    @property
    def content(self) -> str:
        """Get the message content."""
        return self._data.content

    @property
    def is_user(self) -> bool:
        """Whether this is a user message."""
        return self._data.is_user

    @property
    def raw_session_id(self) -> str:
        """Get the original session ID."""
        return self._data.session_id

    def to_dict(self) -> dict[str, Any]:
        """Convert message to a dictionary for storage."""
        return {
            "agent_type": self.agent_type,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "content": self.content,
            "is_user": self.is_user,
            "session_id": self.session_id,
            "raw_data": self._data.raw_data or {},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CodexMessage:
        """Create a message from a dictionary.

        Args:
            data: Dictionary containing serialized message data

        Returns:
            New CodexMessage instance
        """
        message_data = CodexMessageData(
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            is_user=data["is_user"],
            session_id=data["session_id"],
            raw_data=data.get("raw_data", {}),
        )
        return cls.from_data(message_data)
