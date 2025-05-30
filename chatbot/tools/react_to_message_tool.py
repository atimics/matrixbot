from typing import Dict, Any, List, Optional

from tool_base import AbstractTool, ToolResult
from event_definitions import ReactToMessageCommand

class ReactToMessageTool(AbstractTool):
    """Tool to react to a specific message with an emoji or text."""

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "react_to_message",
                "description": "Reacts to a specific message with an emoji or text key.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_event_id": {
                            "type": "string",
                            "description": "The event ID of the message to react to. Can be '$event:last_user_message' to refer to the last user message in the current batch."
                        },
                        "reaction_key": {
                            "type": "string",
                            "description": "The reaction emoji or key (e.g., '👍', '😄')."
                        }
                    },
                    "required": ["target_event_id", "reaction_key"]
                }
            }
        }

    async def execute(
        self,
        room_id: str,
        arguments: Dict[str, Any],
        tool_call_id: Optional[str],
        llm_provider_info: Dict[str, Any],
        conversation_history_snapshot: List[Dict[str, Any]],
        last_user_event_id: Optional[str],
        db_path: Optional[str] = None # Added to accept db_path
    ) -> ToolResult:
        target_event_id_arg = arguments.get("target_event_id")
        reaction_key = arguments.get("reaction_key")

        if not target_event_id_arg:
            return ToolResult(
                status="failure",
                result_for_llm_history="[Tool react_to_message failed: Missing target_event_id argument.]",
                error_message="Missing required argument: target_event_id"
            )
        
        if reaction_key is None: # Check for None explicitly to allow empty string if desired by design, though tests imply empty is a failure
            return ToolResult(
                status="failure",
                result_for_llm_history="[Tool react_to_message failed: Missing reaction_key argument.]",
                error_message="Missing required argument: reaction_key"
            )

        if not reaction_key: # Explicitly disallow empty string for reaction_key based on test failure
            return ToolResult(
                status="failure",
                result_for_llm_history="[Tool react_to_message failed: Reaction key cannot be empty.]",
                error_message="Reaction key cannot be empty."
            )

        resolved_target_event_id = target_event_id_arg
        if target_event_id_arg == "$event:last_user_message":
            if last_user_event_id:
                resolved_target_event_id = last_user_event_id
            else:
                return ToolResult(
                    status="failure",
                    result_for_llm_history="[Tool react_to_message failed: LLM requested reaction to last user message, but no last_user_event_id was available in context.]",
                    error_message="Cannot resolve $event:last_user_message for reaction, last_user_event_id is not available."
                )

        react_command = ReactToMessageCommand(
            room_id=room_id,
            event_id_to_react_to=resolved_target_event_id, 
            reaction_key=reaction_key
        )
        return ToolResult(
            status="success",
            result_for_llm_history=f"Reaction '{reaction_key}' sent to event '{resolved_target_event_id}'.",
            commands_to_publish=[react_command]
        )
