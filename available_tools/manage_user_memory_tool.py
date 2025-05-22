import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime # Ensure datetime is imported
from pydantic import BaseModel, ValidationError

from tool_base import AbstractTool, ToolResult
import database  # Assuming database.py is in the PYTHONPATH

logger = logging.getLogger(__name__)

class ManageUserMemoryTool(AbstractTool):
    """Manages persistent memories about users."""

    class ArgsModel(BaseModel):
        action: str
        user_id: str
        memory_text: Optional[str] = None
        memory_id: Optional[int] = None

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "manage_user_memory",
                "description": "Manages persistent memories about users (e.g., preferences, past interactions, sentiment notes).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["add", "get", "list", "delete"],
                            "description": "The action to perform: 'add' a new memory, 'get' or 'list' existing memories for a user, or 'delete' a specific memory."
                        },
                        "user_id": {
                            "type": "string",
                            "description": "The user ID (e.g., '@username:homeserver.org') to associate the memory with."
                        },
                        "memory_text": {
                            "type": "string",
                            "description": "The text of the memory to add. Required if action is 'add'."
                        },
                        "memory_id": {
                            "type": "integer",
                            "description": "The ID of the memory to delete. Required if action is 'delete'."
                        }
                    },
                    "required": ["action", "user_id"]
                }
            }
        }

    async def execute(
        self,
        room_id: str, # Not directly used by this tool but part of the signature
        arguments: Dict[str, Any],
        tool_call_id: Optional[str],
        llm_provider_info: Dict[str, Any],
        conversation_history_snapshot: List[Dict[str, Any]],
        last_user_event_id: Optional[str],
        db_path: Optional[str] = None
    ) -> ToolResult:
        tool_name = self.get_definition()['function']['name']

        try:
            args = self.ArgsModel(**arguments)
        except ValidationError as ve:
            logger.warning(f"{tool_name}: Argument validation failed: {ve}")
            return ToolResult(
                status="failure",
                result_for_llm_history=f"[Tool {tool_name} failed: Invalid arguments.]",
                error_message="Invalid arguments provided to manage_user_memory"
            )

        action = args.action
        user_id = args.user_id
        memory_text = args.memory_text
        memory_id = args.memory_id

        if not db_path:
            logger.error(f"{tool_name}: db_path is not configured.")
            return ToolResult(
                status="failure",
                result_for_llm_history=f"[Tool {tool_name} failed: Database path not configured.]",
                error_message="Database path not configured for the tool."
            )
        
        if not user_id:
            return ToolResult(
                status="failure",
                result_for_llm_history=f"[Tool {tool_name} failed: Missing required argument 'user_id'.]",
                error_message="Missing required argument: user_id"
            )

        try:
            state_updates = None
            if action == "add":
                if not memory_text:
                    return ToolResult(
                        status="failure",
                        result_for_llm_history=f"[Tool {tool_name}(action=add) failed: Missing 'memory_text' argument.]",
                        error_message="Missing required argument: memory_text for action 'add'"
                    )
                await asyncio.to_thread(database.add_user_memory, db_path, user_id, memory_text)
                logger.info(f"{tool_name}: Added memory for user '{user_id}'.")
                state_updates = {f"{tool_name}.last_action": f"Added memory for {user_id}"}
                return ToolResult(
                    status="success",
                    result_for_llm_history=f"[Tool {tool_name}(action=add) executed: Memory added for user '{user_id}'.]",
                    state_updates=state_updates
                )
            elif action == "get" or action == "list": # 'get' and 'list' are functionally the same for this tool
                memories = await asyncio.to_thread(database.get_user_memories, db_path, user_id)
                if memories:
                    # Corrected timestamp formatting
                    formatted_memories = "\n".join([f"- ID {mem[0]}: {mem[2]} (Noted: {datetime.fromtimestamp(mem[3]).strftime('%Y-%m-%d %H:%M')})" for mem in memories])
                    logger.info(f"{tool_name}: Fetched memories for user '{user_id}'.")
                    return ToolResult(
                        status="success",
                        result_for_llm_history=f"[Tool {tool_name}(action={action}) executed: Memories for user '{user_id}':\n{formatted_memories}]"
                    )
                else:
                    logger.info(f"{tool_name}: No memories found for user '{user_id}'.")
                    return ToolResult(
                        status="success",
                        result_for_llm_history=f"[Tool {tool_name}(action={action}) executed: No memories found for user '{user_id}'.]"
                    )
            elif action == "delete":
                if memory_id is None: # Check for None explicitly, as 0 could be a valid ID if not auto-incrementing from 1
                    return ToolResult(
                        status="failure",
                        result_for_llm_history=f"[Tool {tool_name}(action=delete) failed: Missing 'memory_id' argument.]",
                        error_message="Missing required argument: memory_id for action 'delete'"
                    )
                await asyncio.to_thread(database.delete_user_memory, db_path, memory_id)
                logger.info(f"{tool_name}: Deleted memory with ID '{memory_id}' for user '{user_id}'.")
                state_updates = {f"{tool_name}.last_action": f"Deleted memory ID {memory_id} for {user_id}"}
                return ToolResult(
                    status="success",
                    result_for_llm_history=f"[Tool {tool_name}(action=delete) executed: Memory with ID '{memory_id}' deleted for user '{user_id}'.]",
                    state_updates=state_updates
                )
            else:
                logger.warning(f"{tool_name}: Invalid action '{action}'.")
                return ToolResult(
                    status="failure",
                    result_for_llm_history=f"[Tool {tool_name} failed: Invalid action '{action}'. Must be 'add', 'get', 'list', or 'delete'.]",
                    error_message=f"Invalid action specified: {action}. Must be 'add', 'get', 'list', or 'delete'."
                )
        except Exception as e:
            logger.error(f"{tool_name}: Error during action '{action}' for user '{user_id}': {e}", exc_info=True)
            return ToolResult(
                status="failure",
                result_for_llm_history=f"[Tool {tool_name}(action={action}) for user '{user_id}' failed due to an internal error.]",
                error_message=f"Error performing action '{action}' for user '{user_id}': {str(e)}"
            )
