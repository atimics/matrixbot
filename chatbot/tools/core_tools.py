"""
Core tools that don't depend on specific platforms.
"""
import asyncio
import logging
import time
from typing import Any, Dict

from .base import ActionContext, ToolInterface
from ..core.world_state import Message
from ..core.world_state import Message

logger = logging.getLogger(__name__)


class WaitTool(ToolInterface):
    """
    Tool for waiting/observing without taking action.
    """

    @property
    def name(self) -> str:
        return "wait"

    @property
    def description(self) -> str:
        return "Do nothing and wait until the next world update or observation cycle. Use this when no immediate action is needed or to see if new information becomes available."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "duration": {
                    "type": "number",
                    "description": "Duration to wait in seconds",
                    "default": 0
                }
            },
            "required": []
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the wait action by doing nothing, allowing the main processing
        loop to continue to its next natural cycle.
        """
        message = "Waited for the next observation cycle."
        logger.debug(message)

        return {
            "status": "success",
            "message": message,
            "timestamp": time.time(),
            "duration": 0,
        }


class LogInternalMonologueTool(ToolInterface):
    """
    A tool for the AI to record its internal thoughts or observations.
    """

    @property
    def name(self) -> str:
        return "log_internal_monologue"

    @property
    def description(self) -> str:
        return "Record a thought, observation, or internal monologue note to your private log. Use this when you have something to say but no external action is appropriate."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "thought": {
                    "type": "string",
                    "description": "The thought, observation, or reflection to be logged."
                }
            },
            "required": ["thought"]
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Executes the action by creating a special message in the world state.
        """
        thought = params.get("thought")
        if not thought:
            return {"status": "failure", "error": "Thought content cannot be empty."}

        if not context.world_state_manager:
            logger.warning("WorldStateManager not available. Cannot log internal monologue.")
            return {"status": "failure", "error": "World state manager not available."}
            
        try:
            # Define a dedicated internal channel ID
            internal_channel_id = "system:internal_monologue"

            # Create a message object for the monologue
            monologue_message = Message(
                id=f"monologue_{int(time.time() * 1000)}",
                channel_id=internal_channel_id,
                channel_type="internal",
                sender="SYSTEM_AI",
                content=thought,
                timestamp=time.time()
            )

            # Add this message to the world state
            context.world_state_manager.add_message(internal_channel_id, monologue_message)

            logger.debug(f"Logged internal monologue: '{thought[:100]}...'")

            return {
                "status": "success",
                "message": "Internal monologue logged successfully.",
                "timestamp": time.time()
            }
        except Exception as e:
            logger.error(f"Error logging internal monologue: {e}", exc_info=True)
            return {"status": "failure", "error": str(e)}
