import logging
from typing import Dict, Any, List, Optional

from tool_base import AbstractTool, ToolResult, ToolParameter
from event_definitions import SendMatrixMessageCommand

logger = logging.getLogger(__name__)

class SendMessageTool(AbstractTool):
    """Tool to send a textual message to the current channel."""

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "send_message",
                "description": "Sends a textual message to the current channel.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "The text message to send."
                        }
                    },
                    "required": ["text"]
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
        db_path: Optional[str] = None
    ) -> ToolResult:
        text = arguments.get("text")

        if text is None: # Check for None explicitly, as empty string might be a valid (though perhaps undesirable) message
            return ToolResult(
                status="failure",
                result_for_llm_history="[Tool send_message failed: Missing required argument 'text'.]",
                error_message="Missing required argument: text"
            )
        
        if not text: # Check for empty string specifically, based on test_send_message_tool_execute_empty_text
            return ToolResult(
                status="failure",
                result_for_llm_history="[Tool send_message failed: Text argument cannot be empty.]",
                error_message="Text argument cannot be empty."
            )

        send_command = SendMatrixMessageCommand(
            room_id=room_id,
            text=text,
            reply_to_event_id=None  # As per requirement
        )
        logger.info(f"SendMessageTool: Prepared SendMatrixMessageCommand to room {room_id} with text: {text[:50]}..." )
        return ToolResult(
            status="success",
            result_for_llm_history=f"Message '{text}' sent.", # Aligning with test_send_message_tool_execute_success
            commands_to_publish=[send_command]
        )
