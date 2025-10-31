# Purpose: load and validate user configuration for locating Codex session data.
# Author: Codex with Lauren Parlett
# Date: 2025-10-30
# Related tests: TBD (planned)

"""Load user configuration for codex_sessions_tool."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

if sys.version_info >= (3, 11):
    import tomllib
    _toml_loads = tomllib.loads
    _TOMLDecodeError = tomllib.TOMLDecodeError
else:
    import tomli
    _toml_loads = tomli.loads
    _TOMLDecodeError = tomli.TOMLDecodeError


class ConfigError(RuntimeError):
    """Raised when configuration cannot be loaded or validated."""


@dataclass(frozen=True)
class SessionsConfig:
    """User-defined settings for locating Codex session logs."""

    sessions_root: Path
    ingest_batch_size: int = 1000


def load_config(config_path: Path | None = None) -> SessionsConfig:
    """Load configuration from ``user/config.toml`` unless overridden."""

    path = config_path or Path("user") / "config.toml"
    if not path.exists():
        raise ConfigError(
            f"Configuration file not found at {path}. "
            "Copy user/config.example.toml to user/config.toml and set sessions root."
        )

    try:
        data = _toml_loads(path.read_text(encoding="utf-8"))
    except _TOMLDecodeError as exc:
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

    ingest_config = data.get("ingest", {})
    batch_size = 1000
    if isinstance(ingest_config, dict):
        override = ingest_config.get("batch_size")
        if override is not None:
            if not isinstance(override, int) or override <= 0:
                raise ConfigError(
                    "ingest.batch_size must be a positive integer when provided."
                )
            batch_size = override

    return SessionsConfig(sessions_root=root, ingest_batch_size=batch_size)
