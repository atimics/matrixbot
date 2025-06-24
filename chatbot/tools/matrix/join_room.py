"""
Join Matrix Room Tool - Join Matrix Rooms

Tool for joining Matrix rooms by room ID or alias.
Uses ServiceRegistry abstraction for clean platform integration.
"""

import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class JoinMatrixRoomTool(ToolInterface):
    """
    Tool for joining Matrix rooms by room ID or alias.
    """

    @property
    def name(self) -> str:
        return "join_matrix_room"

    @property
    def description(self) -> str:
        return "Join a Matrix room by room ID or alias. Use this when you want to join a new room that you're not currently in."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "room_identifier": "string - The room ID (!room:server.com) or alias (#room:server.com) to join",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Matrix room join action using ServiceRegistry.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Get Matrix observer from service registry (for now, until we have a room management service)
        matrix_observer = context.service_registry.get_service("matrix_observer")
        if not matrix_observer:
            error_msg = "Matrix observer not available in ServiceRegistry."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        room_identifier = params.get("room_identifier")

        if not room_identifier:
            error_msg = "Missing required parameter: room_identifier"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Use the observer's join_room method
            result = await matrix_observer.join_room(room_identifier)
            logger.info(f"Matrix observer join_room returned: {result}")

            if result.get("success"):
                room_id = result.get("room_id", room_identifier)
                success_msg = f"Successfully joined Matrix room {room_id}"
                logger.info(success_msg)

                return {
                    "status": "success",
                    "message": success_msg,
                    "room_id": room_id,
                    "room_identifier": room_identifier,
                    "timestamp": time.time(),
                }
            else:
                error_msg = f"Failed to join Matrix room: {result.get('error', 'unknown error')}"
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
