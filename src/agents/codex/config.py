"""Codex-specific agent configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from ...core.interfaces.config import AgentConfig, AgentFeatures


class CodexConfig(AgentConfig):
    """Configuration for the Codex AI agent."""

    # Class-level default features
    DEFAULT_FEATURES: ClassVar[AgentFeatures] = AgentFeatures(
        supports_streaming=True,
        supports_function_calls=True,
        supports_tool_usage=True,
        supports_file_edits=True,
        supports_context_window=True,
    )

    def __init__(self, root_path: Path, features: AgentFeatures | None = None) -> None:
        """Initialize Codex configuration.

        Args:
            root_path: Root directory containing Codex session logs
            features: Optional feature overrides, falls back to DEFAULT_FEATURES
        """
        super().__init__(
            agent_type="codex",
            root_path=root_path,
            features=features or self.DEFAULT_FEATURES,
        )

    def validate(self) -> None:
        """Validate the configuration.

        Raises:
            ValueError: If the root path is missing or not a directory
        """
        if not self.root_path.exists() or not self.root_path.is_dir():
            raise ValueError(f"Invalid Codex root path: {self.root_path}")

    def to_dict(self) -> dict[str, Any]:
        """Convert config to a dictionary for storage.

        This implementation provides a simplified view of the config data,
        focusing on the most commonly used attributes for serialization.

        Returns:
            Dictionary representation of the config
        """
        return {
            "type": self.agent_type,
            "root": str(self.root_path),
            "features": {
                "streaming": self.features.supports_streaming,
                "function_calls": self.features.supports_function_calls,
                "tool_usage": self.features.supports_tool_usage,
                "context_window": self.features.supports_context_window,
                "file_edits": self.features.supports_file_edits,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CodexConfig:
        """Create a config instance from a dictionary.

        Args:
            data: Dictionary containing config data

        Returns:
            New config instance
        """
        features = AgentFeatures(
            supports_streaming=data.get("features", {}).get("streaming", True),
            supports_function_calls=data.get("features", {}).get(
                "function_calls", True
            ),
            supports_tool_usage=data.get("features", {}).get("tool_usage", True),
            supports_context_window=data.get("features", {}).get(
                "context_window", True
            ),
            supports_file_edits=data.get("features", {}).get("file_edits", True),
        )
        return cls(root_path=Path(data["root"]), features=features)
