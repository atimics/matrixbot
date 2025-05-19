from typing import Dict, Any, List, Optional
import json
import logging

from tool_base import AbstractTool, ToolResult
from event_definitions import SendReplyCommand # Changed from SendMatrixMessageCommand

logger = logging.getLogger(__name__)

class SendReplyTool(AbstractTool):
    """Tool to send a reply message to the current room."""

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "send_reply",
                "description": "Sends a textual reply message to the current room, quoting the message being replied to.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "The text content of the reply message."
                        },
                        "reply_to_event_id": {
                            "type": "string",
                            "description": "The event ID of the message to reply to. This visually quotes the original message. Can be '$event:last_user_message' to refer to the last user message in the current batch."
                        }
                    },
                    "required": ["text", "reply_to_event_id"]
                }
            }
        }

    async def execute(
        self,
        room_id: str,
        arguments: Dict[str, Any], # Ensure this is Dict[str, Any]
        tool_call_id: Optional[str],
        llm_provider_info: Dict[str, Any],
        conversation_history_snapshot: List[Dict[str, Any]],
        last_user_event_id: Optional[str],
        db_path: Optional[str] = None # Added to accept db_path
    ) -> ToolResult:
        logger.info(f"SendReplyTool: Executing in room {room_id} with args: {arguments}")
        
        text = arguments.get("text")
        reply_to_event_id_arg = arguments.get("reply_to_event_id")

        if text is None: # Check for None explicitly
            return ToolResult(
                status="failure",
                result_for_llm_history="[Tool send_reply failed: Missing text argument.]",
                error_message="Missing required argument: text"
            )

        if not text: # Check for empty string
            return ToolResult(
                status="failure",
                result_for_llm_history="[Tool send_reply failed: Text argument cannot be empty.]",
                error_message="Text argument cannot be empty."
            )

        if not reply_to_event_id_arg:
            return ToolResult(
                status="failure",
                result_for_llm_history="[Tool send_reply failed: Missing reply_to_event_id argument.]",
                error_message="Missing required argument: reply_to_event_id"
            )

        resolved_reply_to_event_id = reply_to_event_id_arg
        if reply_to_event_id_arg == "$event:last_user_message":
            if last_user_event_id:
                resolved_reply_to_event_id = last_user_event_id
            else:
                return ToolResult(
                    status="failure",
                    result_for_llm_history="[Tool send_reply failed: LLM requested reply to last user message, but no last_user_event_id was available in context.]",
                    error_message="Cannot resolve $event:last_user_message, last_user_event_id is not available."
                )

        # Use SendReplyCommand as it's specifically for replies
        send_command = SendReplyCommand(
            room_id=room_id,
            text=text,
            reply_to_event_id=resolved_reply_to_event_id
        )
        return ToolResult(
            status="success",
            result_for_llm_history=f"Reply '{text}' sent to event '{resolved_reply_to_event_id}'.",
            commands_to_publish=[send_command]
        )
