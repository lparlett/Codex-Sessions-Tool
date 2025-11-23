"""Codex action event model.

Purpose: Represent AI agent actions (tool calls, file edits, etc.).
Author: Codex + user
Date: 2025-10-30
Related tests: tests/conftest.py

AI-assisted code: Portions generated with AI support.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ...core.models.base_event import BaseEvent
from ...core.models.event_data import BaseEventData, EventCategory, EventPriority


@dataclass(frozen=True)
class ActionData:
    """Immutable container for Codex action attributes."""

    action_type: str
    session_id: str
    timestamp: datetime
    details: dict[str, Any] | None = None
    raw_data: dict[str, Any] | None = None

    @property
    def category(self) -> EventCategory:
        """Return the event category for the action type."""
        if self.action_type == "tool_call":
            return EventCategory.TOOL_CALL
        if self.action_type == "tool_result":
            return EventCategory.TOOL_RESULT
        return EventCategory.SYSTEM


class Action(BaseEvent):
    """Represents an action taken by the Codex AI agent."""

    def __init__(self, data: ActionData) -> None:
        """Initialize a Codex action event with structured data."""
        super().__init__(
            BaseEventData(
                agent_type="codex",
                timestamp=data.timestamp,
                event_type=f"action.{data.action_type}",
                event_category=data.category,
                priority=EventPriority.MEDIUM,
                session_id=data.session_id,
                raw_data=data.raw_data or {},
            )
        )
        self._action_type = data.action_type
        self._details = data.details or {}

    @property
    def action_type(self) -> str:
        """Get the type of action being performed."""
        return self._action_type

    @property
    def tool_name(self) -> str | None:
        """Get the name of the tool if this is a tool action."""
        return self._details.get("tool_name")

    @property
    def parameters(self) -> dict[str, Any] | None:
        """Get the tool parameters if this is a tool action."""
        return self._details.get("parameters")

    @property
    def result(self) -> str | None:
        """Get the action result if available."""
        return self._details.get("result")

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            "agent_type": self.agent_type,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "event_category": self.event_category.value,
            "priority": self.priority.value,
            "session_id": self.session_id,
            "raw_data": self.raw_data,
            "action_type": self._action_type,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "result": self.result,
        }

    @classmethod
    def create(
        cls,
        action_type: str,
        session_id: str,
        timestamp: datetime | None = None,
        details: dict[str, Any] | None = None,
        raw_data: dict[str, Any] | None = None,
    ) -> Action:
        """Factory to build an Action from primitive values."""
        data = ActionData(
            action_type=action_type,
            session_id=session_id,
            timestamp=timestamp or datetime.now(),
            details=details,
            raw_data=raw_data,
        )
        return cls(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Action:
        """Create an Action instance from a dictionary."""
        return cls(
            ActionData(
                action_type=data["action_type"],
                session_id=data["session_id"],
                timestamp=datetime.fromisoformat(data["timestamp"]),
                details={
                    "tool_name": data.get("tool_name"),
                    "parameters": data.get("parameters"),
                    "result": data.get("result"),
                },
                raw_data=data.get("raw_data", {}),
            )
        )
