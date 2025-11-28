"""Tests for session_parser helper functions (AI-assisted by Codex GPT-5)."""

# pylint: disable=import-error

from __future__ import annotations

import unittest
from typing import Any
from pathlib import Path

import pytest

from src.parsers import session_parser
from src.parsers.session_parser import group_by_user_messages

TC = unittest.TestCase()


def test_group_by_user_messages_splits_prelude_and_multiple_groups() -> None:
    """Group events around user messages and preserve prelude."""

    events = [
        {"type": "session_meta", "payload": {"id": "s1"}},
        {"type": "event_msg", "payload": {"type": "user_message", "message": "First"}},
        {"type": "event_msg", "payload": {"type": "agent_message", "message": "A1"}},
        {"type": "response_item", "payload": {"type": "message", "text": "B1"}},
        {"type": "event_msg", "payload": {"type": "user_message", "message": "Second"}},
        {"type": "event_msg", "payload": {"type": "agent_message", "message": "A2"}},
    ]

    prelude, groups = group_by_user_messages(events)

    TC.assertEqual(len(prelude), 1)
    TC.assertEqual(len(groups), 2)

    first_group = groups[0]
    second_group = groups[1]

    TC.assertEqual(first_group["user"]["payload"]["message"], "First")
    TC.assertEqual(len(first_group["events"]), 2)
    TC.assertEqual(second_group["user"]["payload"]["message"], "Second")
    TC.assertEqual(len(second_group["events"]), 1)


def test_group_by_user_messages_handles_missing_payloads() -> None:
    """Non-dict payloads should be treated as non-user events and go to prelude."""

    events: list[dict[str, Any]] = [
        {"type": None, "payload": "not-a-dict"},
        {"type": "event_msg", "payload": "still-not-a-dict"},
        {"type": "event_msg", "payload": {"type": "user_message", "message": "Go"}},
        {"type": "turn_context", "payload": {"cwd": "/workspace"}},
        {"payload": {"type": "agent_message", "message": "missing type"}},
    ]

    prelude, groups = group_by_user_messages(events)

    TC.assertIn({"type": None, "payload": "not-a-dict"}, prelude)
    TC.assertIn({"type": "event_msg", "payload": "still-not-a-dict"}, prelude)
    TC.assertEqual(len(groups), 1)
    TC.assertEqual(groups[0]["user"]["payload"]["message"], "Go")
    TC.assertEqual(groups[0]["events"][0]["type"], "turn_context")


def test_group_by_user_messages_handles_empty_events_list() -> None:
    """Empty event list should return empty prelude and groups."""

    prelude, groups = group_by_user_messages([])
    TC.assertEqual(prelude, [])
    TC.assertEqual(groups, [])


def test_load_session_events_handles_trailing_partial_json(tmp_path: Path) -> None:
    """load_session_events should fail on malformed JSON lines."""

    log_file = tmp_path / "bad.jsonl"
    log_file.write_text('{"ok": true}\n{"incomplete": ', encoding="utf-8")
    with pytest.raises(ValueError):
        session_parser.load_session_events(log_file)
