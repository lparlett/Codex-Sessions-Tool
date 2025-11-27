"""Unit tests for CLI helpers and session parsing utilities."""

# pylint: disable=import-error,protected-access

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

import unittest

import pytest

from cli import ingest_session
from cli import group_session
from src.parsers import session_parser
from src.services import ingest
from src.services.config import ConfigError, SessionsConfig, load_config
from src.services.ingest import SessionSummary

TC = unittest.TestCase()


def _write_cli_config(tmp_path: Path) -> tuple[Path, Path]:
    """Write a minimal config file and return its path and db path."""

    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    db_path = reports_dir / "session.sqlite"

    config_file = tmp_path / "config.toml"
    config_file.write_text(
        textwrap.dedent(
            f"""
            [sessions]
            root = "{sessions_root.as_posix()}"

            [ingest]
            db_path = "{db_path.as_posix()}"

            [outputs]
            reports_dir = "{reports_dir.as_posix()}"
            """
        ),
        encoding="utf-8",
    )
    return config_file, db_path.resolve()


def test_resolve_runtime_options_debug_caps_limit() -> None:
    """Debug mode should cap limit at 2 and enable verbose."""
    args = argparse.Namespace(verbose=False, debug=True, limit=None)
    verbose, limit = ingest_session._resolve_runtime_options(
        args
    )  # pylint: disable=protected-access
    TC.assertTrue(verbose)
    TC.assertEqual(limit, 2)


def test_validate_db_path_rejects_missing_parent(tmp_path: Path) -> None:
    """validate_db_path should raise when parent folder is absent."""
    target = tmp_path / "missing_dir" / "session.sqlite"
    with pytest.raises(ConfigError):
        ingest_session.validate_db_path(target)


def test_print_error_details_renders_and_counts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """_print_error_details should summarize a list of structured errors."""
    errors = [
        {"severity": "ERROR", "code": "bad", "message": "oops"},
        {"severity": "WARNING", "code": "warn", "message": "hmm"},
        {"severity": "ERROR", "code": "another", "message": "more"},
        {"severity": "ERROR", "code": "extra", "message": "extra"},
    ]
    count = ingest_session._print_error_details(
        errors, indent=""
    )  # pylint: disable=protected-access
    captured = capsys.readouterr().out
    TC.assertEqual(count, 4)
    TC.assertIn("ERROR/bad: oops", captured)
    TC.assertIn("... 1 more", captured)


def test_report_many_results(capsys: pytest.CaptureFixture[str]) -> None:
    """_report_many_results should aggregate totals and print them."""
    s1: SessionSummary = (
        ingest._create_empty_summary(  # pylint: disable=protected-access
            Path("file1.jsonl"), 1
        )
    )
    s1["errors"] = [{"severity": "ERROR", "code": "x", "message": "m"}]
    s2: SessionSummary = (
        ingest._create_empty_summary(  # pylint: disable=protected-access
            Path("file2.jsonl"), 2
        )
    )
    summaries: list[SessionSummary] = [s1, s2]
    ingest_session._report_many_results(
        summaries, Path("db.sqlite")
    )  # pylint: disable=protected-access
    captured = capsys.readouterr().out
    TC.assertIn("Ingested: file1.jsonl", captured)
    TC.assertIn("Ingested: file2.jsonl", captured)
    TC.assertIn("Files processed: 2", captured)
    TC.assertIn("errors: 1", captured)


def test_shorten_truncates_long_text() -> None:
    """shorten should ellipsize text exceeding the limit."""
    text = "a" * 10
    TC.assertEqual(group_session.shorten(text, limit=5), "aa...")


def test_shorten_handles_whitespace_and_zero_limit() -> None:
    """shorten should handle whitespace-only and small/zero limits safely."""

    TC.assertEqual(group_session.shorten("   "), "")
    TC.assertEqual(group_session.shorten("abc", limit=0), "...")
    TC.assertEqual(group_session.shorten("abc", limit=2), "ab...")


