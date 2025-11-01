"""Codex-specific parser errors."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ParserError(Exception):
    """Base class for parser errors."""

    message: str
    file_path: Path | None = None
    line_number: int | None = None

    def __str__(self) -> str:
        parts = [self.message]
        if self.file_path:
            parts.append(f"File: {self.file_path}")
        if self.line_number is not None:
            parts.append(f"Line: {self.line_number}")
        return " - ".join(parts)


class InvalidMetadataError(ParserError):
    """Raised when metadata cannot be extracted from a log file."""


class InvalidEventError(ParserError):
    """Raised when an event fails validation."""
