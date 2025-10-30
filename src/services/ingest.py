# Purpose: transform Codex session events into normalized SQLite rows via structured ingest.
# Author: Codex with Lauren Parlett
# Date: 2025-10-30
# Related tests: TBD (planned)

"""Ingest Codex session logs into SQLite."""

from __future__ import annotations

import json
import logging
from itertools import islice
from pathlib import Path
from typing import Any, Iterable, Iterator, TypedDict

from src.parsers.session_parser import (
    SessionDiscoveryError,
    iter_session_files,
    group_by_user_messages,
    load_session_events,
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


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def _extract_tag_value(text: str, tag: str) -> str | None:
    """Return inner text for the given XML-style tag if present."""

    start_tag = f"<{tag}>"
    end_tag = f"</{tag}>"
    start_index = text.find(start_tag)
    if start_index == -1:
        return None
    start_index += len(start_tag)
    end_index = text.find(end_tag, start_index)
    if end_index == -1:
        return None
    return text[start_index:end_index].strip()


def _extract_session_details(prelude: Iterable[dict]) -> dict[str, Any]:
    """Derive session-wide metadata from the prelude events."""

    details: dict[str, Any] = {
        "session_id": None,
        "session_timestamp": None,
        "cwd": None,
        "approval_policy": None,
        "sandbox_mode": None,
        "network_access": None,
    }

    for event in prelude:
        event_type = event.get("type")
        payload = event.get("payload")
        if event_type == "session_meta" and isinstance(payload, dict):
            details["session_id"] = payload.get("id")
            details["session_timestamp"] = payload.get("timestamp") or event.get("timestamp")
            details["cwd"] = payload.get("cwd") or details["cwd"]
        elif (
            event_type == "response_item"
            and isinstance(payload, dict)
            and payload.get("type") == "message"
        ):
            content = payload.get("content")
            if isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    text = item.get("text")
                    if not isinstance(text, str):
                        continue
                    if "<environment_context>" not in text:
                        continue
                    details["cwd"] = _extract_tag_value(text, "cwd") or details["cwd"]
                    details["approval_policy"] = _extract_tag_value(text, "approval_policy")
                    details["sandbox_mode"] = _extract_tag_value(text, "sandbox_mode")
                    details["network_access"] = _extract_tag_value(text, "network_access")

    return details


def _insert_session(conn, file_id: int, prelude: list[dict]) -> None:
    """Persist session-level metadata captured before the first user prompt."""

    details = _extract_session_details(prelude)
    conn.execute(
        """
        INSERT INTO sessions (
            file_id, session_id, session_timestamp, cwd, approval_policy,
            sandbox_mode, network_access, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            file_id,
            details["session_id"],
            details["session_timestamp"],
            details["cwd"],
            details["approval_policy"],
            details["sandbox_mode"],
            details["network_access"],
            _json_dumps({"events": prelude}),
        ),
    )


def _extract_token_fields(payload: dict) -> dict:
    primary = payload.get("rate_limits", {}).get("primary", {}) if isinstance(payload, dict) else {}
    secondary = payload.get("rate_limits", {}).get("secondary", {}) if isinstance(payload, dict) else {}
    return {
        "primary_used_percent": primary.get("used_percent"),
        "primary_window_minutes": primary.get("window_minutes"),
        "primary_resets": primary.get("resets_at") or primary.get("resets_in_seconds"),
        "secondary_used_percent": secondary.get("used_percent"),
        "secondary_window_minutes": secondary.get("window_minutes"),
        "secondary_resets": secondary.get("resets_at") or secondary.get("resets_in_seconds"),
    }


def _extract_turn_context(payload: dict) -> dict:
    sandbox = payload.get("sandbox_policy", {}) if isinstance(payload, dict) else {}
    writable_roots = sandbox.get("writable_roots")
    if isinstance(writable_roots, list):
        writable_roots = ", ".join(str(item) for item in writable_roots)
    return {
        "cwd": payload.get("cwd"),
        "approval_policy": payload.get("approval_policy"),
        "sandbox_mode": sandbox.get("mode"),
        "network_access": sandbox.get("network_access"),
        "writable_roots": writable_roots,
    }


def _get_reasoning_text(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return None
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        return text
    if payload.get("summary"):
        summary = payload["summary"]
        if isinstance(summary, list) and summary:
            entry = summary[0]
            if isinstance(entry, dict):
                text = entry.get("text")
                if isinstance(text, str) and text.strip():
                    return text
    content = payload.get("content")
    if isinstance(content, str) and content.strip():
        return content
    return None


def _ensure_file_row(conn, session_file: Path) -> int:
    # Ensure a canonical record for the session file so re-ingest replaces prior rows.
    cursor = conn.execute("SELECT id FROM files WHERE path = ?", (str(session_file),))
    row = cursor.fetchone()
    if row:
        file_id = row[0]
        conn.execute("UPDATE files SET ingested_at = CURRENT_TIMESTAMP WHERE id = ?", (file_id,))
        # Remove existing prompt-linked data so the ingest always reflects the latest run.
        conn.execute("DELETE FROM prompts WHERE file_id = ?", (file_id,))
        conn.execute("DELETE FROM sessions WHERE file_id = ?", (file_id,))
        return file_id
    cursor = conn.execute("INSERT INTO files (path) VALUES (?)", (str(session_file),))
    return cursor.lastrowid


def _parse_prompt_message(message: str | None) -> tuple[str | None, str | None, str | None]:
    """Extract structured context from the standard prompt template."""

    if not message:
        return None, None, None

    active_file: str | None = None
    open_tabs: list[str] = []
    my_request_lines: list[str] = []

    state: str | None = None
    for line in message.splitlines():
        stripped = line.strip()

        if stripped.startswith("## Active file:"):
            active_file = stripped[len("## Active file:") :].strip() or None
            state = None
            continue

        if stripped.startswith("## Open tabs:"):
            state = "open_tabs"
            continue

        if stripped.startswith("## My request for Codex:"):
            state = "my_request"
            continue

        if state == "open_tabs":
            if stripped.startswith("-"):
                open_tabs.append(stripped[1:].strip())
                continue
            if stripped.startswith("## ") or stripped == "":
                state = None
                continue
            open_tabs.append(stripped)
            continue

        if state == "my_request":
            if stripped.startswith("## "):
                state = None
                continue
            my_request_lines.append(line.rstrip())

    open_tabs_value = "\n".join(tab for tab in open_tabs if tab) or None
    my_request_value = "\n".join(line for line in my_request_lines if line).strip() or None

    return active_file, open_tabs_value, my_request_value


def _insert_prompt(conn, file_id: int, prompt_index: int, timestamp: str | None, message: str, raw: dict) -> int:
    active_file, open_tabs, my_request = _parse_prompt_message(message)
    cursor = conn.execute(
        """
        INSERT INTO prompts (
            file_id, prompt_index, timestamp, message, active_file, open_tabs, my_request, raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            file_id,
            prompt_index,
            timestamp,
            message,
            active_file,
            open_tabs,
            my_request,
            _json_dumps(raw),
        ),
    )
    return cursor.lastrowid


def _insert_token(conn, prompt_id: int, timestamp: str | None, payload: dict, raw: dict) -> None:
    fields = _extract_token_fields(payload)
    conn.execute(
        """
        INSERT INTO token_messages (
            prompt_id, timestamp,
            primary_used_percent, primary_window_minutes, primary_resets,
            secondary_used_percent, secondary_window_minutes, secondary_resets,
            raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            prompt_id,
            timestamp,
            fields["primary_used_percent"],
            fields["primary_window_minutes"],
            fields["primary_resets"],
            fields["secondary_used_percent"],
            fields["secondary_window_minutes"],
            fields["secondary_resets"],
            _json_dumps(raw),
        ),
    )


def _insert_turn_context(conn, prompt_id: int, timestamp: str | None, payload: dict, raw: dict) -> None:
    ctx = _extract_turn_context(payload)
    conn.execute(
        """
        INSERT INTO turn_context_messages (
            prompt_id, timestamp, cwd, approval_policy, sandbox_mode,
            network_access, writable_roots, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            prompt_id,
            timestamp,
            ctx["cwd"],
            ctx["approval_policy"],
            ctx["sandbox_mode"],
            str(ctx["network_access"]) if ctx["network_access"] is not None else None,
            ctx["writable_roots"],
            _json_dumps(raw),
        ),
    )


def _insert_agent_reasoning(conn, prompt_id: int, timestamp: str | None, source: str, payload: dict, raw: dict) -> None:
    text = _get_reasoning_text(payload)
    conn.execute(
        """
        INSERT INTO agent_reasoning_messages (prompt_id, timestamp, source, text, raw_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (prompt_id, timestamp, source, text, _json_dumps(raw)),
    )


def _insert_function_plan(conn, prompt_id: int, timestamp: str | None, payload: dict, raw: dict) -> None:
    conn.execute(
        """
        INSERT INTO function_plan_messages (prompt_id, timestamp, name, arguments, raw_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            prompt_id,
            timestamp,
            payload.get("name"),
            payload.get("arguments"),
            _json_dumps(raw),
        ),
    )


def _insert_function_call(
    conn,
    prompt_id: int,
    timestamp: str | None,
    payload: dict,
    raw: dict,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO function_calls (
            prompt_id, call_timestamp, name, call_id, arguments, raw_call_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            prompt_id,
            timestamp,
            payload.get("name"),
            payload.get("call_id"),
            payload.get("arguments"),
            _json_dumps(raw),
        ),
    )
    return cursor.lastrowid


def _update_function_call_output(
    conn,
    row_id: int,
    timestamp: str | None,
    payload: dict,
    raw: dict,
) -> None:
    conn.execute(
        """
        UPDATE function_calls
        SET output_timestamp = ?, output = ?, raw_output_json = ?
        WHERE id = ?
        """,
        (
            timestamp,
            payload.get("output"),
            _json_dumps(raw),
            row_id,
        ),
    )


def _process_events(conn, prompt_id: int, events: Iterable[dict]) -> dict[str, int]:
    counts = {
        "token_messages": 0,
        "turn_context_messages": 0,
        "agent_reasoning_messages": 0,
        "function_plan_messages": 0,
        "function_calls": 0,
    }

    call_rows_by_id: dict[str, int] = {}
    call_row_queue: list[int] = []

    for event in events:
        event_type = event.get("type")
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        timestamp = event.get("timestamp")

        if event_type == "event_msg":
            subtype = payload.get("type")
            if subtype == "token_count":
                _insert_token(conn, prompt_id, timestamp, payload, event)
                counts["token_messages"] += 1
            elif subtype == "agent_reasoning":
                _insert_agent_reasoning(conn, prompt_id, timestamp, "event_msg", payload, event)
                counts["agent_reasoning_messages"] += 1
            elif subtype == "turn_aborted":
                _insert_agent_reasoning(conn, prompt_id, timestamp, "turn_aborted", payload, event)
                counts["agent_reasoning_messages"] += 1
            elif subtype == "agent_message":
                _insert_agent_reasoning(conn, prompt_id, timestamp, "agent_message", payload, event)
                counts["agent_reasoning_messages"] += 1

        elif event_type == "turn_context":
            _insert_turn_context(conn, prompt_id, timestamp, payload, event)
            counts["turn_context_messages"] += 1

        elif event_type == "response_item":
            subtype = payload.get("type")
            if subtype == "reasoning":
                # Skip encrypted reasoning content that mirrors agent_reasoning entries.
                continue
            elif subtype == "function_call":
                name = payload.get("name")
                if name == "update_plan":
                    _insert_function_plan(conn, prompt_id, timestamp, payload, event)
                    counts["function_plan_messages"] += 1
                else:
                    row_id = _insert_function_call(conn, prompt_id, timestamp, payload, event)
                    call_id = payload.get("call_id")
                    if isinstance(call_id, str) and call_id:
                        call_rows_by_id[call_id] = row_id
                    else:
                        call_row_queue.append(row_id)
                    counts["function_calls"] += 1
            elif subtype == "function_call_output":
                call_id = payload.get("call_id")
                row_id: int | None = None
                if isinstance(call_id, str) and call_id and call_id in call_rows_by_id:
                    row_id = call_rows_by_id.pop(call_id)
                elif call_row_queue:
                    row_id = call_row_queue.pop(0)
                else:
                    row_id = _insert_function_call(conn, prompt_id, None, {}, {})
                    counts["function_calls"] += 1
                _update_function_call_output(conn, row_id, timestamp, payload, event)

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

    _insert_session(conn, file_id, prelude or [])

    for index, group in enumerate(groups, start=1):
        prompt_event = group["user"]
        prompt_payload = prompt_event.get("payload", {})
        message = prompt_payload.get("message", "") if isinstance(prompt_payload, dict) else ""
        timestamp = prompt_event.get("timestamp")
        prompt_id = _insert_prompt(conn, file_id, index, timestamp, message, prompt_event)
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


def ingest_session_file(session_file: Path, db_path: Path, *, verbose: bool = False) -> SessionSummary:
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
            summary = _ingest_single_session(conn, session_file, verbose=verbose)
            conn.commit()
            yield summary

        if not processed:
            raise SessionDiscoveryError(f"No session files found under {root}")
    finally:
        conn.close()
