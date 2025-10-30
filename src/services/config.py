# Purpose: load and validate user configuration for locating Codex session data.
# Author: Codex with Lauren Parlett
# Date: 2025-10-30
# Related tests: TBD (planned)

"""Load user configuration for codex_sessions_tool."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


class ConfigError(RuntimeError):
    """Raised when configuration cannot be loaded or validated."""


@dataclass(frozen=True)
class SessionsConfig:
    """User-defined settings for locating Codex session logs."""

    sessions_root: Path


def load_config(config_path: Path | None = None) -> SessionsConfig:
    """Load configuration from ``user/config.toml`` unless overridden."""

    path = config_path or Path("user") / "config.toml"
    if not path.exists():
        raise ConfigError(
            f"Configuration file not found at {path}. "
            "Copy user/config.example.toml to user/config.toml and set sessions root."
        )

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Config at {path} is not valid TOML: {exc}") from exc

    sessions = data.get("sessions")
    if not isinstance(sessions, dict):
        raise ConfigError("Missing [sessions] table in configuration.")

    root_value = sessions.get("root")
    if not root_value:
        raise ConfigError("Configuration requires 'root' under [sessions].")

    root = Path(root_value).expanduser().resolve()
    if not root.exists():
        raise ConfigError(f"Configured sessions root does not exist: {root}")

    if not root.is_dir():
        raise ConfigError(f"Configured sessions root is not a directory: {root}")

    return SessionsConfig(sessions_root=root)
