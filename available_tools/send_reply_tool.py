\
from typing import Dict, Any, List, Optional

from tool_base import AbstractTool, ToolResult
from event_definitions import SendReplyCommand

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
        arguments: Dict[str, Any],
        tool_call_id: Optional[str],
        llm_provider_info: Dict[str, Any],
        conversation_history_snapshot: List[Dict[str, Any]],
        last_user_event_id: Optional[str]
    ) -> ToolResult:
        text = arguments.get("text")
        reply_to_event_id_arg = arguments.get("reply_to_event_id")

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
