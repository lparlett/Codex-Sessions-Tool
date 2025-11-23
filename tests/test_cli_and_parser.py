"""Unit tests for CLI helpers and session parsing utilities."""

from __future__ import annotations

import argparse
from pathlib import Path

import unittest

import pytest

from cli import ingest_session
from cli import group_session
from src.parsers import session_parser
from src.services.config import ConfigError, SessionsConfig, load_config
from src.services.ingest import SessionSummary

TC = unittest.TestCase()


def test_resolve_runtime_options_debug_caps_limit() -> None:
    """Debug mode should cap limit at 2 and enable verbose."""
    args = argparse.Namespace(verbose=False, debug=True, limit=None)
    verbose, limit = ingest_session._resolve_runtime_options(args)  # pylint: disable=protected-access
    TC.assertTrue(verbose)
    TC.assertEqual(limit, 2)


def test_validate_db_path_rejects_missing_parent(tmp_path: Path) -> None:
    """validate_db_path should raise when parent folder is absent."""
    target = tmp_path / "missing_dir" / "session.sqlite"
    with pytest.raises(ConfigError):
        ingest_session.validate_db_path(target)


def test_print_error_details_renders_and_counts(capsys: pytest.CaptureFixture[str]) -> None:
    """_print_error_details should summarize a list of structured errors."""
    errors = [
        {"severity": "ERROR", "code": "bad", "message": "oops"},
        {"severity": "WARNING", "code": "warn", "message": "hmm"},
        {"severity": "ERROR", "code": "another", "message": "more"},
        {"severity": "ERROR", "code": "extra", "message": "extra"},
    ]
    count = ingest_session._print_error_details(errors, indent="")  # pylint: disable=protected-access
    captured = capsys.readouterr().out
    TC.assertEqual(count, 4)
    TC.assertIn("ERROR/bad: oops", captured)
    TC.assertIn("... 1 more", captured)


def test_report_many_results(capsys: pytest.CaptureFixture[str]) -> None:
    """_report_many_results should aggregate totals and print them."""
    summaries: list[SessionSummary] = [
        {
            "session_file": "file1.jsonl",
            "file_id": 1,
            "prompts": 0,
            "token_messages": 0,
            "turn_context_messages": 0,
            "agent_reasoning_messages": 0,
            "function_plan_messages": 0,
            "function_calls": 0,
            "errors": [{"severity": "ERROR", "code": "x", "message": "m"}],
        },
        {
            "session_file": "file2.jsonl",
            "file_id": 2,
            "prompts": 0,
            "token_messages": 0,
            "turn_context_messages": 0,
            "agent_reasoning_messages": 0,
            "function_plan_messages": 0,
            "function_calls": 0,
            "errors": [],
        },
    ]
    ingest_session._report_many_results(summaries, Path("db.sqlite"))  # pylint: disable=protected-access
    captured = capsys.readouterr().out
    TC.assertIn("Ingested: file1.jsonl", captured)
    TC.assertIn("Files processed: 2", captured)
    TC.assertIn("rows: 3", captured)  # total rows aggregated


def test_shorten_truncates_long_text() -> None:
    """shorten should ellipsize text exceeding the limit."""
    text = "a" * 10
    TC.assertEqual(group_session.shorten(text, limit=5), "aa...")


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
                {"type": "event_msg", "timestamp": "t2", "payload": {"type": "ai_response", "message": "Hey"}}  # noqa: E501
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
    config_file.write_text("[sessions]\nroot = \"./missing\"\n", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(config_file)
