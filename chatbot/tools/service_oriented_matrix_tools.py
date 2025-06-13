"""
Service-Oriented Matrix Tools

Matrix tools that use the service registry instead of direct observer access.
These tools demonstrate the new service-oriented architecture.
"""

import logging
import time
from typing import Any, Dict

from ..config import settings
from .base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class ServiceOrientedSendMatrixReplyTool(ToolInterface):
    """
    Service-oriented tool for sending replies to specific messages in Matrix channels.
    Uses the service registry instead of direct observer access.
    """

    @property
    def name(self) -> str:
        return "send_matrix_reply_v2"

    @property
    def description(self) -> str:
        return ("Service-oriented reply tool for Matrix channels. Uses clean service interfaces. "
                "Reply to a specific message in a Matrix channel. If reply_to_id is not provided, will send as a regular message to the channel. "
                "Recently generated media (within 5 minutes) will be automatically attached as a separate image message if no explicit image_url is provided.")

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "channel_id": "string (Matrix room ID) - The room where the reply should be sent",
            "content": "string - The message content to send as a reply (supports markdown formatting)",
            "reply_to_id": "string (optional) - The event ID of the message to reply to. If not provided, sends as regular message",
            "format_as_markdown": "boolean (optional, default: true) - Whether to format the content as markdown",
            "image_url": "string (optional) - URL of an image to attach. If not provided, recently generated media will be auto-attached",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Matrix reply action using service-oriented approach.
        """
        logger.info(f"Executing service-oriented tool '{self.name}' with params: {params}")

        # Get Matrix service from service registry
        matrix_service = context.get_messaging_service("matrix")
        if not matrix_service:
            error_msg = "Matrix messaging service not available"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Check if service is available
        if not await matrix_service.is_available():
            error_msg = "Matrix service is not currently available"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        room_id = params.get("channel_id")
        content = params.get("content")
        reply_to_event_id = params.get("reply_to_id")
        format_as_markdown = params.get("format_as_markdown", True)
        image_url = params.get("image_url")

        missing_params = []
        if not room_id:
            missing_params.append("channel_id")
        if not content:
            missing_params.append("content")

        if missing_params:
            error_msg = f"Missing required parameters for Matrix reply: {', '.join(missing_params)}"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Auto-attachment: Check for recently generated media if no image_url provided
        if not image_url and context.world_state_manager:
            recent_media_url = context.world_state_manager.get_last_generated_media_url()
            if recent_media_url:
                # Check if the media was generated recently (within last 5 minutes)
                if hasattr(context.world_state_manager.state, 'generated_media_library'):
                    media_library = context.world_state_manager.state.generated_media_library
                    if media_library:
                        last_media = media_library[-1]
                        media_age = time.time() - last_media.get('timestamp', 0)
                        if media_age <= 300:  # 5 minutes
                            image_url = recent_media_url
                            logger.info(f"Auto-attaching recently generated media to Matrix reply: {image_url}")

        # Send reply or regular message using service
        if reply_to_event_id:
            result = await matrix_service.send_reply(
                channel_id=room_id,
                content=content,
                reply_to_id=reply_to_event_id,
                format_as_markdown=format_as_markdown
            )
        else:
            logger.info(f"reply_to_id missing, falling back to regular message in {room_id}")
            result = await matrix_service.send_message(
                channel_id=room_id,
                content=content,
                format_as_markdown=format_as_markdown
            )

        # Send auto-attached image if available
        image_event_id = None
        if image_url and result.get("status") == "success":
            media_service = context.get_media_service("matrix")
            if media_service:
                image_result = await media_service.send_image(
                    channel_id=room_id,
                    image_url=image_url,
                    caption="Auto-attached recently generated media"
                )
                if image_result.get("status") == "success":
                    image_event_id = image_result.get("event_id")
                    logger.info(f"Auto-attached image sent with event ID: {image_event_id}")

        # Add image information to result if attached
        if image_event_id:
            result["auto_attached_image"] = {
                "event_id": image_event_id,
                "image_url": image_url
            }

        return result


class ServiceOrientedReactToMatrixMessageTool(ToolInterface):
    """
    Service-oriented tool for reacting to Matrix messages.
    Uses the service registry instead of direct observer access.
    """

    @property
    def name(self) -> str:
        return "react_to_matrix_message_v2"

    @property
    def description(self) -> str:
        return ("Service-oriented reaction tool for Matrix messages. Uses clean service interfaces. "
                "React to a specific message in a Matrix channel with an emoji. "
                "Use this to acknowledge messages, show agreement, or express emotions without sending a full reply.")

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "channel_id": "string (Matrix room ID) - The room containing the message to react to",
            "event_id": "string - The event ID of the message to react to",
            "reaction": "string - The emoji or reaction to add (e.g. '👍', '❤️', '😄')",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Matrix reaction action using service-oriented approach.
        """
        logger.info(f"Executing service-oriented tool '{self.name}' with params: {params}")

        # Get Matrix service from service registry
        matrix_service = context.get_messaging_service("matrix")
        if not matrix_service:
            error_msg = "Matrix messaging service not available"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Check if service is available
        if not await matrix_service.is_available():
            error_msg = "Matrix service is not currently available"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        room_id = params.get("channel_id")
        event_id = params.get("event_id")
        reaction = params.get("reaction")

        missing_params = []
        if not room_id:
            missing_params.append("channel_id")
        if not event_id:
            missing_params.append("event_id")
        if not reaction:
            missing_params.append("reaction")

        if missing_params:
            error_msg = f"Missing required parameters for Matrix reaction: {', '.join(missing_params)}"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Send reaction using service
        result = await matrix_service.react_to_message(
            channel_id=room_id,
            event_id=event_id,
            reaction=reaction
        )

        return result
