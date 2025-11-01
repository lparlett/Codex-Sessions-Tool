"""Base interfaces for AI agent log parsing."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Iterator, Optional

from ..models.base_event import BaseEvent


class AgentLogMetadata:
    """Metadata about an agent's log file."""

    def __init__(
        self,
        agent_type: str,
        session_id: str,
        timestamp: datetime,
        workspace_path: Optional[str] = None,
        user_id: Optional[str] = None,
        version: Optional[str] = None,
    ) -> None:
        self.agent_type = agent_type
        self.session_id = session_id
        self.timestamp = timestamp
        self.workspace_path = workspace_path
        self.user_id = user_id
        self.version = version


class ILogParser(ABC):
    """Interface for AI agent log parsers."""

    @property
    @abstractmethod
    def agent_type(self) -> str:
        """Get the type identifier for this agent parser."""

    @abstractmethod
    def get_metadata(self, file_path: Path) -> AgentLogMetadata:
        """Extract metadata from a log file without fully parsing it.

        Args:
            file_path: Path to the log file

        Returns:
            Metadata about the log file

        Raises:
            ParserError: If metadata cannot be extracted
        """

    @abstractmethod
    def parse_file(self, file_path: Path) -> Iterator[BaseEvent]:
        """Parse a single log file into a sequence of events.

        Args:
            file_path: Path to the log file to parse

        Returns:
            Iterator of parsed events

        Raises:
            ParserError: If the file cannot be parsed
        """

    @abstractmethod
    def find_log_files(self, root_path: Path) -> Generator[Path, None, None]:
        """Find all log files for this agent type in the given root directory.

        Args:
            root_path: Root directory to search for log files

        Returns:
            Generator yielding paths to log files
        """

    @abstractmethod
    def validate_event(self, event_data: dict[str, Any]) -> bool:
        """Validate that an event matches this agent's schema.

        Args:
            event_data: Raw event data to validate

        Returns:
            True if valid, False if not
        """

    @abstractmethod
    def get_agent_type(self) -> str:
        """Get the type identifier for this agent.

        Returns:
            String identifier for this agent type
        """
