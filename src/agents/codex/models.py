"""Codex-specific event models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ...core.models.base_event import BaseEvent, EventCategory, EventPriority


class CodexMessage(BaseEvent):
    """Represents a message (user input or AI response) in a Codex session."""

    def __init__(
        self,
        timestamp: datetime,
        content: str,
        is_user: bool,
        session_id: str,
        raw_data: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a Codex message event.

        Args:
            timestamp: When the message was sent/received
            content: The message text
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
        self.content = content
        self.is_user = is_user
        # session_id is set in the BaseEvent constructor

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
    def from_dict(cls, data: dict[str, Any]) -> CodexMessage:
        """Create a message from a dictionary."""
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            content=data["content"],
            is_user=data["is_user"],
            session_id=data["session_id"],
            raw_data=data["raw_data"],
        )


# CodexAction has been moved to action.py module
