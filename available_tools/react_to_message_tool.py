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

        resolved_target_event_id = target_event_id_arg
        if target_event_id_arg == "$event:last_user_message" and last_user_event_id:
            resolved_target_event_id = last_user_event_id
        elif target_event_id_arg == "$event:last_user_message" and not last_user_event_id:
            return ToolResult(
                status="failure",
                result_for_llm_history="[Tool react_to_message failed: LLM requested reaction to last user message, but no last_user_event_id was available in context.]",
                error_message="Cannot react to $event:last_user_message; context for last_user_event_id is missing."
            )

        if not resolved_target_event_id or not reaction_key:
            return ToolResult(
                status="failure",
                result_for_llm_history=f"[Tool react_to_message failed: Missing required arguments. Provided: target_event_id='{resolved_target_event_id}', reaction_key='{reaction_key}']",
                error_message="Missing 'target_event_id' or 'reaction_key' argument for react_to_message tool."
            )

        react_command = ReactToMessageCommand(
            room_id=room_id,
            event_id_to_react_to=resolved_target_event_id, # Changed from target_event_id
            reaction_key=reaction_key
        )
        return ToolResult(
            status="success",
            result_for_llm_history=f"[Tool react_to_message executed: Reaction '{reaction_key}' queued.]",
            commands_to_publish=[react_command]
        )
