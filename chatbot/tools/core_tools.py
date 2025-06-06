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
        return {}

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the wait action.
        """
        duration = params.get("duration", 1.0)

        # Validate and sanitize duration
        try:
            duration = float(duration)
            if duration < 0:
                duration = 1.0
                logger.warning(
                    "Negative duration provided for wait tool. Using default 1.0s."
                )
        except (ValueError, TypeError):
            logger.warning(
                f"Invalid duration '{params.get('duration')}' for wait tool. Using default 1.0s."
            )
            duration = 1.0

        await asyncio.sleep(duration)

        message = f"Waited {duration} seconds and observed the current state."
        logger.info(message)

        return {
            "status": "success",
            "message": message,
            "timestamp": time.time(),
            "duration": duration,
        }
