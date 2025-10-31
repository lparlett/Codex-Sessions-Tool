"""Tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Generator
import unittest
from unittest.mock import patch
import pytest


from src.services.config import ConfigError, SessionsConfig, load_config


def test_load_config_missing_file() -> None:
    """Test that loading missing config file raises appropriate error."""
    with pytest.raises(ConfigError, match="Configuration file not found"):
        load_config(Path("nonexistent.toml"))


def test_load_config_invalid_toml() -> None:
    """Test that invalid TOML raises appropriate error."""
    mock_toml = "invalid [ toml"
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.read_text", return_value=mock_toml),
    ):
        with pytest.raises(ConfigError, match="not valid TOML"):
            load_config(Path("test.toml"))


def test_load_config_missing_sessions() -> None:
    """Test that missing [sessions] table raises appropriate error."""
    mock_toml = """
    [other]
    value = "test"
    """
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.read_text", return_value=mock_toml),
    ):
        with pytest.raises(ConfigError, match="Missing \\[sessions\\] table"):
            load_config(Path("test.toml"))


def test_load_config_missing_root() -> None:
    """Test that missing root setting raises appropriate error."""
    mock_toml = """
    [sessions]
    other = "value"
    """
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.read_text", return_value=mock_toml),
    ):
        with pytest.raises(ConfigError, match="requires 'root'"):
            load_config(Path("test.toml"))


@pytest.fixture(name="mock_path_exists")
def fixture_mock_path_exists() -> Generator[None, None, None]:
    """Mock Path.exists and Path.is_dir to return True."""
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.is_dir", return_value=True),
        patch("pathlib.Path.expanduser", return_value=Path("/mock/path")),
        patch("pathlib.Path.resolve", return_value=Path("/mock/path")),
    ):
        yield


def test_load_config_valid(
    mock_path_exists: None,
) -> None:  # pylint: disable=unused-argument
    """Test loading valid configuration."""
    test_case = unittest.TestCase()
    mock_toml = """
    [sessions]
    root = "~/sessions"

    [ingest]
    batch_size = 500
    """
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.read_text", return_value=mock_toml),
    ):
        config = load_config(Path("test.toml"))
        test_case.assertIsInstance(config, SessionsConfig)
        test_case.assertEqual(config.sessions_root, Path("/mock/path"))
        test_case.assertEqual(config.ingest_batch_size, 500)


def test_load_config_invalid_batch_size() -> None:
    """Test that invalid batch size raises appropriate error."""
    mock_toml = """
    [sessions]
    root = "~/sessions"

    [ingest]
    batch_size = -1
    """
    with (
        patch("pathlib.Path.exists", side_effect=[True, True]),
        patch("pathlib.Path.read_text", return_value=mock_toml),
        patch("pathlib.Path.expanduser", return_value=Path("/mock/sessions")),
        patch("pathlib.Path.resolve", return_value=Path("/mock/sessions")),
        patch("pathlib.Path.is_dir", return_value=True),
    ):
        with pytest.raises(ConfigError, match="must be a positive integer"):
            load_config(Path("test.toml"))


def test_load_config_default_batch_size(
    mock_path_exists: None,
) -> None:  # pylint: disable=unused-argument
    """Test that default batch size is used when not specified."""
    test_case = unittest.TestCase()
    mock_toml = """
    [sessions]
    root = "~/sessions"
    """
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.read_text", return_value=mock_toml),
    ):
        config = load_config(Path("test.toml"))
        test_case.assertEqual(config.ingest_batch_size, 1000)


def test_load_config_nonexistent_root() -> None:
    """Test that nonexistent root directory raises appropriate error."""
    mock_toml = """
    [sessions]
    root = "~/sessions"
    """
    with (
        patch("pathlib.Path.exists", side_effect=[True, False]),
        patch("pathlib.Path.read_text", return_value=mock_toml),
        patch("pathlib.Path.expanduser", return_value=Path("/mock/sessions")),
        patch("pathlib.Path.resolve", return_value=Path("/mock/sessions")),
    ):
        with pytest.raises(ConfigError, match="does not exist"):
            load_config(Path("test.toml"))


def test_load_config_root_not_directory() -> None:
    """Test that non-directory root raises appropriate error."""
    mock_toml = """
    [sessions]
    root = "~/sessions"
    """
    with (
        patch("pathlib.Path.exists", side_effect=[True, True]),
        patch("pathlib.Path.read_text", return_value=mock_toml),
        patch("pathlib.Path.expanduser", return_value=Path("/mock/sessions")),
        patch("pathlib.Path.resolve", return_value=Path("/mock/sessions")),
        patch("pathlib.Path.is_dir", return_value=False),
    ):
        with pytest.raises(ConfigError, match="is not a directory"):
            load_config(Path("test.toml"))
