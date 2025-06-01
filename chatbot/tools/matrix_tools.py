"""
Matrix platform-specific tools.
"""
import logging
import time
from typing import Any, Dict

from .base import ActionContext, ToolInterface
from ..utils.markdown_utils import format_for_matrix

logger = logging.getLogger(__name__)


class SendMatrixReplyTool(ToolInterface):
    """
    Tool for sending replies to specific messages in Matrix channels.
    """

    @property
    def name(self) -> str:
        return "send_matrix_reply"

    @property
    def description(self) -> str:
        return "Reply to a specific message in a Matrix channel. If reply_to_id is not provided, will send as a regular message to the channel."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "channel_id": "string (Matrix room ID) - The room where the reply should be sent",
            "content": "string - The message content to send as a reply (supports markdown formatting)",
            "reply_to_id": "string (optional) - The event ID of the message to reply to. If not provided, sends as regular message",
            "format_as_markdown": "boolean (optional, default: true) - Whether to format the content as markdown",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Matrix reply action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Check if Matrix integration is available
        if not context.matrix_observer:
            error_msg = "Matrix integration (observer) not configured."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        room_id = params.get("channel_id")
        content = params.get("content")
        reply_to_event_id = params.get("reply_to_id")
        format_as_markdown = params.get("format_as_markdown", True)

        missing_params = []
        if not room_id:
            missing_params.append("channel_id")
        if not content:
            missing_params.append("content")

        if missing_params:
            error_msg = f"Missing required parameters for Matrix reply: {', '.join(missing_params)}"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # If reply_to_id is missing but we have channel_id and content, fall back to regular message
        if not reply_to_event_id:
            logger.info(f"reply_to_id missing, falling back to regular message in {room_id}")
            try:
                # Format content if markdown is enabled
                if format_as_markdown:
                    formatted = format_for_matrix(content)
                    result = await context.matrix_observer.send_formatted_message(
                        room_id, formatted["plain"], formatted["html"]
                    )
                else:
                    result = await context.matrix_observer.send_message(room_id, content)
                
                logger.info(f"Matrix observer send_message returned: {result}")

                if result.get("success"):
                    event_id = result.get("event_id", "unknown")
                    success_msg = f"Sent Matrix message (fallback from reply) to {room_id} (event: {event_id})"
                    logger.info(success_msg)

                    return {
                        "status": "success",
                        "message": success_msg,
                        "event_id": event_id,
                        "room_id": room_id,
                        "sent_content": content,
                        "fallback_to_message": True,  # Indicate this was a fallback
                        "timestamp": time.time(),
                    }
                else:
                    error_msg = f"Failed to send Matrix message (fallback) via observer: {result.get('error', 'unknown error')}"
                    logger.error(error_msg)
                    return {
                        "status": "failure",
                        "error": error_msg,
                        "timestamp": time.time(),
                    }

            except Exception as e:
                error_msg = f"Error executing fallback message for {self.name}: {str(e)}"
                logger.exception(error_msg)
                return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Format content if markdown is enabled
            if format_as_markdown:
                formatted = format_for_matrix(content)
                result = await context.matrix_observer.send_formatted_reply(
                    room_id, formatted["plain"], formatted["html"], reply_to_event_id
                )
            else:
                result = await context.matrix_observer.send_reply(
                    room_id, content, reply_to_event_id
                )
            logger.info(f"Matrix observer send_reply returned: {result}")

            if result.get("success"):
                event_id = result.get("event_id", "unknown")
                success_msg = f"Sent Matrix reply to {room_id} (event: {event_id})"
                logger.info(success_msg)

                return {
                    "status": "success",
                    "message": success_msg,
                    "event_id": event_id,
                    "room_id": room_id,
                    "reply_to_event_id": reply_to_event_id,
                    "sent_content": content,  # For AI Blindness Fix
                    "timestamp": time.time(),
                }
            else:
                error_msg = f"Failed to send Matrix reply via observer: {result.get('error', 'unknown error')}"
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


