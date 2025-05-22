import logging
import os
import asyncio
from typing import Dict, Any, List, Optional

from pydantic import BaseModel, ValidationError
from tool_base import AbstractTool, ToolResult
from event_definitions import RequestAISummaryCommand, HistoricalMessage  # Updated imports
from database import SummaryData  # Import SummaryData

import database  # Use absolute import assuming root is in PYTHONPATH

logger = logging.getLogger(__name__)

class ManageChannelSummaryTool(AbstractTool):
    """Tool to manage channel summaries, either by requesting an update or fetching the current one."""

    class ArgsModel(BaseModel):
        action: str
        room_id: Optional[str] = None

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "manage_channel_summary",
                "description": "Manages the summary for the current channel. Can request an AI-generated update or fetch the existing summary.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["request_update", "get_current"],
                            "description": "The action to perform: 'request_update' to trigger a new summary generation, or 'get_current' to fetch the existing one."
                        },
                        "room_id": { # Optional: LLM might provide it, but tool should use context room_id
                            "type": "string",
                            "description": "Optional: The ID of the room for which to manage the summary. If provided, it should match the current room context."
                        }
                    },
                    "required": ["action"]
                }
            }
        }

    async def execute(
        self,
        room_id: str, # This is the actual room_id from the context
        *, # Make subsequent arguments keyword-only
        db_path: str, # Injected by ToolExecutionService
        arguments: Dict[str, Any],
        tool_call_id: Optional[str],
        llm_provider_info: Dict[str, Any],
        conversation_history_snapshot: List[Dict[str, Any]],
        last_user_event_id: Optional[str]
    ) -> ToolResult:
        try:
            args = self.ArgsModel(**arguments)
        except ValidationError as ve:
            logger.warning(f"ManageChannelSummaryTool: Argument validation failed: {ve}")
            return ToolResult(
                status="failure",
                result_for_llm_history="[Tool manage_channel_summary failed: Invalid arguments]",
                error_message="Invalid arguments provided to manage_channel_summary",
            )

        action = args.action

        if action == "request_update":
            messages_for_summary_cmd: List[HistoricalMessage] = []
            last_event_id_in_snapshot: Optional[str] = None
            for msg_obj in conversation_history_snapshot: # Changed variable name for clarity
                try:
                    hist_msg: HistoricalMessage
                    if isinstance(msg_obj, HistoricalMessage):
                        hist_msg = msg_obj
                    else:
                        # Ensure msg_obj is a dict before attempting to unpack it
                        if not isinstance(msg_obj, dict):
                            logger.warning(f"ManageChannelSummaryTool: Skipping non-dict message: {type(msg_obj)}")
                            continue
                        hist_msg = HistoricalMessage(**msg_obj)
                    
                    messages_for_summary_cmd.append(hist_msg)

                    # Access event_id directly from the HistoricalMessage object
                    if hist_msg.role == "user" and hasattr(hist_msg, 'event_id') and hist_msg.event_id:
                        last_event_id_in_snapshot = hist_msg.event_id
                except Exception as e:
                    logger.warning(f"ManageChannelSummaryTool: Could not convert or process message: {msg_obj}. Error: {e}")
            
            summary_command = RequestAISummaryCommand(
                room_id=room_id, 
                force_update=True, # Changed from force_generation to force_update
                messages_to_summarize=messages_for_summary_cmd,
                last_event_id_in_messages=last_event_id_in_snapshot or last_user_event_id # Fallback
            )
            return ToolResult(
                status="success",
                result_for_llm_history="AI summary update requested for this channel.",
                commands_to_publish=[summary_command]
            )
        elif action == "get_current":
            try:
                # database.get_summary returns a tuple: (summary_text, last_event_id_summarized) or None
                summary_details_tuple = await asyncio.to_thread(database.get_summary, db_path, room_id)
            except Exception as e:
                logger.error(f"ManageChannelSummaryTool: Error calling database.get_summary for room {room_id}: {e}")
                return ToolResult(
                    status="failure",
                    result_for_llm_history=f"[Tool manage_channel_summary(action=get_current) failed: Error accessing database for room {room_id}.]",
                    error_message=f"Database error fetching summary for room {room_id}: {str(e)}"
                )
            
            if summary_details_tuple:
                summary_text, last_event_id_summarized = summary_details_tuple
                # Use SummaryData fields
                return ToolResult(
                    status="success",
                    result_for_llm_history=f"Current summary (last updated for event {last_event_id_summarized}):\\n{summary_text}"
                )
            else:
                return ToolResult(
                    status="success",
                    result_for_llm_history="No summary is currently available for this channel."
                )
        else:
            return ToolResult(
                status="failure",
                result_for_llm_history=f"[Tool manage_channel_summary failed: Invalid action '{action}']",
                error_message=f"Invalid action specified: {action}. Must be 'request_update' or 'get_current'."
            )
