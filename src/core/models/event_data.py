"""Data models for base event handling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Any


class EventCategory(Enum):
    """High-level categorization of event types."""

    USER_INPUT = auto()
    AGENT_RESPONSE = auto()
    SYSTEM = auto()
    TOOL_CALL = auto()
    TOOL_RESULT = auto()
    REASONING = auto()
    ERROR = auto()
    OTHER = auto()


class EventPriority(Enum):
    """Priority level for event processing and display."""

    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()


@dataclass
class BaseEventData:
    """Data container for core event attributes."""

    agent_type: str
    timestamp: datetime
    event_type: str
    event_category: EventCategory
    priority: EventPriority = EventPriority.MEDIUM
    session_id: str | None = None
    raw_data: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Validate event data after initialization."""
        if not self.agent_type:
            raise ValueError("agent_type cannot be empty")
        if not self.event_type:
            raise ValueError("event_type cannot be empty")
