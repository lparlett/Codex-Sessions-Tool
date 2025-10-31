# Purpose: normalize Codex session events into SQLite rows for transparency.
# Author: Codex with Lauren Parlett
# Date: 2025-10-30
# Related tests: TBD (planned)

"""Ingest Codex session logs into SQLite."""

from __future__ import annotations

import logging
from itertools import islice
from pathlib import Path
from typing import Iterable, Iterator, TypedDict

from src.parsers.session_parser import (
    SessionDiscoveryError,
    iter_session_files,
    group_by_user_messages,
    load_session_events,
)
from src.parsers.handlers.event_handlers import (
    EventHandlerDeps,
    FunctionCallTracker,
    handle_event_msg,
    handle_response_item_event,
    handle_turn_context_event,
)
from src.parsers.handlers.db_utils import (
    insert_session,
    insert_prompt,
    insert_token,
    insert_turn_context,
    insert_agent_reasoning,
    insert_function_plan,
    insert_function_call,
    update_function_call_output,
)
from src.services.database import ensure_schema, get_connection


logger = logging.getLogger(__name__)


class SessionSummary(TypedDict):
    """Structured ingest result for a single Codex session file."""

    session_file: str
    file_id: int
    prompts: int
    token_messages: int
    turn_context_messages: int
    agent_reasoning_messages: int
    function_plan_messages: int
    function_calls: int


def _ensure_file_row(conn, session_file: Path) -> int:
    """Return file id, creating or resetting prompt data as needed."""

    cursor = conn.execute(
        "SELECT id FROM files WHERE path = ?", (str(session_file),)
    )
    row = cursor.fetchone()
    if row:
        file_id = row[0]
        conn.execute(
            "UPDATE files SET ingested_at = CURRENT_TIMESTAMP WHERE id = ?",
            (file_id,),
        )
        conn.execute("DELETE FROM prompts WHERE file_id = ?", (file_id,))
        conn.execute("DELETE FROM sessions WHERE file_id = ?", (file_id,))
        return file_id
    cursor = conn.execute(
        "INSERT INTO files (path) VALUES (?)", (str(session_file),)
    )
    return cursor.lastrowid


def _process_events(
    conn,
    prompt_id: int,
    events: Iterable[dict],
) -> dict[str, int]:
    """Process events for a prompt and populate child tables."""

    counts = {
        "token_messages": 0,
        "turn_context_messages": 0,
        "agent_reasoning_messages": 0,
        "function_plan_messages": 0,
        "function_calls": 0,
    }

    deps = EventHandlerDeps(
        insert_token=insert_token,
        insert_turn_context=insert_turn_context,
        insert_agent_reasoning=insert_agent_reasoning,
        insert_function_plan=insert_function_plan,
        insert_function_call=insert_function_call,
        update_function_call_output=update_function_call_output,
    )
    tracker = FunctionCallTracker()

    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue

        event_type = event.get("type")
        timestamp = event.get("timestamp")

        if event_type == "event_msg":
            handle_event_msg(
                deps,
                conn,
                prompt_id,
                timestamp,
                payload,
                event,
                counts,
            )
        elif event_type == "turn_context":
            handle_turn_context_event(
                deps,
                conn,
                prompt_id,
                timestamp,
                payload,
                event,
                counts,
            )
        elif event_type == "response_item":
            handle_response_item_event(
                deps,
                conn,
                prompt_id,
                timestamp,
                payload,
                event,
                tracker,
                counts,
            )

    return counts


def _ingest_single_session(
    conn,
    session_file: Path,
    *,
    verbose: bool = False,
) -> SessionSummary:
    """Internal helper to ingest one session using an existing connection."""

    if verbose:
        logger.info("Ingesting %s", session_file)

    events = load_session_events(session_file)
    prelude, groups = group_by_user_messages(events)

    file_id = _ensure_file_row(conn, session_file)

    summary: SessionSummary = {
        "session_file": str(session_file),
        "file_id": file_id,
        "prompts": 0,
        "token_messages": 0,
        "turn_context_messages": 0,
        "agent_reasoning_messages": 0,
        "function_plan_messages": 0,
        "function_calls": 0,
    }

    insert_session(conn, file_id, prelude or [])

    for index, group in enumerate(groups, start=1):
        prompt_event = group["user"]
        prompt_payload = prompt_event.get("payload", {})
        message = (
            prompt_payload.get("message", "")
            if isinstance(prompt_payload, dict)
            else ""
        )
        timestamp = prompt_event.get("timestamp")
        prompt_id = insert_prompt(
            conn,
            file_id,
            index,
            timestamp,
            message,
            prompt_event,
        )
        summary["prompts"] = summary["prompts"] + 1
        counts = _process_events(conn, prompt_id, group["events"])
        for key in (
            "token_messages",
            "turn_context_messages",
            "agent_reasoning_messages",
            "function_plan_messages",
            "function_calls",
        ):
            summary[key] = summary[key] + counts.get(key, 0)

    return summary


def ingest_session_file(
    session_file: Path,
    db_path: Path,
    *,
    verbose: bool = False,
) -> SessionSummary:
    """Parse a session log and persist structured data into SQLite."""

    conn = get_connection(db_path)
    ensure_schema(conn)

    try:
        summary = _ingest_single_session(conn, session_file, verbose=verbose)
        conn.commit()
        return summary
    finally:
        conn.close()


def ingest_sessions_in_directory(
    root: Path,
    db_path: Path,
    *,
    limit: int | None = None,
    verbose: bool = False,
) -> Iterator[SessionSummary]:
    """Ingest multiple session files beneath ``root``."""

    conn = get_connection(db_path)
    ensure_schema(conn)

    try:
        files_iter = iter_session_files(root)
        if limit is not None:
            files_iter = islice(files_iter, limit)

        processed = False
        for session_file in files_iter:
            processed = True
            summary = _ingest_single_session(
                conn,
                session_file,
                verbose=verbose,
            )
            conn.commit()
            yield summary

        if not processed:
            raise SessionDiscoveryError(f"No session files found under {root}")
    finally:
        conn.close()
