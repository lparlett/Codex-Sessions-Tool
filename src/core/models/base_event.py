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

    def __init__(self, data: BaseEventData) -> None:
        """Initialize a base event from validated event data."""
        self._data = data

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
