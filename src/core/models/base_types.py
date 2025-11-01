"""Base types and interfaces for agent configuration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AgentFeatures:
    """Feature flags for agent capabilities."""

    supports_streaming: bool = False
    supports_function_calls: bool = False
    supports_tool_usage: bool = False
    supports_context_window: bool = False
    supports_file_edits: bool = False


class AgentConfig(ABC):
    """Base configuration for an AI agent.

    This class provides a consistent interface for agent configuration while
    delegating data storage to the AgentConfigData container.
    """

    def __init__(
        self, agent_type: str, root_path: Path, features: AgentFeatures | None = None
    ) -> None:
        """Initialize agent configuration.

        Args:
            agent_type: Type identifier for the AI agent
            root_path: Root directory containing agent logs
            features: Optional set of agent feature flags
        """
        self.agent_type = agent_type
        self.root_path = root_path
        self.features = features

    @abstractmethod
    def validate(self) -> None:
        """Validate the configuration.

        Raises:
            ValueError: If configuration is invalid
        """

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary format."""

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentConfig:
        """Create configuration from dictionary data."""
