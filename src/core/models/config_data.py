"""Data models for agent configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Dict, Type

from .base_types import AgentConfig, AgentFeatures


@dataclass
class AgentConfigData:
    """Data container for agent configuration."""

    agent_type: str
    root_path: Path
    features: AgentFeatures | None = None

    def __post_init__(self) -> None:
        if not self.agent_type:
            raise ValueError("agent_type cannot be an empty string")


class AgentRegistry:
    """Global registry of available AI agents."""

    _agents: ClassVar[Dict[str, Type[AgentConfig]]] = {}
