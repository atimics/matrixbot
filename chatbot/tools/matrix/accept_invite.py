"""
Accept Matrix Invite Tool - Accept Matrix Room Invitations

Tool for accepting Matrix room invitations.
Uses ServiceRegistry abstraction for clean platform integration.
"""

import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class AcceptMatrixInviteTool(ToolInterface):
    """
    Tool for accepting Matrix room invitations.
    """

    @property
    def name(self) -> str:
        return "accept_matrix_invite"

    @property
    def description(self) -> str:
        return "Accept a pending Matrix room invitation and join the room. Use this when you want to join a room you've been invited to. You can see pending invites in the world state."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "room_id": "string - The room ID of the invitation to accept (e.g., !xmpqAkRnpDKKtcUWrC:chat.ratimics.com)",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Matrix invite acceptance action using ServiceRegistry.
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

        if not room_id:
            error_msg = "Missing required parameter: room_id"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Use the observer's accept_invite method
            result = await matrix_observer.accept_invite(room_id)
            logger.info(f"Matrix observer accept_invite returned: {result}")

            if result.get("success"):
                success_msg = (
                    f"Successfully accepted Matrix room invitation for {room_id}"
                )
                logger.info(success_msg)

                return {
                    "status": "success",
                    "message": success_msg,
                    "room_id": room_id,
                    "timestamp": time.time(),
                }
            else:
                error_msg = f"Failed to accept Matrix room invitation: {result.get('error', 'unknown error')}"
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
