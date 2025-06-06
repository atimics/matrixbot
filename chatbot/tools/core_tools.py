"""
Core tools that don't depend on specific platforms.
"""
import asyncio
import logging
import time
from typing import Any, Dict

from .base import ActionContext, ToolInterface

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
        # Allow optional duration parameter for waiting in seconds
        return {
            "type": "object",
            "properties": {
                "duration": {
                    "type": "number",
                    "description": "Duration to wait in seconds",
                    "default": 0
                }
            }
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the wait action by doing nothing, allowing the main processing
        loop to continue to its next natural cycle.
        """
        message = "Waited for the next observation cycle."
        logger.info(message)

        return {
            "status": "success",
            "message": message,
            "timestamp": time.time(),
            "duration": 0,
        }
