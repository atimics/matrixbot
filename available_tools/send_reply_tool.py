from typing import Dict, Any, List, Optional
import json
import logging

from tool_base import AbstractTool, ToolResult
from event_definitions import SendReplyCommand

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
        arguments: Dict[str, Any], # Changed type hint from str to Dict[str, Any]
        tool_call_id: Optional[str],
        llm_provider_info: Dict[str, Any],
        conversation_history_snapshot: List[Dict[str, Any]],
        last_user_event_id: Optional[str]
    ) -> ToolResult:
        logger.info(f"SendReplyTool: Executing in room {room_id} with args: {arguments}")
        # Remove JSON parsing as arguments are already a dict
        # try:
        #     parsed_arguments = json.loads(arguments)
        # except json.JSONDecodeError as e:
        #     logger.error(f"SendReplyTool: Failed to parse arguments JSON: {arguments}. Error: {e}")
        #     return ToolResult(status="failure", error_message=f"Invalid arguments format: {e}", result_for_llm_history=f"[Tool Error: send_reply failed to parse arguments: {e}]")

        parsed_arguments = arguments # Use arguments directly

        text = parsed_arguments.get("text")
        reply_to_event_id_arg = parsed_arguments.get("reply_to_event_id")

        resolved_reply_to_event_id = reply_to_event_id_arg
        if reply_to_event_id_arg == "$event:last_user_message" and last_user_event_id:
            resolved_reply_to_event_id = last_user_event_id
        elif reply_to_event_id_arg == "$event:last_user_message" and not last_user_event_id:
            return ToolResult(
                status="failure",
                result_for_llm_history="[Tool send_reply failed: LLM requested reply to last user message, but no last_user_event_id was available in context.]",
                error_message="Cannot reply to $event:last_user_message; context for last_user_event_id is missing."
            )

        if not text or not resolved_reply_to_event_id:
            return ToolResult(
                status="failure",
                result_for_llm_history=f"[Tool send_reply failed: Missing required arguments. Provided: text='{text}', reply_to_event_id='{resolved_reply_to_event_id}']",
                error_message="Missing 'text' or 'reply_to_event_id' argument for send_reply tool."
            )

        send_command = SendReplyCommand(
            room_id=room_id,
            text=text,
            reply_to_event_id=resolved_reply_to_event_id
        )
        return ToolResult(
            status="success",
            result_for_llm_history="[Tool send_reply executed: Reply message queued.]",
            commands_to_publish=[send_command]
        )