def test_describe_event_handles_message_payload() -> None:
    """describe_event should include payload type and timestamp."""
    event = {
        "type": "event_msg",
        "timestamp": "2025-10-31T10:00:00Z",
        "payload": {"type": "agent_message", "message": "Hello world"},
    }
    desc = group_session.describe_event(event)
    TC.assertIn("event_msg (agent_message) @ 2025-10-31T10:00:00Z", desc)
    TC.assertIn("Hello world", desc)


def test_render_prelude_and_groups(capsys: pytest.CaptureFixture[str]) -> None:
    """_render_groups should handle empty and populated groups."""
    captured: list[str] = []
    # no groups path
    group_session._render_groups([], captured)  # pylint: disable=protected-access
    TC.assertIn("No user messages found", captured[-1])

    # populated path
    captured.clear()
    groups = [
        {
            "user": {"timestamp": "t1", "payload": {"message": "Hi"}},
            "events": [
                {
                    "type": "event_msg",
                    "timestamp": "t2",
                    "payload": {"type": "ai_response", "message": "Hey"},
                }  # noqa: E501
            ],
        }
    ]
    group_session._render_groups(groups, captured)  # pylint: disable=protected-access
    out = capsys.readouterr().out
    TC.assertIn("Prompt 1", out)
    TC.assertIn("ai_response", out)


def test_group_by_user_messages_splits_prelude_and_groups() -> None:
    """Ensure grouping yields prelude and grouped events correctly."""
    events = [
        {"type": "session_meta", "payload": {}},
        {"type": "event_msg", "payload": {"type": "user_message", "message": "Hi"}},
        {"type": "event_msg", "payload": {"type": "ai_response", "message": "Hello"}},
    ]
    prelude, groups = session_parser.group_by_user_messages(events)
    TC.assertEqual(len(prelude), 1)
    TC.assertEqual(len(groups), 1)
    TC.assertEqual(groups[0]["user"]["payload"]["message"], "Hi")
    TC.assertEqual(groups[0]["events"][0]["payload"]["message"], "Hello")


def test_describe_response_item_branches() -> None:
    """_describe_payload should render response and function call details."""
    payload = {
        "type": "response_item",
        "timestamp": "t1",
        "payload": {"type": "function_call_output", "output": "done"},
    }
    desc = group_session.describe_event(payload)
    TC.assertTrue("function_call_output" in desc or "output" in desc)


def test_find_first_session_file_returns_earliest(tmp_path: Path) -> None:
    """find_first_session_file should select the earliest file by path order."""
    # create nested structure year/month/day with files
    day1 = tmp_path / "2024" / "01" / "01"
    day2 = tmp_path / "2024" / "02" / "01"
    for path in (day1, day2):
        path.mkdir(parents=True, exist_ok=True)
    first = day1 / "a.jsonl"
    second = day2 / "b.jsonl"
    first.write_text("{}", encoding="utf-8")
    second.write_text("{}", encoding="utf-8")

    found = session_parser.find_first_session_file(tmp_path)
    TC.assertEqual(found, first)


def test_find_first_session_file_raises_when_empty(tmp_path: Path) -> None:
    """find_first_session_file should raise when no files exist."""

    (tmp_path / "2024" / "01" / "01").mkdir(parents=True, exist_ok=True)
    with pytest.raises(session_parser.SessionDiscoveryError):
        session_parser.find_first_session_file(tmp_path)


def test_load_session_events_raises_on_bad_json(tmp_path: Path) -> None:
    """load_session_events should raise ValueError when JSON is invalid."""
    log_file = tmp_path / "bad.jsonl"
    log_file.write_text('{"ok": true}\n{bad json}\n', encoding="utf-8")

    with pytest.raises(ValueError):
        session_parser.load_session_events(log_file)


def test_iter_session_files_yields_all(tmp_path: Path) -> None:
    """iter_session_files should walk nested date directories in order."""
    day = tmp_path / "2025" / "01" / "02"
    day.mkdir(parents=True)
    file1 = day / "a.jsonl"
    file2 = day / "b.jsonl"
    file1.write_text("", encoding="utf-8")
    file2.write_text("", encoding="utf-8")

    files = list(session_parser.iter_session_files(tmp_path))
    TC.assertEqual(files, [file1, file2])


