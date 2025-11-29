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
    rule_id: str | None
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
    rule_id: str | None
    scope: str
    field_path: str | None
    replacement_text: str
    reason: str | None
    actor: str | None
    active: bool
    created_at: str
    updated_at: str | None


def create_redaction(conn: Connection, payload: RedactionCreate) -> int:
    """Insert a redaction row and return its id."""

    _validate_scope(payload.scope)
    _validate_field_path(payload.scope, payload.field_path)
    replacement = payload.replacement_text.strip()
    if not replacement:
        raise ValueError("replacement_text must be a non-empty string.")

    cursor = _execute(
        conn,
        """
        INSERT INTO redactions (
            prompt_id,
            rule_id,
            scope,
            field_path,
            replacement_text,
            reason,
            actor
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.prompt_id,
            payload.rule_id,
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

    cursor = _execute(
        conn,
        """
        SELECT
            id,
            prompt_id,
            rule_id,
            scope,
            field_path,
            replacement_text,
            reason,
            actor,
            active,
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
            rule_id,
            scope,
            field_path,
            replacement_text,
            reason,
            actor,
            active,
            created_at,
            updated_at
        FROM redactions
        WHERE (? IS NULL OR prompt_id = ?)
          AND (? IS NULL OR scope = ?)
          AND active = ?
        ORDER BY created_at DESC, id DESC
    """
    params: tuple[Any, ...] = (prompt_id, prompt_id, scope, scope, 1)
    cursor = _execute(conn, query, params)
    rows = cursor.fetchall()
    return [_row_to_record(row) for row in rows]


# pylint: disable=too-many-arguments
# pylint: disable=too-many-locals
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
    rule_id: str | None = None,
    active: bool | None = None,
) -> bool:
    """Update a redaction row; returns True when a row was changed."""

    assignments, params = _collect_update_fields(
        prompt_id=prompt_id,
        scope=scope,
        field_path=field_path,
        replacement_text=replacement_text,
        reason=reason,
        actor=actor,
        rule_id=rule_id,
        active=active,
    )
    if not assignments:
        return False

    assignments.append("updated_at = CURRENT_TIMESTAMP")
    params.append(redaction_id)
    set_clause = ", ".join(assignments)
    # Bandit B608: assignments are constructed from vetted columns only.
    query = "UPDATE redactions SET " + set_clause + " WHERE id = ?"  # nosec B608
    cursor = _execute(conn, query, tuple(params))
    return bool(getattr(cursor, "rowcount", 0) > 0)


def delete_redaction(conn: Connection, redaction_id: int) -> bool:
    """Delete a redaction row by id."""

    cursor = _execute(conn, "DELETE FROM redactions WHERE id = ?", (redaction_id,))
    return bool(getattr(cursor, "rowcount", 0) > 0)


def _row_to_record(row: Iterable[Any]) -> RedactionRecord:
    """Convert a DB row to a RedactionRecord."""

    (
        row_id,
        prompt_id,
        rule_id,
        scope,
        field_path,
        replacement_text,
        reason,
        actor,
        active,
        created_at,
        updated_at,
    ) = row
    return RedactionRecord(
        id=int(row_id),
        prompt_id=int(prompt_id) if prompt_id is not None else None,
        rule_id=str(rule_id) if rule_id is not None else None,
        scope=str(scope),
        field_path=str(field_path) if field_path is not None else None,
        replacement_text=str(replacement_text),
        reason=str(reason) if reason is not None else None,
        actor=str(actor) if actor is not None else None,
        active=bool(active),
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


def _collect_update_fields(
    *,
    prompt_id: int | None,
    scope: str | None,
    field_path: str | None,
    replacement_text: str | None,
    reason: str | None,
    actor: str | None,
    rule_id: str | None,
    active: bool | None,
) -> tuple[list[str], list[Any]]:
    """Build update clause components with validation."""

    assignments: list[str] = []
    params: list[Any] = []

    _append_prompt(assignments, params, prompt_id)
    _append_scope(assignments, params, scope)
    _append_field_path(assignments, params, scope, field_path)
    _append_replacement(assignments, params, replacement_text)
    _append_optional(assignments, params, "reason", reason)
    _append_optional(assignments, params, "actor", actor)
    _append_rule(assignments, params, rule_id)
    _append_active(assignments, params, active)

    return assignments, params


def _append_prompt(
    assignments: list[str], params: list[Any], prompt_id: int | None
) -> None:
    """Add prompt assignment when present."""

    if prompt_id is not None:
        assignments.append("prompt_id = ?")
        params.append(prompt_id)


def _append_scope(assignments: list[str], params: list[Any], scope: str | None) -> None:
    """Add scope assignment with validation."""

    if scope is not None:
        _validate_scope(scope)
        assignments.append("scope = ?")
        params.append(scope)


def _append_field_path(
    assignments: list[str],
    params: list[Any],
    scope: str | None,
    field_path: str | None,
) -> None:
    """Add field_path assignment with validation."""

    if field_path is None:
        return
    _validate_field_path(scope or "prompt", field_path)
    assignments.append("field_path = ?")
    params.append(field_path.strip() or None)


def _append_replacement(
    assignments: list[str], params: list[Any], replacement_text: str | None
) -> None:
    """Add replacement_text assignment with validation."""

    if replacement_text is None:
        return
    replacement = replacement_text.strip()
    if not replacement:
        raise ValueError("replacement_text must be a non-empty string.")
    assignments.append("replacement_text = ?")
    params.append(replacement)


def _append_optional(
    assignments: list[str],
    params: list[Any],
    column: str,
    value: str | None,
) -> None:
    """Add optional string assignment."""

    if value is not None:
        assignments.append(f"{column} = ?")
        params.append(_normalize_optional(value))


def _append_rule(
    assignments: list[str], params: list[Any], rule_id: str | None
) -> None:
    """Add rule_id assignment when provided."""

    if rule_id is not None:
        assignments.append("rule_id = ?")
        params.append(rule_id)


def _append_active(
    assignments: list[str], params: list[Any], active: bool | None
) -> None:
    """Add active flag assignment when provided."""

    if active is not None:
        assignments.append("active = ?")
        params.append(1 if active else 0)


def _execute(conn: Any, query: str, params: Iterable[Any] | None = None) -> Any:
    """Execute a query with placeholder adaptation for sqlite and psycopg2."""

    params = tuple(params or ())
    prepared = _prepare_query(conn, query)
    cursor = conn.cursor()
    cursor.execute(prepared, params)
    return cursor


def _prepare_query(conn: Any, query: str) -> str:
    """Convert sqlite-style ? placeholders to %s when needed."""

    module_name = conn.__class__.__module__
    if module_name.startswith("sqlite3"):
        return query
    return query.replace("?", "%s")
