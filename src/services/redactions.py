"""Redaction persistence helpers for prompts and related content.

Purpose: CRUD helpers for the ``redactions`` table (AI-assisted by Codex GPT-5).
Author: Codex with Lauren Parlett
Date: 2025-11-27
Related tests: tests/test_redactions.py
"""

from __future__ import annotations

from dataclasses import dataclass
from sqlite3 import Connection
from typing import Any, Iterable

ALLOWED_SCOPES: tuple[str, ...] = ("prompt", "field", "global")


@dataclass(frozen=True)
class RedactionCreate:
    """Input payload for creating a redaction record."""

    prompt_id: int | None
    scope: str
    replacement_text: str
    field_path: str | None = None
    reason: str | None = None
    actor: str | None = None


@dataclass(frozen=True)
class RedactionRecord:  # pylint: disable=too-many-instance-attributes
    """Represents a stored redaction row."""

    id: int
    prompt_id: int | None
    scope: str
    field_path: str | None
    replacement_text: str
    reason: str | None
    actor: str | None
    created_at: str
    updated_at: str | None


def create_redaction(conn: Connection, payload: RedactionCreate) -> int:
    """Insert a redaction row and return its id."""

    _validate_scope(payload.scope)
    _validate_field_path(payload.scope, payload.field_path)
    replacement = payload.replacement_text.strip()
    if not replacement:
        raise ValueError("replacement_text must be a non-empty string.")

    cursor = conn.execute(
        """
        INSERT INTO redactions (
            prompt_id,
            scope,
            field_path,
            replacement_text,
            reason,
            actor
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            payload.prompt_id,
            payload.scope,
            payload.field_path.strip() if payload.field_path else None,
            replacement,
            _normalize_optional(payload.reason),
            _normalize_optional(payload.actor),
        ),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("Failed to insert redaction row.")
    return int(cursor.lastrowid)


def get_redaction(conn: Connection, redaction_id: int) -> RedactionRecord | None:
    """Return a single redaction row by id."""

    cursor = conn.execute(
        """
        SELECT
            id,
            prompt_id,
            scope,
            field_path,
            replacement_text,
            reason,
            actor,
            created_at,
            updated_at
        FROM redactions
        WHERE id = ?
        """,
        (redaction_id,),
    )
    row = cursor.fetchone()
    return _row_to_record(row) if row else None


def list_redactions(
    conn: Connection,
    *,
    prompt_id: int | None = None,
    scope: str | None = None,
) -> list[RedactionRecord]:
    """Return redactions filtered by prompt or scope."""

    if scope is not None:
        _validate_scope(scope)

    query = """
        SELECT
            id,
            prompt_id,
            scope,
            field_path,
            replacement_text,
            reason,
            actor,
            created_at,
            updated_at
        FROM redactions
        WHERE (? IS NULL OR prompt_id = ?)
          AND (? IS NULL OR scope = ?)
        ORDER BY created_at DESC, id DESC
    """
    params: tuple[Any, ...] = (prompt_id, prompt_id, scope, scope)
    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    return [_row_to_record(row) for row in rows]


# pylint: disable=too-many-arguments
def update_redaction(
    conn: Connection,
    redaction_id: int,
    *,
    prompt_id: int | None = None,
    scope: str | None = None,
    field_path: str | None = None,
    replacement_text: str | None = None,
    reason: str | None = None,
    actor: str | None = None,
) -> bool:
    """Update a redaction row; returns True when a row was changed."""

    assignments: list[str] = []
    params: list[Any] = []

    if prompt_id is not None:
        assignments.append("prompt_id = ?")
        params.append(prompt_id)
    if scope is not None:
        _validate_scope(scope)
        assignments.append("scope = ?")
        params.append(scope)
    if field_path is not None:
        _validate_field_path(scope or "prompt", field_path)
        assignments.append("field_path = ?")
        params.append(field_path.strip() or None)
    if replacement_text is not None:
        replacement = replacement_text.strip()
        if not replacement:
            raise ValueError("replacement_text must be a non-empty string.")
        assignments.append("replacement_text = ?")
        params.append(replacement)
    if reason is not None:
        assignments.append("reason = ?")
        params.append(_normalize_optional(reason))
    if actor is not None:
        assignments.append("actor = ?")
        params.append(_normalize_optional(actor))

    if not assignments:
        return False

    assignments.append("updated_at = CURRENT_TIMESTAMP")
    params.append(redaction_id)
    set_clause = ", ".join(assignments)
    # Bandit B608: assignments are constructed from vetted columns only.
    query = "UPDATE redactions SET " + set_clause + " WHERE id = ?"  # nosec B608
    cursor = conn.execute(query, tuple(params))
    return cursor.rowcount > 0


def delete_redaction(conn: Connection, redaction_id: int) -> bool:
    """Delete a redaction row by id."""

    cursor = conn.execute("DELETE FROM redactions WHERE id = ?", (redaction_id,))
    return cursor.rowcount > 0


def _row_to_record(row: Iterable[Any]) -> RedactionRecord:
    """Convert a DB row to a RedactionRecord."""

    (
        row_id,
        prompt_id,
        scope,
        field_path,
        replacement_text,
        reason,
        actor,
        created_at,
        updated_at,
    ) = row
    return RedactionRecord(
        id=int(row_id),
        prompt_id=int(prompt_id) if prompt_id is not None else None,
        scope=str(scope),
        field_path=str(field_path) if field_path is not None else None,
        replacement_text=str(replacement_text),
        reason=str(reason) if reason is not None else None,
        actor=str(actor) if actor is not None else None,
        created_at=str(created_at),
        updated_at=str(updated_at) if updated_at is not None else None,
    )


def _validate_scope(scope: str) -> None:
    """Ensure scope is known to prevent injection in CRUD helpers."""

    if scope not in ALLOWED_SCOPES:
        raise ValueError(f"Invalid scope '{scope}'. Allowed scopes: {ALLOWED_SCOPES}")


def _validate_field_path(scope: str, field_path: str | None) -> None:
    """Require field_path when operating on field-level redactions."""

    if field_path is not None and not field_path.strip():
        raise ValueError("field_path cannot be blank when provided.")
    if scope == "field" and not field_path:
        raise ValueError("field_path is required when scope='field'.")


def _normalize_optional(value: str | None) -> str | None:
    """Return a trimmed optional string or None."""

    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None
