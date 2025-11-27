"""Tests for validation and sanitization helpers."""

# pylint: disable=duplicate-code,import-error

from __future__ import annotations

import unittest

import pytest

from src.services.validation import validate_event, EventValidationError
from src.services.sanitization import sanitize_json, REDACTED

TC = unittest.TestCase()


def test_validate_event_normalizes_payload() -> None:
    """validate_event should coerce payload to dict and preserve fields."""
    event = {"type": "event_msg", "timestamp": "2025-10-31T10:00:00Z"}
    normalized = validate_event(event)
    TC.assertEqual(normalized["payload"], {})
    TC.assertEqual(normalized["type"], "event_msg")


@pytest.mark.parametrize(
    "bad_event",
    [
        "not-a-dict",
        {"type": "", "timestamp": "x"},
        {"type": "event_msg", "timestamp": 1},
        {"type": "event_msg", "payload": "not-dict"},
    ],
)
def test_validate_event_rejects_bad_inputs(bad_event: object) -> None:
    """validate_event should raise EventValidationError on invalid shapes."""
    with pytest.raises(EventValidationError):
        validate_event(bad_event)


def test_sanitize_json_redacts_sensitive_values() -> None:
    """sanitize_json should redact keys and secret-looking strings."""
    payload = {
        "access_token": "secret-token",
        "nested": {"password": "p@ss"},
        "tuple": ("apikey",),
        "string_secret": "sk-abcdef1234567890",
        "safe": "hello",
    }
    sanitized = sanitize_json(payload)
    TC.assertEqual(sanitized["access_token"], REDACTED)
    TC.assertEqual(sanitized["nested"]["password"], REDACTED)
    TC.assertEqual(sanitized["string_secret"], REDACTED)
    TC.assertEqual(sanitized["safe"], "hello")


def test_sanitize_json_handles_false_negatives_and_casing() -> None:
    """Sanitization should catch heuristics and case-insensitive sensitive keys."""

    payload = {
        "Authorization": "Bearer abc123",
        "api_key_backup": "short-token-123",
        "unicode_secret": "sk-ßeta-secret",
        "custom": "uuidlike-1234-5678-9012-3456",
    }
    sanitized = sanitize_json(payload)
    TC.assertEqual(sanitized["Authorization"], REDACTED)
    TC.assertEqual(sanitized["api_key_backup"], "short-token-123")
    TC.assertEqual(sanitized["unicode_secret"], REDACTED)
    TC.assertEqual(sanitized["custom"], "uuidlike-1234-5678-9012-3456")


def test_sanitize_json_with_missing_markers() -> None:
    """Secrets that don't match heuristics should remain unchanged."""

    payload = {"note": "short-token", "uuid": "12345678-1234-1234-1234-123456789012"}
    sanitized = sanitize_json(payload)
    TC.assertEqual(sanitized, payload)


def test_validate_event_defaults_payload_and_metadata() -> None:
    """validate_event should default payload/metadata when missing."""

    event = {"type": "event_msg", "timestamp": "t1", "metadata": None}
    normalized = validate_event(event)
    TC.assertEqual(normalized["payload"], {})
    TC.assertIsNone(normalized.get("metadata"))


def test_validate_event_roundtrip_structure() -> None:
    """validate_event should preserve fields and allow revalidation."""

    event = {
        "type": "event_msg",
        "timestamp": "t2",
        "payload": {"type": "agent_message", "text": "hi"},
        "metadata": {"source": "cli"},
    }
    normalized = validate_event(event)
    normalized_again = validate_event(normalized)
    TC.assertEqual(normalized_again["metadata"], {"source": "cli"})
    TC.assertEqual(normalized_again["payload"]["type"], "agent_message")