def test_load_config_honors_batch_override(tmp_path: Path) -> None:
    """load_config should parse TOML and apply ingest batch size override."""
    config_dir = tmp_path / "user"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"
    config_file.write_text(
        '[sessions]\nroot = "."\n[ingest]\nbatch_size = 50\n',
        encoding="utf-8",
    )

    # ensure cwd so load_config finds file via explicit path
    cfg = ingest_session.load_config(config_file)  # reuse to exercise wrapper
    TC.assertIsInstance(cfg, SessionsConfig)
    TC.assertEqual(cfg.ingest_batch_size, 50)


def test_load_config_invalid_root(tmp_path: Path) -> None:
    """load_config should raise when sessions.root is missing."""
    config_dir = tmp_path / "user"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"
    config_file.write_text('[sessions]\nroot = "./missing"\n', encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(config_file)


def test_resolve_database_path_defaults_to_config(tmp_path: Path) -> None:
    """_resolve_database_path should fall back to config when CLI is None."""

    config_file, db_path = _write_cli_config(tmp_path)
    config = load_config(config_file)

    resolved = (
        ingest_session._resolve_database_path(  # pylint: disable=protected-access
            None, config
        )
    )
    TC.assertEqual(resolved, db_path)


def test_resolve_database_path_prefers_cli_override(tmp_path: Path) -> None:
    """_resolve_database_path should honor CLI override when provided."""

    config_file, _ = _write_cli_config(tmp_path)
    config = load_config(config_file)

    override_dir = tmp_path / "override"
    override_dir.mkdir()
    override_path = override_dir / "override.sqlite"

    resolved = (
        ingest_session._resolve_database_path(  # pylint: disable=protected-access
            override_path, config
        )
    )
    TC.assertEqual(resolved, override_path.resolve())


def test_describe_event_token_and_turn_context(tmp_path: Path) -> None:
    """describe_event should cover token_count and turn_context payloads."""

    token_event = {
        "type": "event_msg",
        "timestamp": "t0",
        "payload": {
            "type": "token_count",
            "rate_limits": {
                "primary": {"used_percent": 10, "window_minutes": 60, "resets_at": 123}
            },
        },
    }
    desc = group_session.describe_event(token_event)
    TC.assertIn("primary", desc)
    TC.assertIn("10%", desc)

    turn_ctx_event = {
        "type": "turn_context",
        "timestamp": "t1",
        "payload": {"cwd": str(tmp_path / "work")},
    }
    ctx_desc = group_session.describe_event(turn_ctx_event)
    work_path = str(tmp_path / "work")
    TC.assertIn(f"cwd: {work_path}", ctx_desc)


def test_render_prelude_and_prompt_group_empty_events(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Prelude rendering and empty group events should be printed and captured."""

    prelude = [
        {
            "type": "event_msg",
            "timestamp": "t0",
            "payload": {"type": "agent_message", "message": "Prelude hello"},
        }
    ]
    captured: list[str] = []
    group_session._render_prelude(prelude, captured)  # pylint: disable=protected-access
    out = capsys.readouterr().out
    TC.assertIn("-- Session Prelude --", out)
    TC.assertIn("Prelude hello", out)

    captured.clear()
    group = {
        "user": {"timestamp": "t1", "payload": {"message": "Hi there"}},
        "events": [],
    }
    group_session._render_prompt_group(
        1, group, captured
    )  # pylint: disable=protected-access
    out = capsys.readouterr().out
    TC.assertIn("Prompt 1", out)
    TC.assertIn("No subsequent events recorded.", out)


def test_describe_event_handles_unknown_payloads() -> None:
    """describe_event should degrade gracefully on missing/unknown payload types."""

    unknown_payload = {"type": "event_msg", "timestamp": "t0", "payload": {}}
    desc_unknown = group_session.describe_event(unknown_payload)
    TC.assertIn("event_msg", desc_unknown)

    missing_payload = {"type": "turn_context", "timestamp": "t1"}
    desc_missing = group_session.describe_event(missing_payload)
    TC.assertIn("turn_context", desc_missing)

    none_payload = {"type": "event_msg", "timestamp": "t2", "payload": None}
    desc_none = group_session.describe_event(none_payload)
    TC.assertIn("event_msg", desc_none)
