"""
Leave Matrix Room Tool - Leave Matrix Rooms

Tool for leaving Matrix rooms.
Uses ServiceRegistry abstraction for clean platform integration.
"""

import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class LeaveMatrixRoomTool(ToolInterface):
    """
    Tool for leaving Matrix rooms.
    """

    @property
    def name(self) -> str:
        return "leave_matrix_room"

    @property
    def description(self) -> str:
        return "Leave a Matrix room. Use this when you want to stop participating in a room."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "room_id": "string - The room ID to leave",
            "reason": "string (optional) - Reason for leaving the room",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Matrix room leave action using ServiceRegistry.
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
        reason = params.get("reason", "Leaving room")

        if not room_id:
            error_msg = "Missing required parameter: room_id"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Use the observer's leave_room method
            result = await matrix_observer.leave_room(room_id, reason)
            logger.info(f"Matrix observer leave_room returned: {result}")

            if result.get("success"):
                success_msg = f"Successfully left Matrix room {room_id}"
                logger.info(success_msg)

                return {
                    "status": "success",
                    "message": success_msg,
                    "room_id": room_id,
                    "reason": reason,
                    "timestamp": time.time(),
                }
            else:
                error_msg = f"Failed to leave Matrix room: {result.get('error', 'unknown error')}"
                logger.error(error_msg)
                return {
                    "status": "failure",
                    "error": error_msg,
                    "timestamp": time.time(),
                }

        except Exception as e:
            error_msg = f"Error executing {self.name}: {str(e)}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
