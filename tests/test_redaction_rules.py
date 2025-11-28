"""Tests for rule-based redactions (AI-assisted by Codex GPT-5)."""

# pylint: disable=import-error,protected-access

from __future__ import annotations

import json
import unittest
from pathlib import Path

import pytest

from src.services.redaction_rules import (
    DEFAULT_REPLACEMENT,
    RuleOptions,
    RedactionRule,
    apply_rules,
    load_rules,
)

TC = unittest.TestCase()


def test_apply_rules_honors_order_and_counts() -> None:
    """Rules apply in order and produce per-rule counts with titles."""

    rules = [
        RedactionRule(
            id="emails",
            type="regex",
            pattern=r"[\w.-]+@[\w.-]+",
            options=RuleOptions(replacement="EMAIL"),
        ),
        RedactionRule(
            id="tokens",
            type="regex",
            pattern=r"token-[0-9]+",
        ),
    ]
    text = "Contact me at user@example.com with token-123 or token-456."
    redacted, summary = apply_rules(text, rules)

    TC.assertIn("EMAIL", redacted)
    TC.assertIn(DEFAULT_REPLACEMENT, redacted)
    TC.assertEqual(summary["tokens"]["count"], 2)


def test_literal_rule_matches_exact_text() -> None:
    """Literal rules should match exact text (case-sensitive when requested)."""

    rules = [
        RedactionRule(id="name", type="literal", pattern="Lauren"),
        RedactionRule(
            id="case_sensitive",
            type="literal",
            pattern="SECRET",
            options=RuleOptions(ignore_case=False),
        ),
    ]
    redacted, summary = apply_rules("Lauren keeps secret and SECRET", rules)

    TC.assertEqual(redacted, "<REDACTED> keeps secret and <REDACTED>")
    TC.assertEqual(summary["name"]["count"], 1)
    TC.assertEqual(summary["case_sensitive"]["count"], 1)


def test_marker_rule_replaces_inner_content() -> None:
    """Marker rules should redact only the enclosed content."""

    rule = RedactionRule(
        id="marker",
        type="marker",
        pattern=r"\[redact\s+(?P<content>.+?)\]",
        options=RuleOptions(dotall=True),
    )
    text = "Logs: [redact password=abc123] continue"
    redacted, summary = apply_rules(text, [rule])

    TC.assertEqual(redacted, "Logs: <REDACTED> continue")
    TC.assertEqual(summary["marker"]["count"], 1)


def test_disabled_rules_are_skipped() -> None:
    """Disabled rules should not apply."""

    rules = [
        RedactionRule(
            id="enabled",
            type="regex",
            pattern="secret",
        ),
        RedactionRule(
            id="disabled",
            type="regex",
            pattern="data",
            options=RuleOptions(enabled=False),
        ),
    ]
    redacted, summary = apply_rules("secret and data", rules)

    TC.assertEqual(redacted, "<REDACTED> and data")
    TC.assertNotIn("disabled", summary)


def test_load_rules_from_json_and_defaults(tmp_path: Path) -> None:
    """JSON rule files load and enforce overrides by ID."""

    rule_path = tmp_path / "rules.json"
    rule_path.write_text(
        json.dumps(
            [
                {
                    "id": "email",
                    "type": "regex",
                    "pattern": "override",
                    "enabled": False,
                },
                {
                    "id": "custom",
                    "type": "regex",
                    "pattern": "custom",
                },
            ]
        ),
        encoding="utf-8",
    )

    rules = load_rules(rule_path)
    rule_ids = [rule.id for rule in rules]

    TC.assertIn("email", rule_ids)
    TC.assertIn("custom", rule_ids)

    email_rule = next(rule for rule in rules if rule.id == "email")
    TC.assertFalse(email_rule.enabled)


def test_invalid_rule_fails_fast(tmp_path: Path) -> None:
    """Invalid entries should raise for visibility."""

    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps([{"title": "missing id"}]), encoding="utf-8")

    with pytest.raises(ValueError):
        load_rules(bad_path)


def test_load_rules_requires_id_and_pattern(tmp_path: Path) -> None:
    """Rules without required keys should raise."""

    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps([{"pattern": "x"}]), encoding="utf-8")

    with pytest.raises(ValueError):
        load_rules(bad_path)
