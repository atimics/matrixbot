import logging
from typing import Dict, Any, List, Optional

from pydantic import BaseModel, ValidationError
from tool_base import AbstractTool, ToolResult
import database  # Assuming database.py is in the PYTHONPATH

logger = logging.getLogger(__name__)

class ManageSummarizationPromptTool(AbstractTool):
    """Manages the AI's summarization prompt. Allows fetching or updating it."""

    class ArgsModel(BaseModel):
        action: str
        new_prompt_text: Optional[str] = None

    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "manage_summarization_prompt",
                "description": "Manages the AI\'s summarization prompt. Allows fetching or updating it.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["get_current", "update"],
                            "description": "The action to perform: 'get_current' to fetch the current summarization prompt, or 'update' to change it."
                        },
                        "new_prompt_text": {
                            "type": "string",
                            "description": "The new text for the summarization prompt. Required if action is 'update'."
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
            logger.warning(f"ManageSummarizationPromptTool: Argument validation failed: {ve}")
            return ToolResult(
                status="failure",
                result_for_llm_history=f"[Tool {self.get_definition()['function']['name']} failed: Invalid arguments.]",
                error_message="Invalid arguments provided to manage_summarization_prompt"
            )

        action = args.action
        new_prompt_text = args.new_prompt_text
        prompt_name = "summarization_default"

        if not db_path:
            logger.error("ManageSummarizationPromptTool: db_path is not configured.")
            return ToolResult(
                status="failure",
                result_for_llm_history=f"[Tool {self.get_definition()['function']['name']} failed: Database path not configured.]",
                error_message="Database path not configured for the tool."
            )

        try:
            if action == "get_current":
                current_prompt_tuple = await database.get_prompt(db_path, prompt_name)
                if current_prompt_tuple:
                    current_prompt = current_prompt_tuple[0]
                    logger.info(f"ManageSummarizationPromptTool: Fetched summarization prompt '{prompt_name}'.")
                    return ToolResult(
                        status="success",
                        result_for_llm_history=f"[Tool {self.get_definition()['function']['name']}(action=get_current) executed: Current summarization prompt is: '{current_prompt}']"
                    )
                else:
                    logger.warning(f"ManageSummarizationPromptTool: Summarization prompt '{prompt_name}' not found.")
                    return ToolResult(
                        status="success",
                        result_for_llm_history=f"[Tool {self.get_definition()['function']['name']}(action=get_current) executed: Summarization prompt '{prompt_name}' not found.]"
                    )
            elif action == "update":
                if not new_prompt_text:
                    logger.warning("ManageSummarizationPromptTool: Action 'update' called without 'new_prompt_text'.")
                    return ToolResult(
                        status="failure",
                        result_for_llm_history=f"[Tool {self.get_definition()['function']['name']}(action=update) failed: Missing 'new_prompt_text' argument.]",
                        error_message="Missing required argument: new_prompt_text for action 'update'"
                    )
                await database.update_prompt(db_path, prompt_name, new_prompt_text)
                logger.info(f"ManageSummarizationPromptTool: Updated summarization prompt '{prompt_name}'.")
                return ToolResult(
                    status="success",
                    result_for_llm_history=f"[Tool {self.get_definition()['function']['name']}(action=update) executed: Summarization prompt '{prompt_name}' updated successfully.]"
                )
            else:
                logger.warning(f"ManageSummarizationPromptTool: Invalid action '{action}'.")
                return ToolResult(
                    status="failure",
                    result_for_llm_history=f"[Tool {self.get_definition()['function']['name']} failed: Invalid action '{action}'. Must be 'get_current' or 'update'.]",
                    error_message=f"Invalid action specified: {action}. Must be 'get_current' or 'update'."
                )
        except Exception as e:
            logger.error(f"ManageSummarizationPromptTool: Error during action '{action}': {e}", exc_info=True)
            return ToolResult(
                status="failure",
                result_for_llm_history=f"[Tool {self.get_definition()['function']['name']}(action={action}) failed due to an internal error.]",
                error_message=f"Error performing action '{action}': {str(e)}"
            )
