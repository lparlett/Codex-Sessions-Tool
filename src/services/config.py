"""Load user configuration for codex_sessions_tool.

Purpose: Load and validate user configuration for locating Codex session data.
Author: Codex with Lauren Parlett
Date: 2025-10-30
AI-assisted: Updated with Codex (GPT-5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
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
class DatabaseConfig:
    """Database connection preferences."""

    backend: str = "sqlite"  # sqlite or postgres
    sqlite_path: Path = Path("reports") / "session_data.sqlite"
    postgres_dsn: str | None = None


@dataclass(frozen=True)
class OutputPaths:
    """Output destinations for generated artifacts."""

    reports_dir: Path = Path("reports")


@dataclass(frozen=True)
class SessionsConfig:
    """User-defined settings for locating Codex session logs."""

    sessions_root: Path
    ingest_batch_size: int = 1000
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    outputs: OutputPaths = field(default_factory=OutputPaths)


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
    batch_size = _load_batch_size(ingest_config)
    database_cfg = _load_database_config(ingest_config, data.get("database", {}))
    outputs_cfg = _load_outputs_config(data.get("outputs", {}))

    return SessionsConfig(
        sessions_root=root,
        ingest_batch_size=batch_size,
        database=database_cfg,
        outputs=outputs_cfg,
    )


def _load_batch_size(ingest_config: dict | None) -> int:
    """Return validated ingest batch size."""

    batch_size = 1000
    if isinstance(ingest_config, dict):
        override = ingest_config.get("batch_size")
        if override is not None:
            if not isinstance(override, int) or override <= 0:
                raise ConfigError(
                    "ingest.batch_size must be a positive integer when provided."
                )
            batch_size = override
    return batch_size


def _load_database_config(
    ingest_config: dict | None, database_table: dict | None
) -> DatabaseConfig:
    """Load database configuration with sensible defaults."""

    backend = "sqlite"
    sqlite_path = Path("reports") / "session_data.sqlite"
    postgres_dsn: str | None = None

    if isinstance(ingest_config, dict):
        db_path = ingest_config.get("db_path")
        if isinstance(db_path, str) and db_path.strip():
            sqlite_path = Path(db_path)

    if isinstance(database_table, dict):
        backend_value = database_table.get("backend")
        if isinstance(backend_value, str) and backend_value.strip():
            backend = backend_value.strip().lower()
        dsn_value = database_table.get("postgres_dsn")
        if isinstance(dsn_value, str) and dsn_value.strip():
            postgres_dsn = dsn_value.strip()
        sqlite_override = database_table.get("sqlite_path")
        if isinstance(sqlite_override, str) and sqlite_override.strip():
            sqlite_path = Path(sqlite_override)

    if backend not in {"sqlite", "postgres"}:
        raise ConfigError("database.backend must be either 'sqlite' or 'postgres'.")

    if backend == "postgres" and not postgres_dsn:
        raise ConfigError("database.postgres_dsn is required when backend=postgres.")

    sqlite_path = _validate_sqlite_path(sqlite_path)

    return DatabaseConfig(
        backend=backend,
        sqlite_path=sqlite_path,
        postgres_dsn=postgres_dsn,
    )


def _load_outputs_config(outputs_table: dict | None) -> OutputPaths:
    """Load and validate output directory configuration."""

    reports_dir = Path("reports")
    if isinstance(outputs_table, dict):
        reports_value = outputs_table.get("reports_dir")
        if isinstance(reports_value, str) and reports_value.strip():
            reports_dir = Path(reports_value)

    resolved_reports_dir = _validate_existing_directory(
        reports_dir, "outputs.reports_dir"
    )
    return OutputPaths(reports_dir=resolved_reports_dir)


def _validate_existing_directory(path: Path, label: str) -> Path:
    """Ensure a path exists and is a directory with write permission."""

    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise ConfigError(f"{label} does not exist: {resolved}")
    if not resolved.is_dir():
        raise ConfigError(f"{label} is not a directory: {resolved}")
    if not os.access(resolved, os.W_OK):
        raise ConfigError(f"{label} is not writable: {resolved}")
    return resolved


def _validate_sqlite_path(sqlite_path: Path) -> Path:
    """Validate SQLite database path and parent directory accessibility."""

    resolved = sqlite_path.expanduser().resolve()
    if resolved.exists() and resolved.is_dir():
        raise ConfigError(f"Configured database path is a directory: {resolved}")

    parent = resolved.parent
    if not parent.exists():
        raise ConfigError(f"Database parent directory does not exist: {parent}")
    if not parent.is_dir():
        raise ConfigError(f"Database parent is not a directory: {parent}")
    if not os.access(parent, os.W_OK):
        raise ConfigError(f"Database parent directory is not writable: {parent}")
    return resolved
