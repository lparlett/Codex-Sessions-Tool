"""Codex action event model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ...core.models.base_event import (
    BaseEvent,
    BaseEventData,
    EventCategory,
    EventPriority,
)


@dataclass
class CodexActionData:
    """Data container for Codex action attributes."""

    action_type: str
    timestamp: datetime
    session_id: str
    tool_name: str | None = None
    parameters: dict[str, Any] | None = None
    result: str | None = None
    raw_data: dict[str, Any] | None = None


class CodexAction(BaseEvent):
    """Represents an action taken by the AI (tool use, file edit, etc)."""

    def __init__(
        self,
        action_type: str,
        timestamp: datetime,
        session_id: str,
        tool_name: str | None = None,
        parameters: dict[str, Any] | None = None,
        result: str | None = None,
        raw_data: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a Codex action event.

        Creates a new action instance using the provided attributes. For creating
        an action from existing data, use the from_data class method instead.

        Args:
            action_type: Type of action (tool_call, file_edit, etc)
            timestamp: When the action occurred
            session_id: Unique identifier for the chat session
            tool_name: Name of tool used (if applicable)
            parameters: Tool parameters (if applicable)
            result: Result/output of the action
            raw_data: Original event data for audit/debugging
        """
        self._action_data = CodexActionData(
            action_type=action_type,
            timestamp=timestamp,
            session_id=session_id,
            tool_name=tool_name,
            parameters=parameters,
            result=result,
            raw_data=raw_data,
        )

        # Initialize base class with computed event info
        super().__init__(
            agent_type="codex",
            timestamp=timestamp,
            event_type=f"action.{action_type}",
            event_category=self._get_category(action_type),
            priority=EventPriority.MEDIUM,
            session_id=session_id,
            raw_data=raw_data,
        )

    @staticmethod
    def _get_category(action_type: str) -> EventCategory:
        """Get the event category based on action type."""
        if action_type == "tool_call":
            return EventCategory.TOOL_CALL
        elif action_type == "tool_result":
            return EventCategory.TOOL_RESULT
        return EventCategory.SYSTEM

    @classmethod
    def from_data(
        cls, data: CodexActionData, base_event_data: BaseEventData | None = None
    ) -> CodexAction:
        """Create an action from action data.

        Args:
            data: Action data container
            base_event_data: Optional base event data. If not provided, will be
                created from the action data.

        Returns:
            New action instance
        """
        instance = cls(
            action_type=data.action_type,
            timestamp=data.timestamp,
            session_id=data.session_id,
            tool_name=data.tool_name,
            parameters=data.parameters,
            result=data.result,
            raw_data=data.raw_data,
        )
        if base_event_data:
            instance._data = base_event_data
        return instance

    @property
    def action_type(self) -> str:
        """Get the action type."""
        return self._action_data.action_type

    @property
    def tool_name(self) -> str | None:
        """Get the tool name if available."""
        return self._action_data.tool_name

    @property
    def parameters(self) -> dict[str, Any] | None:
        """Get the tool parameters if available."""
        return self._action_data.parameters

    @property
    def result(self) -> str | None:
        """Get the action result if available."""
        return self._action_data.result

    @property
    def raw_session_id(self) -> str:
        """Get the original session ID."""
        if self._action_data.session_id is None:
            raise ValueError("Session ID is required but was None")
        return self._action_data.session_id

    def to_dict(self) -> dict[str, Any]:
        """Convert action to a dictionary for storage."""
        return {
            "agent_type": self.agent_type,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "action_type": self.action_type,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "result": self.result,
            "session_id": self.session_id,
            "raw_data": self._data.raw_data or {},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CodexAction:
        """Create an action from a dictionary."""
        action_data = CodexActionData(
            action_type=data["action_type"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            session_id=data["session_id"],
            tool_name=data.get("tool_name"),
            parameters=data.get("parameters"),
            result=data.get("result"),
            raw_data=data.get("raw_data", {}),
        )
        return cls.from_data(action_data)
