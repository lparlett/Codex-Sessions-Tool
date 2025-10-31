# Purpose: aggregate session parser handler helpers.
# Author: Codex with Lauren Parlett
# Date: 2025-10-30
# Related tests: TBD (planned)

"""Handler utilities supporting Codex session parsing."""

from .db_utils import (
    AgentReasoningInsert,
    EventInsert,
    FunctionCallInsert,
    FunctionCallOutputUpdate,
    PromptInsert,
    SAFE_COLUMNS,  # Explicitly import SAFE_COLUMNS
    SessionInsert,
    extract_session_details,
    extract_token_fields,
    extract_turn_context,
    get_reasoning_text,
    insert_agent_reasoning,
    insert_function_call,
    insert_function_plan,
    insert_prompt,
    insert_session,
    insert_token,
    insert_turn_context,
    json_dumps,
    parse_prompt_message,
    update_function_call_output,
)
from .db_utils import DB_UTIL_EXPORTS
from .event_handlers import (
    EventContext,
    EventHandlerDeps,
    FunctionCallTracker,
    handle_event_msg,
    handle_response_item_event,
    handle_turn_context_event,
)
from .event_handlers import EVENT_HANDLER_EXPORTS

# Explicitly list all exports for static type checking
__all__ = [
    # DB Utilities
    "AgentReasoningInsert",
    "EventInsert",
    "FunctionCallInsert",
    "FunctionCallOutputUpdate",
    "PromptInsert",
    "SAFE_COLUMNS",
    "SessionInsert",
    "extract_session_details",
    "extract_token_fields",
    "extract_turn_context",
    "get_reasoning_text",
    "insert_agent_reasoning",
    "insert_function_call",
    "insert_function_plan",
    "insert_prompt",
    "insert_session",
    "insert_token",
    "insert_turn_context",
    "json_dumps",
    "parse_prompt_message",
    "update_function_call_output",
    # Event Handlers
    "EventContext",
    "EventHandlerDeps",
    "FunctionCallTracker",
    "handle_event_msg",
    "handle_response_item_event",
    "handle_turn_context_event",
]
