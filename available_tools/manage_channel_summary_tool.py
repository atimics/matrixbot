import logging
import os
from typing import Dict, Any, List, Optional

from tool_base import AbstractTool, ToolResult
from event_definitions import BaseEvent # Assuming RequestAISummaryCommand will be a BaseEvent
# We need to define RequestAISummaryCommand in event_definitions.py
# For now, let's create a placeholder or assume it exists.

# Placeholder for the command, proper definition should be in event_definitions.py
class RequestAISummaryCommand(BaseEvent):
    event_type: str = "request_ai_summary_command"
    room_id: str
    force_update: bool = False
    messages_to_summarize: Optional[List[Dict[str, Any]]] = None # Changed from List[str]

# Assuming database.py has a get_summary function
# This might need to be adjusted if database.py is not in the same directory or path
# For now, we assume it can be imported directly if it's in the Python path.
# try:
#     import database
# except ImportError:
#     # This is a fallback if direct import fails, 
#     # depending on project structure, a more robust import might be needed.
#     logging.warning("ManageChannelSummaryTool: Could not import 'database' module directly.")
#     # A mock or dummy database object could be used for linting/type-checking if needed
#     class MockDB:
#         def get_summary(self, room_id: str) -> Optional[tuple[Optional[str], Optional[str]]]:
#             return None, None
#     database = MockDB()

import database # Use absolute import assuming root is in PYTHONPATH

logger = logging.getLogger(__name__)

class ManageChannelSummaryTool(AbstractTool):
    """Manages the persistent summary of the current conversation channel."""

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "manage_channel_summary",
                "description": "Manages the persistent summary of the current conversation channel. Use 'request_update' to ask for the summary to be updated with recent conversation. Use 'get_current' to retrieve the latest saved summary.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string", 
                            "enum": ["request_update", "get_current"],
                            "description": "The action to perform: 'request_update' to trigger a new summary generation, or 'get_current' to fetch the existing one."
                        },
                        # room_id is implicitly available to the execute method, so not needed as an LLM param.
                        # However, the spec asks for it. Let's keep it for now.
                        "room_id": {
                            "type": "string",
                            "description": "The ID of the room for which to manage the summary. This should match the current room."
                        }
                    },
                    "required": ["action", "room_id"]
                }
            }
        }

    async def execute(
        self,
        room_id: str, # This is the actual room_id from the context
        arguments: Dict[str, Any],
        tool_call_id: Optional[str],
        llm_provider_info: Dict[str, Any],
        conversation_history_snapshot: List[Dict[str, Any]],
        last_user_event_id: Optional[str]
    ) -> ToolResult:
        action = arguments.get("action")
        llm_provided_room_id = arguments.get("room_id")

        # Optional: Validate llm_provided_room_id against the context room_id
        if llm_provided_room_id and llm_provided_room_id != room_id:
            logger.warning(f"ManageChannelSummaryTool: LLM provided room_id '{llm_provided_room_id}' does not match context room_id '{room_id}'. Using context room_id.")
            # Decide if this is a failure or just a warning. For now, proceed with context room_id.

        if action == "request_update":
            # The conversation_history_snapshot is the most up-to-date history available to the tool.
            # This is what should be summarized.
            summary_command = RequestAISummaryCommand(
                room_id=room_id, 
                force_update=True, # LLM explicitly requested an update
                messages_to_summarize=conversation_history_snapshot
            )
            return ToolResult(
                status="success",
                result_for_llm_history="[Tool manage_channel_summary(action=request_update) executed: Channel summary update requested. This will be processed asynchronously.]",
                commands_to_publish=[summary_command]
            )
        elif action == "get_current":
            try:
                summary_text, _ = database.get_summary(room_id) # Assuming get_summary returns (text, last_event_id) or (None, None)
            except Exception as e:
                logger.error(f"ManageChannelSummaryTool: Error calling database.get_summary for room {room_id}: {e}")
                return ToolResult(
                    status="failure",
                    result_for_llm_history=f"[Tool manage_channel_summary(action=get_current) failed: Error accessing summary data.]",
                    error_message=f"Failed to retrieve summary from database: {e}"
                )
            
            return ToolResult(
                status="success",
                result_for_llm_history=f"[Tool manage_channel_summary(action=get_current) executed: Current channel summary is: '{summary_text or 'Not available'}']"
                # No data_for_followup_llm needed here, the summary is in the history.
            )
        else:
            return ToolResult(
                status="failure",
                result_for_llm_history=f"[Tool manage_channel_summary failed: Invalid action '{action}'. Must be 'request_update' or 'get_current'.]",
                error_message=f"Invalid action specified: {action}. Allowed actions are 'request_update' or 'get_current'."
            )
