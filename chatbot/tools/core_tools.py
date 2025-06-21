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


class RequestProcessingCycleTool(ToolInterface):
    """
    Tool for the AI to explicitly request a new processing cycle.
    
    This tool allows the AI to request that its understanding of the world
    state be refreshed and a new processing cycle be triggered. This is useful
    when the AI has taken an action that changes the world state significantly
    and wants to re-evaluate the situation.
    """

    @property
    def name(self) -> str:
        return "request_reprocessing"

    @property
    def description(self) -> str:
        return "Request a fresh processing cycle to re-evaluate the current world state. Use this after taking significant actions that might change the context or when you need to reconsider your approach with updated information."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Reason for requesting reprocessing (e.g., 'posted_message', 'state_changed', 'need_fresh_perspective')"
                },
                "details": {
                    "type": "string", 
                    "description": "Additional details about why reprocessing is needed",
                    "default": ""
                }
            },
            "required": ["reason"]
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the reprocessing request by marking the world state as stale.
        """
        reason = params.get("reason", "explicit_request")
        details_str = params.get("details", "")
        
        if not context.processing_hub:
            logger.warning("Processing hub not available. Cannot request reprocessing.")
            return {"status": "failure", "error": "Processing hub not available."}
            
        try:
            # Mark state as stale with the provided reason
            details = {
                "tool_request": True,
                "timestamp": time.time()
            }
            if details_str:
                details["details"] = details_str
                
            context.processing_hub.mark_state_as_stale(
                f"ai_requested_{reason}",
                details
            )

            message = f"Requested reprocessing: {reason}"
            if details_str:
                message += f" - {details_str}"
                
            logger.debug(f"AI requested reprocessing: {reason}")

            return {
                "status": "success",
                "message": message,
                "timestamp": time.time(),
                "reason": reason
            }
        except Exception as e:
            logger.error(f"Error requesting reprocessing: {e}", exc_info=True)
            return {"status": "failure", "error": str(e)}
