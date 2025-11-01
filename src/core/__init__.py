"""Core interfaces and models for AI-Log-Trail."""

from .interfaces.config import AgentConfig
from .interfaces.parser import ILogParser
from .models.base_event import BaseEvent

__all__ = ["AgentConfig", "BaseEvent", "ILogParser"]
