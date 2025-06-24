"""
React to Matrix Message Tool - React to Matrix Messages with Emoji

Tool for reacting to Matrix messages with emoji.
Uses ServiceRegistry abstraction for clean platform integration.
"""

import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class ReactToMatrixMessageTool(ToolInterface):
    """
    Tool for reacting to Matrix messages with emoji.
    """

    @property
    def name(self) -> str:
        return "react_to_matrix_message"

    @property
    def description(self) -> str:
        return "React to a Matrix message with an emoji. Use this to express emotions or acknowledgments without sending a full message."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "room_id": "string - The room ID where the message is located",
            "event_id": "string - The event ID of the message to react to",
            "emoji": "string - The emoji to react with (e.g., '👍', '❤️', '😀')",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Matrix reaction action using ServiceRegistry.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Get Matrix observer from service registry
        matrix_observer = context.service_registry.get_service("matrix_observer")
        if not matrix_observer:
            error_msg = "Matrix observer not available in ServiceRegistry."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        room_id = params.get("room_id")
        event_id = params.get("event_id")
        emoji = params.get("emoji")

        missing_params = []
        if not room_id:
            missing_params.append("room_id")
        if not event_id:
            missing_params.append("event_id")
        if not emoji:
            missing_params.append("emoji")

        if missing_params:
            error_msg = f"Missing required parameters: {', '.join(missing_params)}"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Use the observer's react_to_message method
            result = await matrix_observer.react_to_message(
                room_id, event_id, emoji
            )
            logger.info(f"Matrix observer react_to_message returned: {result}")

            if result.get("success"):
                success_msg = f"Successfully reacted to message {event_id} with {emoji}"
                logger.info(success_msg)

                # Record this action in world state
                if context.world_state_manager:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={
                            "room_id": room_id,
                            "event_id": event_id,
                            "emoji": emoji,
                        },
                        result="success",
                    )

                return {
                    "status": "success",
                    "message": success_msg,
                    "room_id": room_id,
                    "event_id": event_id,
                    "emoji": emoji,
                    "timestamp": time.time(),
                }
            else:
                error_msg = f"Failed to react to Matrix message: {result.get('error', 'unknown error')}"
                logger.error(error_msg)

                # Record this action failure in world state
                if context.world_state_manager:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={
                            "room_id": room_id,
                            "event_id": event_id,
                            "emoji": emoji,
                        },
                        result=f"failure: {result.get('error', 'unknown error')}",
                    )

                return {
                    "status": "failure",
                    "error": error_msg,
                    "timestamp": time.time(),
                }

        except Exception as e:
            error_msg = f"Error executing {self.name}: {str(e)}"
            logger.exception(error_msg)

            # Record this action failure in world state
            if context.world_state_manager:
                context.world_state_manager.add_action_result(
                    action_type=self.name,
                    parameters={
                        "room_id": room_id,
                        "event_id": event_id,
                        "emoji": emoji,
                    },
                    result=f"failure: {str(e)}",
                )

            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
