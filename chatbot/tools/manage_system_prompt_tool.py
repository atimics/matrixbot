import logging
from typing import Dict, Any, List, Optional

from pydantic import BaseModel, ValidationError
from tool_base import AbstractTool, ToolResult
import database  # Assuming database.py is in the PYTHONPATH

logger = logging.getLogger(__name__)

class ManageSystemPromptTool(AbstractTool):
    """Manages the AI's core system prompt. Allows fetching or updating it."""

    class ArgsModel(BaseModel):
        action: str
        new_prompt_text: Optional[str] = None

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "manage_system_prompt",
                "description": "Manages the AI\'s core system prompt. Allows fetching or updating it.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["get_current", "update"],
                            "description": "The action to perform: 'get_current' to fetch the current system prompt, or 'update' to change it."
                        },
                        "new_prompt_text": {
                            "type": "string",
                            "description": "The new text for the system prompt. Required if action is 'update'."
                        }
                    },
                    "required": ["action"]
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
        try:
            args = self.ArgsModel(**arguments)
        except ValidationError as ve:
            logger.warning(f"ManageSystemPromptTool: Argument validation failed: {ve}")
            return ToolResult(
                status="failure",
                result_for_llm_history="[Tool manage_system_prompt failed: Invalid arguments.]",
                error_message="Invalid arguments provided to manage_system_prompt"
            )

        action = args.action
        new_prompt_text = args.new_prompt_text

        if not db_path:
            logger.error("ManageSystemPromptTool: db_path is not configured.")
            return ToolResult(
                status="failure",
                result_for_llm_history="[Tool manage_system_prompt failed: Database path not configured.]",
                error_message="Database path not configured for the tool."
            )

        try:
            if action == "get_current":
                prompt_name = "system_default"
                current_prompt_tuple = await database.get_prompt(db_path, prompt_name)
                # Check if the prompt exists and has content
                if current_prompt_tuple and current_prompt_tuple[0] is not None:
                    current_prompt = current_prompt_tuple[0]
                    logger.info(f"ManageSystemPromptTool: Fetched system prompt '{prompt_name}'.")
                    return ToolResult(
                        status="success",
                        result_for_llm_history=f"[Tool manage_system_prompt(action=get_current) executed: Current system prompt is: '{current_prompt}']"
                    )
                else:
                    logger.warning(f"ManageSystemPromptTool: System prompt '{prompt_name}' not found.")
                    return ToolResult(
                        status="success", # Success from tool perspective, but prompt not found
                        result_for_llm_history=f"[Tool manage_system_prompt(action=get_current) executed: System prompt '{prompt_name}' not found.]"
                    )
            elif action == "update":
                if not new_prompt_text:
                    logger.warning("ManageSystemPromptTool: Action 'update' called without 'new_prompt_text'.")
                    return ToolResult(
                        status="failure",
                        result_for_llm_history="[Tool manage_system_prompt(action=update) failed: Missing 'new_prompt_text' argument.]",
                        error_message="Missing required argument: new_prompt_text for action 'update'"
                    )
                prompt_name = "system_default"
                await database.update_prompt(db_path, prompt_name, new_prompt_text)
                logger.info(f"ManageSystemPromptTool: Updated system prompt '{prompt_name}'.")
                return ToolResult(
                    status="success",
                    result_for_llm_history=f"[Tool manage_system_prompt(action=update) executed: System prompt '{prompt_name}' updated successfully.]",
                    state_updates={"manage_system_prompt.last_action": f"updated to: '{new_prompt_text}'"}
                )
            else:
                logger.warning(f"ManageSystemPromptTool: Invalid action '{action}'.")
                return ToolResult(
                    status="failure",
                    result_for_llm_history=f"[Tool manage_system_prompt failed: Invalid action '{action}'. Must be 'get_current' or 'update'.]",
                    error_message=f"Invalid action specified: {action}. Must be 'get_current' or 'update'."
                )
        except Exception as e:
            logger.error(f"ManageSystemPromptTool: Error during action '{action}': {e}", exc_info=True)
            return ToolResult(
                status="failure",
                result_for_llm_history=f"[Tool manage_system_prompt(action={action}) failed due to an internal error.]",
                error_message=f"Error performing action '{action}': {str(e)}"
            )
