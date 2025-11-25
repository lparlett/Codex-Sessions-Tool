# pylint: disable=import-error
"""Tests for configuration loading and validation."""

from __future__ import annotations

import textwrap
import unittest
from pathlib import Path

import pytest

from src.services.config import ConfigError, SessionsConfig, load_config

TC = unittest.TestCase()


def _write_config(tmp_path: Path, body: str) -> Path:
    """Write TOML content to a temporary config file."""

    config_path = tmp_path / "config.toml"
    config_path.write_text(textwrap.dedent(body), encoding="utf-8")
    return config_path


def _path_for_toml(path: Path) -> str:
    """Return a path string safe for TOML (use forward slashes)."""

    return path.as_posix()


def test_load_config_missing_file() -> None:
    """Test that loading missing config file raises appropriate error."""

    with pytest.raises(ConfigError, match="not found"):
        load_config(Path("nonexistent.toml"))


def test_load_config_invalid_toml(tmp_path: Path) -> None:
    """Test that invalid TOML raises appropriate error."""

    config_path = _write_config(tmp_path, "invalid [ toml")
    with pytest.raises(ConfigError, match="TOML"):
        load_config(config_path)


def test_load_config_missing_sessions(tmp_path: Path) -> None:
    """Test that missing [sessions] table raises appropriate error."""

    config_path = _write_config(
        tmp_path,
        """
        [other]
        value = "test"
        """,
    )
    with pytest.raises(ConfigError, match="sessions"):
        load_config(config_path)


def test_load_config_missing_root(tmp_path: Path) -> None:
    """Test that missing root setting raises appropriate error."""

    config_path = _write_config(
        tmp_path,
        """
        [sessions]
        other = "value"
        """,
    )
    with pytest.raises(ConfigError, match="root"):
        load_config(config_path)


def test_load_config_valid(tmp_path: Path) -> None:
    """Test loading valid configuration with explicit paths."""

    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    sqlite_path = reports_dir / "session.sqlite"

    config_path = _write_config(
        tmp_path,
        f"""
        [sessions]
        root = "{_path_for_toml(sessions_root)}"

        [ingest]
        batch_size = 500
        db_path = "{_path_for_toml(sqlite_path)}"

        [outputs]
        reports_dir = "{_path_for_toml(reports_dir)}"
        """,
    )

    config = load_config(config_path)
    TC.assertIsInstance(config, SessionsConfig)
    TC.assertEqual(config.sessions_root, sessions_root.resolve())
    TC.assertEqual(config.ingest_batch_size, 500)
    TC.assertEqual(config.database.sqlite_path, sqlite_path.resolve())
    TC.assertEqual(config.outputs.reports_dir, reports_dir.resolve())


def test_load_config_invalid_batch_size(tmp_path: Path) -> None:
    """Test that invalid batch size raises appropriate error."""

    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    db_path_value = reports_dir / "db.sqlite"
    config_path = _write_config(
        tmp_path,
        f"""
        [sessions]
        root = "{_path_for_toml(sessions_root)}"

        [ingest]
        batch_size = -1
        db_path = "{_path_for_toml(db_path_value)}"

        [outputs]
        reports_dir = "{_path_for_toml(reports_dir)}"
        """,
    )

    with pytest.raises(ConfigError, match="batch_size"):
        load_config(config_path)


def test_load_config_default_batch_size(tmp_path: Path) -> None:
    """Test that default batch size is used when not specified."""

    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    config_path = _write_config(
        tmp_path,
        f"""
        [sessions]
        root = "{_path_for_toml(sessions_root)}"

        [outputs]
        reports_dir = "{_path_for_toml(reports_dir)}"
        """,
    )

    config = load_config(config_path)
    TC.assertEqual(config.ingest_batch_size, 1000)


def test_load_config_nonexistent_root(tmp_path: Path) -> None:
    """Test that nonexistent root directory raises appropriate error."""

    missing_root = tmp_path / "missing"
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    config_path = _write_config(
        tmp_path,
        f"""
        [sessions]
        root = "{_path_for_toml(missing_root)}"

        [outputs]
        reports_dir = "{_path_for_toml(reports_dir)}"
        """,
    )

    with pytest.raises(ConfigError, match="does not exist"):
        load_config(config_path)


def test_load_config_root_not_directory(tmp_path: Path) -> None:
    """Test that non-directory root raises appropriate error."""

    fake_root = tmp_path / "not_a_dir.txt"
    fake_root.write_text("content", encoding="utf-8")

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    config_path = _write_config(
        tmp_path,
        f"""
        [sessions]
        root = "{_path_for_toml(fake_root)}"

        [outputs]
        reports_dir = "{_path_for_toml(reports_dir)}"
        """,
    )

    with pytest.raises(ConfigError, match="not a directory"):
        load_config(config_path)


def test_load_config_invalid_db_parent(tmp_path: Path) -> None:
    """Test that database path with missing parent raises clear error."""

    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    db_path = tmp_path / "nope" / "db.sqlite"
    config_path = _write_config(
        tmp_path,
        f"""
        [sessions]
        root = "{_path_for_toml(sessions_root)}"

        [ingest]
        db_path = "{_path_for_toml(db_path)}"

        [outputs]
        reports_dir = "{_path_for_toml(reports_dir)}"
        """,
    )

    with pytest.raises(ConfigError, match="parent directory does not exist"):
        load_config(config_path)


def test_load_config_reports_dir_missing(tmp_path: Path) -> None:
    """Test that missing reports directory triggers validation error."""

    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()

    missing_reports = tmp_path / "missing_reports"
    config_path = _write_config(
        tmp_path,
        f"""
        [sessions]
        root = "{_path_for_toml(sessions_root)}"

        [outputs]
        reports_dir = "{_path_for_toml(missing_reports)}"
        """,
    )

    with pytest.raises(ConfigError, match="does not exist"):
        load_config(config_path)