class SendMatrixMessageTool(ToolInterface):
    """
    Tool for sending new messages to Matrix channels.
    """

    @property
    def name(self) -> str:
        return "send_matrix_message"

    @property
    def description(self) -> str:
        return "Send a new message to a Matrix channel. Use this when you want to start a new conversation or make an announcement."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "channel_id": "string (Matrix room ID) - The room where the message should be sent",
            "content": "string - The message content to send (supports markdown formatting)",
            "format_as_markdown": "boolean (optional, default: true) - Whether to format the content as markdown",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Matrix message action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Check if Matrix integration is available
        if not context.matrix_observer:
            error_msg = "Matrix integration (observer) not configured."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        room_id = params.get("channel_id")
        content = params.get("content")
        format_as_markdown = params.get("format_as_markdown", True)

        missing_params = []
        if not room_id:
            missing_params.append("channel_id")
        if not content:
            missing_params.append("content")

        if missing_params:
            error_msg = f"Missing required parameters for Matrix message: {', '.join(missing_params)}"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Format content if markdown is enabled
            if format_as_markdown:
                formatted = format_for_matrix(content)
                result = await context.matrix_observer.send_formatted_message(
                    room_id, formatted["plain"], formatted["html"]
                )
            else:
                result = await context.matrix_observer.send_message(room_id, content)
            
            logger.info(f"Matrix observer send_message returned: {result}")

            if result.get("success"):
                event_id = result.get("event_id", "unknown")
                success_msg = f"Sent Matrix message to {room_id} (event: {event_id})"
                logger.info(success_msg)

                return {
                    "status": "success",
                    "message": success_msg,
                    "event_id": event_id,
                    "room_id": room_id,
                    "sent_content": content,  # For AI Blindness Fix
                    "timestamp": time.time(),
                }
            else:
                error_msg = f"Failed to send Matrix message via observer: {result.get('error', 'unknown error')}"
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
        Execute the Matrix room join action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Check if Matrix integration is available
        if not context.matrix_observer:
            error_msg = "Matrix integration (observer) not configured."
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
            result = await context.matrix_observer.join_room(room_identifier)
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
        Execute the Matrix room leave action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Check if Matrix integration is available
        if not context.matrix_observer:
            error_msg = "Matrix integration (observer) not configured."
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
            result = await context.matrix_observer.leave_room(room_id, reason)
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


class AcceptMatrixInviteTool(ToolInterface):
    """
    Tool for accepting Matrix room invitations.
    """

    @property
    def name(self) -> str:
        return "accept_matrix_invite"

    @property
    def description(self) -> str:
        return "Accept a pending Matrix room invitation. Use this when you have been invited to a room and want to join it."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "room_id": "string - The room ID of the invitation to accept",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Matrix invite acceptance action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Check if Matrix integration is available
        if not context.matrix_observer:
            error_msg = "Matrix integration (observer) not configured."
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
            result = await context.matrix_observer.accept_invite(room_id)
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


class GetMatrixInvitesTool(ToolInterface):
    """
    Tool for retrieving pending Matrix room invitations.
    """

    @property
    def name(self) -> str:
        return "get_matrix_invites"

    @property
    def description(self) -> str:
        return "Get a list of pending Matrix room invitations. Use this to see which rooms you've been invited to."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {}

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Matrix invites retrieval action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Check if Matrix integration is available
        if not context.matrix_observer:
            error_msg = "Matrix integration (observer) not configured."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Use the observer's get_invites method
            result = await context.matrix_observer.get_invites()
            logger.info(f"Matrix observer get_invites returned: {result}")

            if result.get("success"):
                invites = result.get("invites", [])
                success_msg = (
                    f"Retrieved {len(invites)} pending Matrix room invitations"
                )
                logger.info(success_msg)

                return {
                    "status": "success",
                    "message": success_msg,
                    "invites": invites,
                    "invite_count": len(invites),
                    "timestamp": time.time(),
                }
            else:
                error_msg = f"Failed to retrieve Matrix room invitations: {result.get('error', 'unknown error')}"
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
        Execute the Matrix reaction action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Check if Matrix integration is available
        if not context.matrix_observer:
            error_msg = "Matrix integration (observer) not configured."
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
            result = await context.matrix_observer.react_to_message(room_id, event_id, emoji)
            logger.info(f"Matrix observer react_to_message returned: {result}")

            if result.get("success"):
                success_msg = f"Successfully reacted to message {event_id} with {emoji}"
                logger.info(success_msg)

                # Record this action in world state
                if context.world_state_manager:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"room_id": room_id, "event_id": event_id, "emoji": emoji},
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
                        parameters={"room_id": room_id, "event_id": event_id, "emoji": emoji},
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
                    parameters={"room_id": room_id, "event_id": event_id, "emoji": emoji},
                    result=f"failure: {str(e)}",
                )
                
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
