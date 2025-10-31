# Purpose: encapsulate event handling helpers for session ingest.
# Author: Codex with Lauren Parlett
# Date: 2025-10-30
# Related tests: TBD (planned)

"""Helper functions for processing grouped Codex session events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict


InsertTokenFn = Callable[[Any, int, str | None, dict, dict], None]
InsertTurnContextFn = Callable[[Any, int, str | None, dict, dict], None]
InsertAgentReasoningFn = Callable[[Any, int, str | None, str, dict, dict], None]
InsertFunctionPlanFn = Callable[[Any, int, str | None, dict, dict], None]
InsertFunctionCallFn = Callable[[Any, int, str | None, dict, dict], int]
UpdateFunctionCallOutputFn = Callable[[Any, int, str | None, dict, dict], None]


@dataclass
class EventHandlerDeps:
    """Callable dependencies used by the session event handlers."""

    insert_token: InsertTokenFn
    insert_turn_context: InsertTurnContextFn
    insert_agent_reasoning: InsertAgentReasoningFn
    insert_function_plan: InsertFunctionPlanFn
    insert_function_call: InsertFunctionCallFn
    update_function_call_output: UpdateFunctionCallOutputFn


@dataclass
class FunctionCallTracker:
    """Track pending function calls so outputs can be matched accurately."""

    by_id: Dict[str, int] = field(default_factory=dict)
    queue: list[int] = field(default_factory=list)

    def register(self, call_id: str | None, row_id: int) -> None:
        """Register call row by id or queue for later resolution."""

        if call_id:
            self.by_id[call_id] = row_id
        else:
            self.queue.append(row_id)

    def resolve(self, call_id: str | None) -> int | None:
        """Resolve row id for a given call id or fall back to queue."""

        if call_id and call_id in self.by_id:
            return self.by_id.pop(call_id)
        if self.queue:
            return self.queue.pop(0)
        return None


def handle_event_msg(
    deps: EventHandlerDeps,
    conn,
    prompt_id: int,
    timestamp: str | None,
    payload: dict,
    raw_event: dict,
    counts: dict[str, int],
) -> None:
    """Handle event_msg payload variants for a prompt."""

    subtype = payload.get("type")
    if subtype == "token_count":
        deps.insert_token(conn, prompt_id, timestamp, payload, raw_event)
        counts["token_messages"] += 1
        return

    if subtype == "agent_reasoning":
        _record_agent_reasoning(
            deps,
            conn,
            prompt_id,
            timestamp,
            "event_msg",
            payload,
            raw_event,
            counts,
        )
        return

    if subtype == "turn_aborted":
        _record_agent_reasoning(
            deps,
            conn,
            prompt_id,
            timestamp,
            "turn_aborted",
            payload,
            raw_event,
            counts,
        )
        return

    if subtype == "agent_message":
        _record_agent_reasoning(
            deps,
            conn,
            prompt_id,
            timestamp,
            "agent_message",
            payload,
            raw_event,
            counts,
        )


def handle_turn_context_event(
    deps: EventHandlerDeps,
    conn,
    prompt_id: int,
    timestamp: str | None,
    payload: dict,
    raw_event: dict,
    counts: dict[str, int],
) -> None:
    """Handle turn_context events and update counts."""

    deps.insert_turn_context(conn, prompt_id, timestamp, payload, raw_event)
    counts["turn_context_messages"] += 1


def handle_response_item_event(
    deps: EventHandlerDeps,
    conn,
    prompt_id: int,
    timestamp: str | None,
    payload: dict,
    raw_event: dict,
    tracker: FunctionCallTracker,
    counts: dict[str, int],
) -> None:
    """Handle response_item payload variants."""

    subtype = payload.get("type")
    if subtype == "reasoning":
        return

    if subtype == "function_call":
        name = payload.get("name")
        if name == "update_plan":
            deps.insert_function_plan(
                conn,
                prompt_id,
                timestamp,
                payload,
                raw_event,
            )
            counts["function_plan_messages"] += 1
            return
        _register_function_call(
            deps,
            conn,
            prompt_id,
            timestamp,
            payload,
            raw_event,
            tracker,
            counts,
        )
        return

    if subtype == "function_call_output":
        call_id_value = payload.get("call_id")
        call_id = (
            call_id_value
            if isinstance(call_id_value, str) and call_id_value
            else None
        )
        row_id = tracker.resolve(call_id)
        if row_id is None:
            row_id = _register_function_call(
                deps,
                conn,
                prompt_id,
                None,
                {},
                {},
                tracker,
                counts,
            )
        deps.update_function_call_output(
            conn,
            row_id,
            timestamp,
            payload,
            raw_event,
        )


def _record_agent_reasoning(
    deps: EventHandlerDeps,
    conn,
    prompt_id: int,
    timestamp: str | None,
    source: str,
    payload: dict,
    raw_event: dict,
    counts: dict[str, int],
) -> None:
    """Persist agent reasoning and update counters."""

    deps.insert_agent_reasoning(
        conn,
        prompt_id,
        timestamp,
        source,
        payload,
        raw_event,
    )
    counts["agent_reasoning_messages"] += 1


def _register_function_call(
    deps: EventHandlerDeps,
    conn,
    prompt_id: int,
    timestamp: str | None,
    payload: dict,
    raw_event: dict,
    tracker: FunctionCallTracker,
    counts: dict[str, int],
) -> int:
    """Insert a function call row and track it for later outputs."""

    row_id = deps.insert_function_call(
        conn,
        prompt_id,
        timestamp,
        payload,
        raw_event,
    )
    call_id_value = payload.get("call_id")
    call_id = (
        call_id_value
        if isinstance(call_id_value, str) and call_id_value
        else None
    )
    tracker.register(call_id, row_id)
    counts["function_calls"] += 1
    return row_id
