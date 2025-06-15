"""
Matrix room management tools - Join, leave, and manage room invitations using the service layer.
"""
import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class JoinMatrixRoomTool(ToolInterface):
    """
    Tool for joining Matrix rooms by room ID or alias using the service layer.
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
        Execute the Matrix room join action using the service layer.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Get Matrix service from service registry
        messaging_service = context.get_messaging_service("matrix")
        if not messaging_service or not await messaging_service.is_available():
            error_msg = "Matrix service is not available."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        room_identifier = params.get("room_identifier")

        if not room_identifier:
            error_msg = "Missing required parameter: room_identifier"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Use the service layer
            result = await messaging_service.join_room(room_identifier)
            return result

        except Exception as e:
            error_msg = f"Error executing {self.name}: {str(e)}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class LeaveMatrixRoomTool(ToolInterface):
    """
    Tool for leaving Matrix rooms using the service layer.
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
        Execute the Matrix room leave action using the service layer.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Get Matrix service from service registry
        messaging_service = context.get_messaging_service("matrix")
        if not messaging_service or not await messaging_service.is_available():
            error_msg = "Matrix service is not available."
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
            # Use the service layer
            result = await messaging_service.leave_room(room_id, reason)
            return result

        except Exception as e:
            error_msg = f"Error executing {self.name}: {str(e)}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class AcceptMatrixInviteTool(ToolInterface):
    """
    Tool for accepting Matrix room invitations using the service layer.
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
        Execute the Matrix invite acceptance action using the service layer.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Get Matrix service from service registry
        messaging_service = context.get_messaging_service("matrix")
        if not messaging_service or not await messaging_service.is_available():
            error_msg = "Matrix service is not available."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        room_id = params.get("room_id")

        if not room_id:
            error_msg = "Missing required parameter: room_id"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Use the service layer
            result = await messaging_service.accept_invite(room_id)
            return result

        except Exception as e:
            error_msg = f"Error executing {self.name}: {str(e)}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class IgnoreMatrixInviteTool(ToolInterface):
    """
    Tool for ignoring/declining Matrix room invitations using the service layer.
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
        Execute the Matrix invite ignoring action using the service layer.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Get Matrix service from service registry
        messaging_service = context.get_messaging_service("matrix")
        if not messaging_service or not await messaging_service.is_available():
            error_msg = "Matrix service is not available."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        room_id = params.get("room_id")
        reason = params.get("reason", "No reason provided")

        if not room_id:
            error_msg = "Missing required parameter: room_id"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Use the service layer
            result = await messaging_service.ignore_invite(room_id)
            if result.get("status") == "success":
                result["reason"] = reason
            return result

        except Exception as e:
            error_msg = f"Error executing {self.name}: {str(e)}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
