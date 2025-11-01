"""Base models for AI agent events."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from .event_data import BaseEventData, EventCategory, EventPriority


class BaseEvent(ABC):
    """Base class for all AI agent events.

    This class provides a consistent interface for all event types while
    delegating data storage to the BaseEventData container.
    """

    def __init__(
        self,
        agent_type: str,
        timestamp: datetime,
        event_type: str,
        event_category: EventCategory,
        priority: EventPriority = EventPriority.MEDIUM,
        session_id: str | None = None,
        raw_data: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a base event.

        Args:
            agent_type: Type identifier for the AI agent
            timestamp: When the event occurred
            event_type: Type of event (e.g. "user_message", "agent_response")
            event_category: High-level category for the event
            priority: Processing/display priority for the event
            session_id: Identifier for the agent session
            raw_data: Original event data for audit/debugging
        """
        self._data = BaseEventData(
            agent_type=agent_type,
            timestamp=timestamp,
            event_type=event_type,
            event_category=event_category,
            priority=priority,
            session_id=session_id,
            raw_data=raw_data,
        )

    @property
    def agent_type(self) -> str:
        """Get the agent type identifier."""
        return self._data.agent_type

    @property
    def timestamp(self) -> datetime:
        """Get the event timestamp."""
        return self._data.timestamp

    @property
    def event_type(self) -> str:
        """Get the event type."""
        return self._data.event_type

    @property
    def event_category(self) -> EventCategory:
        """Get the event category."""
        return self._data.event_category

    @property
    def priority(self) -> EventPriority:
        """Get the event priority."""
        return self._data.priority

    @property
    def session_id(self) -> str | None:
        """Get the session identifier."""
        return self._data.session_id

    @property
    def raw_data(self) -> dict[str, Any]:
        """Get the raw event data."""
        return self._data.raw_data or {}

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Convert event to a dictionary for storage/serialization.

        Returns:
            Dictionary representation of the event
        """

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict[str, Any]) -> BaseEvent:
        """Create an event instance from a dictionary.

        Args:
            data: Dictionary containing event data

        Returns:
            New event instance
        """
