# Purpose: validate Codex session events before ingest processing.
# Author: Codex with Lauren Parlett
# Date: 2025-10-30
# Related tests: TBD (planned)
# AI-assisted: Generated with Codex (GPT-5).

"""Validators that ensure event payloads meet ingest expectations."""

from __future__ import annotations

from typing import Any


class EventValidationError(ValueError):
    """Raised when a session event is malformed."""


def validate_event(event: Any) -> dict[str, Any]:
    """Return a normalized event dict if validation succeeds.

    Validation guards downstream handlers from unexpected shapes. Only JSON
    objects with a string ``type`` and (optional) dict ``payload`` are allowed.
    """

    if not isinstance(event, dict):
        raise EventValidationError("Event must be a JSON object.")

    normalized: dict[str, Any] = dict(event)

    event_type = normalized.get("type")
    if not isinstance(event_type, str) or not event_type.strip():
        raise EventValidationError("Event 'type' must be a non-empty string.")

    timestamp = normalized.get("timestamp")
    if timestamp is not None and not isinstance(timestamp, str):
        raise EventValidationError(
            "Event 'timestamp' must be a string or null."
        )

    payload = normalized.get("payload")
    if payload is None:
        normalized["payload"] = {}
    elif isinstance(payload, dict):
        normalized["payload"] = dict(payload)
    else:
        raise EventValidationError("Event 'payload' must be a JSON object.")

    metadata = normalized.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        normalized["metadata"] = {}

    return normalized
