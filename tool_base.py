\
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Literal

from event_definitions import BaseEvent # Assuming BaseEvent is in event_definitions

class ToolResult(BaseModel):
    status: Literal["success", "failure", "requires_llm_followup"]
    result_for_llm_history: str
    commands_to_publish: Optional[List[BaseEvent]] = None
    error_message: Optional[str] = None
    data_for_followup_llm: Optional[Dict[str, Any]] = None

class AbstractTool(ABC):
    """Abstract base class for all tools."""

    @abstractmethod
    def get_definition(self) -> Dict[str, Any]:
        """
        Returns the JSON schema definition for the LLM.
        This definition informs the LLM how to use the tool.
        """
        pass

    @abstractmethod
    async def execute(
        self,
        room_id: str,
        arguments: Dict[str, Any],
        tool_call_id: Optional[str],
        llm_provider_info: Dict[str, Any],
        conversation_history_snapshot: List[Dict[str, Any]],
        last_user_event_id: Optional[str]
    ) -> ToolResult:
        """
        Executes the tool's logic.

        Args:
            room_id: The ID of the room where the tool is being executed.
            arguments: The arguments for the tool, as provided by the LLM.
            tool_call_id: The unique ID for this tool call.
            llm_provider_info: Information about the LLM that initiated the call.
            conversation_history_snapshot: A read-only copy of the current conversation history.
            last_user_event_id: The event ID of the latest user message in the processed batch.

        Returns:
            A ToolResult object detailing the outcome of the execution.
        """
        pass

# Pydantic BaseModel needs to be imported if not already available globally
# For ToolResult, we might need to import BaseModel from Pydantic
from pydantic import BaseModel
