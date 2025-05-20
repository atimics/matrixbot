from typing import Dict, Any, List, Optional
import logging

from tool_base import AbstractTool, ToolResult

logger = logging.getLogger(__name__)

class DoNotRespondTool(AbstractTool):
    """Tool to explicitly decide not to send a message or perform any other visible action."""

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "do_not_respond",
                "description": "Take no action and send no message in response to the user's input. Use this if no reply or other action is necessary at this time.",
                "parameters": {
                    "type": "object",
                    "properties": {}, # No parameters
                    "required": []
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
        logger.info(f"DoNotRespondTool: Executing in room {room_id} for tool_call_id {tool_call_id}. No action will be taken as per instruction.")
        return ToolResult(
            status="success",
            result_for_llm_history="[Tool 'do_not_respond' executed: No action taken, bot will not send a message.]",
            commands_to_publish=None, # Explicitly None, or empty list [] is also fine.
            error_message=None,
            data_for_followup_llm=None,
            state_updates=None
        )
