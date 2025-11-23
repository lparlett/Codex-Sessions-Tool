"""Codex action event model.

This module defines the Action class for representing AI agent actions in the
Codex system. Actions include tool calls, file edits, and other operations
that modify the workspace state.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from ...core.models.base_event import BaseEvent, EventCategory, EventPriority


class Action(BaseEvent):
    """Represents an action taken by the Codex AI agent.
    
    An action is a specific type of event that represents something the AI
    agent has done, such as calling a tool or editing a file. Each action
    has both the standard event fields from BaseEvent and action-specific
    details like the tool name, parameters and results.

    Attributes:
        _action_type: The type of action being performed (tool_call, etc)
        _details: Additional contextual details about the action
    """

    def __init__(
        self,
        action_type: str,
        session_id: str,
        timestamp: Optional[datetime] = None,
        details: Optional[Dict[str, Any]] = None,
        raw_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize a Codex action event.

        Args:
            action_type: Type of action (tool_call, file_edit, etc)
            session_id: Unique identifier for the chat session
            timestamp: When the action occurred (defaults to now)
            details: Additional action details (tool name, params, result)
            raw_data: Original event data for audit/debugging
        """
        # Map action type to event category
        event_category = self._get_category(action_type)

        # Initialize base event
        super().__init__(
            agent_type="codex",
            timestamp=timestamp or datetime.now(),
            event_type=f"action.{action_type}",
            event_category=event_category,
            priority=EventPriority.MEDIUM,
            session_id=session_id,
            raw_data=raw_data or {},
        )

        # Store action details
        self._action_type = action_type
        self._details = details or {}

    @property
    def action_type(self) -> str:
        """Get the type of action being performed."""
        return self._action_type
    
    @property
    def tool_name(self) -> Optional[str]:
        """Get the name of the tool if this is a tool action."""
        return self._details.get("tool_name")

    @property
    def parameters(self) -> Optional[Dict[str, Any]]:
        """Get the tool parameters if this is a tool action."""
        return self._details.get("parameters")
    
    @property
    def result(self) -> Optional[str]:
        """Get the action result if available."""
        return self._details.get("result")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary.
        
        Returns:
            Dictionary with event and action-specific data including:
                - Core event fields from BaseEvent (agent_type, etc)
                - action_type: The type of action performed 
                - tool_name: Name of tool used (if a tool action)
                - parameters: Tool parameters (if a tool action)
                - result: Action result (if available)
        """
        return {
            # Core event fields 
            "agent_type": self.agent_type,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "event_category": self.event_category.value,
            "priority": self.priority.value,
            "session_id": self.session_id,
            "raw_data": self.raw_data,
            # Action-specific fields
            "action_type": self._action_type,
            "tool_name": self.tool_name,
            "parameters": self.parameters, 
            "result": self.result,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Action:
        """Create an Action instance from a dictionary.
        
        Args:
            data: Dictionary containing serialized event data
            
        Returns:
            New Action instance populated with the data
        """
        return cls(
            action_type=data["action_type"],
            session_id=data["session_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            details={
                "tool_name": data.get("tool_name"),
                "parameters": data.get("parameters"),
                "result": data.get("result"),
            },
            raw_data=data.get("raw_data", {}),
        )

    @staticmethod
    def _get_category(action_type: str) -> EventCategory:
        """Get the event category based on action type.
        
        Args:
            action_type: The type of action being performed
            
        Returns:
            The corresponding EventCategory
        """
        if action_type == "tool_call":
            return EventCategory.TOOL_CALL
        if action_type == "tool_result":
            return EventCategory.TOOL_RESULT
        return EventCategory.SYSTEM
