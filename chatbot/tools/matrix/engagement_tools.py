"""
Matrix engagement tools - React to messages using the service layer.
"""
import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class ReactToMatrixMessageTool(ToolInterface):
    """
    Tool for reacting to Matrix messages with emoji using the service layer.
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
            "channel_id": "string - The room ID where the message is located",
            "event_id": "string - The event ID of the message to react to",
            "emoji": "string - The emoji to react with (e.g., '👍', '❤️', '😀')",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Matrix reaction action using the service layer.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Get Matrix service from service registry
        messaging_service = context.get_messaging_service("matrix")
        if not messaging_service or not await messaging_service.is_available():
            error_msg = "Matrix service is not available."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        channel_id = params.get("channel_id")
        event_id = params.get("event_id")
        emoji = params.get("emoji")

        missing_params = []
        if not channel_id:
            missing_params.append("channel_id")
        if not event_id:
            missing_params.append("event_id")
        if not emoji:
            missing_params.append("emoji")

        if missing_params:
            error_msg = f"Missing required parameters: {', '.join(missing_params)}"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Use the service layer
            result = await messaging_service.react_to_message(room_id, event_id, emoji)
            
            # Log action in world state regardless of success/failure
            if context.world_state_manager:
                if result.get("status") == "success":
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"room_id": room_id, "event_id": event_id, "emoji": emoji},
                        result="success",
                    )
                else:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"room_id": room_id, "event_id": event_id, "emoji": emoji},
                        result=f"failure: {result.get('error', 'unknown error')}",
                    )
            
            return result

        except Exception as e:
            error_msg = f"Error executing {self.name}: {str(e)}"
            logger.exception(error_msg)

            # Record this action failure in world state
            if context.world_state_manager:
                context.world_state_manager.add_action_result(
                    action_type=self.name,
                    parameters={"room_id": room_id, "event_id": event_id, "emoji": emoji},
                    result=f"failure: {str(e)}",
                )

            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
