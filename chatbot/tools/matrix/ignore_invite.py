"""
Ignore Matrix Invite Tool - Ignore/Decline Matrix Room Invitations

Tool for ignoring or declining Matrix room invitations.
Uses ServiceRegistry abstraction for clean platform integration.
"""

import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class IgnoreMatrixInviteTool(ToolInterface):
    """
    Tool for ignoring/declining Matrix room invitations.
    """

    @property
    def name(self) -> str:
        return "ignore_matrix_invite"

    @property
    def description(self) -> str:
        return "Ignore or decline a pending Matrix room invitation. Use this when you don't want to join a room you've been invited to."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "room_id": "string - The room ID of the invitation to ignore/decline",
            "reason": "string (optional) - Optional reason for declining the invite"
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Matrix invite ignoring action using ServiceRegistry.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Extract and validate parameters
        room_id = params.get("room_id")
        reason = params.get("reason", "No reason provided")

        if not room_id:
            error_msg = "Missing required parameter: room_id"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Simply remove the invite from world state without accepting
            if hasattr(context, 'world_state_manager') and context.world_state_manager:
                removed = context.world_state_manager.remove_pending_matrix_invite(room_id)
                if removed:
                    success_msg = f"Successfully ignored Matrix room invitation for {room_id}"
                    logger.info(f"{success_msg}. Reason: {reason}")
                    
                    return {
                        "status": "success",
                        "message": success_msg,
                        "room_id": room_id,
                        "reason": reason,
                        "timestamp": time.time(),
                    }
                else:
                    error_msg = f"No pending invitation found for room {room_id}"
                    logger.warning(error_msg)
                    return {
                        "status": "failure", 
                        "error": error_msg,
                        "timestamp": time.time(),
                    }
            else:
                error_msg = "World state manager not available"
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
