"""Tests for configuration loading and validation."""

from __future__ import annotations

import unittest
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from src.services.config import ConfigError, SessionsConfig, load_config

# pylint: disable=too-many-locals,duplicate-code


def test_load_config_missing_file() -> None:
    """Test that loading missing config file raises appropriate error."""
    test_case = unittest.TestCase()
    with test_case.assertRaises(ConfigError) as cm:
        load_config(Path("nonexistent.toml"))
    test_case.assertIn("not found", str(cm.exception))


def mock_read_text(content: str) -> object:
    """Create a read_text lambda that supports encoding parameter."""
    return lambda _, encoding=None: content


def mock_path_attrs(mp: MonkeyPatch, exists: bool = True, is_dir: bool = True) -> None:
    """Set up common Path attribute mocks."""
    mp.setattr(Path, "exists", lambda _: exists)
    mp.setattr(Path, "is_dir", lambda _: is_dir)
    mp.setattr(Path, "expanduser", lambda _: Path("/test"))
    mp.setattr(Path, "resolve", lambda _: Path("/test"))


def test_load_config_invalid_toml() -> None:
    """Test that invalid TOML raises appropriate error."""
    test_case = unittest.TestCase()
    mock_toml = "invalid [ toml"

    with MonkeyPatch().context() as mp:
        mock_path_attrs(mp)
        mp.setattr(Path, "read_text", mock_read_text(mock_toml))

        with test_case.assertRaises(ConfigError) as cm:
            load_config(Path("test.toml"))
        test_case.assertIn("TOML", str(cm.exception))


def test_load_config_missing_sessions() -> None:
    """Test that missing [sessions] table raises appropriate error."""
    test_case = unittest.TestCase()
    mock_toml = """
    [other]
    value = "test"
    """

    with MonkeyPatch().context() as mp:
        mock_path_attrs(mp)
        mp.setattr(Path, "read_text", mock_read_text(mock_toml))

        with test_case.assertRaises(ConfigError) as cm:
            load_config(Path("test.toml"))
        test_case.assertIn("sessions", str(cm.exception))


def test_load_config_missing_root() -> None:
    """Test that missing root setting raises appropriate error."""
    test_case = unittest.TestCase()
    mock_toml = """
    [sessions]
    other = "value"
    """

    with MonkeyPatch().context() as mp:
        mock_path_attrs(mp)
        mp.setattr(Path, "read_text", mock_read_text(mock_toml))

        with test_case.assertRaises(ConfigError) as cm:
            load_config(Path("test.toml"))
        test_case.assertIn("root", str(cm.exception))


def test_load_config_valid(tmp_path: Path) -> None:
    """Test loading valid configuration."""
    test_case = unittest.TestCase()
    mock_toml = """
    [sessions]
    root = "~/sessions"

    [ingest]
    batch_size = 500
    """

    with MonkeyPatch().context() as mp:
        # Set up path attributes with tmp_path
        mp.setattr(Path, "exists", lambda _: True)
        mp.setattr(Path, "read_text", mock_read_text(mock_toml))
        mp.setattr(Path, "expanduser", lambda _: tmp_path)
        mp.setattr(Path, "resolve", lambda _: tmp_path)
        mp.setattr(Path, "is_dir", lambda _: True)

        config = load_config(Path("test.toml"))
        test_case.assertIsInstance(config, SessionsConfig)
        test_case.assertEqual(config.sessions_root, tmp_path)
        test_case.assertEqual(config.ingest_batch_size, 500)


def test_load_config_invalid_batch_size() -> None:
    """Test that invalid batch size raises appropriate error."""
    test_case = unittest.TestCase()
    mock_toml = """
    [sessions]
    root = "~/sessions"

    [ingest]
    batch_size = -1
    """

    with MonkeyPatch().context() as mp:
        mock_path_attrs(mp)
        mp.setattr(Path, "read_text", mock_read_text(mock_toml))

        with test_case.assertRaises(ConfigError) as cm:
            load_config(Path("test.toml"))
        test_case.assertIn("batch_size", str(cm.exception))


def test_load_config_default_batch_size() -> None:
    """Test that default batch size is used when not specified."""
    test_case = unittest.TestCase()
    mock_toml = """
    [sessions]
    root = "~/sessions"
    """

    with MonkeyPatch().context() as mp:
        mock_path_attrs(mp)
        mp.setattr(Path, "read_text", mock_read_text(mock_toml))
        config = load_config(Path("test.toml"))
        test_case.assertEqual(config.ingest_batch_size, 1000)


def test_load_config_nonexistent_root(tmp_path: Path) -> None:
    """Test that nonexistent root directory raises appropriate error."""
    mock_toml = """
    [sessions]
    root = "~/sessions"
    """
    with MonkeyPatch().context() as mp:
        mp.setattr(
            Path, "exists", lambda p: str(p) == "test.toml"
        )  # Only config file exists
        mp.setattr(Path, "read_text", mock_read_text(mock_toml))
        mp.setattr(Path, "expanduser", lambda _: tmp_path / "nonexistent")
        mp.setattr(Path, "resolve", lambda s: s)

        with pytest.raises(ConfigError, match="does not exist"):
            load_config(Path("test.toml"))


def test_load_config_root_not_directory() -> None:
    """Test that non-directory root raises appropriate error."""
    mock_toml = """
    [sessions]
    root = "~/sessions"
    """
    with MonkeyPatch().context() as mp:
        mock_path_attrs(mp, is_dir=False)  # Root path exists but is not a directory
        mp.setattr(Path, "read_text", mock_read_text(mock_toml))

        with pytest.raises(ConfigError, match="is not a directory"):
            load_config(Path("test.toml"))
