"""
Matrix messaging tools - Send messages and replies using the observer directly.
"""
import logging
import time
from typing import Any, Dict

from ...config import settings
from ..base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class SendMatrixReplyTool(ToolInterface):
    """
    Tool for sending replies to specific messages in Matrix channels using the observer directly.
    """

    @property
    def name(self) -> str:
        return "send_matrix_reply"

    @property
    def description(self) -> str:
        return ("Reply to a specific message in a Matrix channel. Use \'channel_id\' for the channel and \'message\' for the content. If reply_to_id is not provided, will send as a regular message to the channel. "
                "Recently generated media (within 5 minutes) will be automatically attached as a separate image message if no explicit image_url is provided.")

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "channel_id": "string (Matrix room ID) - The room where the reply should be sent",
            "message": "string - The message content to send as a reply (supports markdown formatting)",
            "reply_to_id": "string (optional) - The event ID of the message to reply to. If not provided, sends as regular message",
            "format_as_markdown": "boolean (optional, default: true) - Whether to format the content as markdown",
            "image_url": "string (optional) - URL of an image to attach. If not provided, recently generated media will be auto-attached",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Matrix reply action using the observer directly.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Get Matrix messaging service from service registry
        matrix_service = context.get_messaging_service("matrix")
        if not matrix_service or not await matrix_service.is_available():
            error_msg = "Matrix messaging service is not available."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        channel_id = params.get("channel_id")
        content = params.get("message")
        reply_to_event_id = params.get("reply_to_id")
        format_as_markdown = params.get("format_as_markdown", True)
        image_url = params.get("image_url")

        missing_params = []
        if not channel_id:
            missing_params.append("channel_id")
        if not content:
            missing_params.append("message")

        if missing_params:
            error_msg = f"Missing required parameters for Matrix reply: {', '.join(missing_params)}"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Deduplication check: prevent replying to events we've already replied to
        if reply_to_event_id and context.world_state_manager:
            if context.world_state_manager.has_bot_replied_to_matrix_event(reply_to_event_id):
                warning_msg = f"Bot has already replied to Matrix event {reply_to_event_id}, skipping to prevent feedback loop"
                logger.warning(warning_msg)
                return {
                    "status": "skipped",
                    "message": warning_msg,
                    "event_id": reply_to_event_id,
                    "channel_id": channel_id,
                    "reason": "already_replied",
                    "timestamp": time.time(),
                }

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

        try:
            # If reply_to_id is missing but we have channel_id and content, fall back to regular message
            if not reply_to_event_id:
                logger.info(f"reply_to_id missing, falling back to regular message in {channel_id}")
                result = await matrix_service.send_message(
                    channel_id=channel_id,
                    content=content
                )
                
                if result.get("status") == "success":
                    # Handle auto-attached image for fallback message
                    image_event_id = None
                    if image_url:
                        media_service = context.get_media_service("matrix")
                        if media_service:
                            image_result = await media_service.send_image(
                                channel_id=channel_id,
                                image_url=image_url
                            )
                            if image_result.get("status") == "success":
                                image_event_id = image_result.get("event_id")
                                logger.info(f"Auto-attached image to Matrix fallback message: {image_event_id}")
                    
                    result.update({
                        "fallback_to_message": True,
                        "auto_attached_image": image_url if image_url else None,
                        "image_event_id": image_event_id,
                    })
                
                return result
            
            # Send reply using the service layer
            result = await matrix_service.send_reply(
                channel_id=channel_id,
                content=content,
                reply_to_id=reply_to_event_id
            )
            
            if result.get("status") == "success":
                # Handle auto-attached image for reply
                image_event_id = None
                if image_url:
                    media_service = context.get_media_service("matrix")
                    if media_service:
                        image_result = await media_service.send_image(
                            channel_id=channel_id,
                            image_url=image_url
                        )
                        if image_result.get("status") == "success":
                            image_event_id = image_result.get("event_id")
                            logger.info(f"Auto-attached image to Matrix reply: {image_event_id}")
                
                result.update({
                    "auto_attached_image": image_url if image_url else None,
                    "image_event_id": image_event_id,
                    "sent_content": content,  # For AI Blindness Fix
                })
            
            return result

        except Exception as e:
            error_msg = f"Error executing {self.name}: {str(e)}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class SendMatrixMessageTool(ToolInterface):
    """
    Tool for sending new messages to Matrix channels using the service layer.
    """

    @property
    def name(self) -> str:
        return "send_matrix_message"

    @property
    def description(self) -> str:
        return ("Send a new message to a Matrix channel. Use 'channel_id' for the channel and 'message' for the content. Use this when you want to start a new conversation or make an announcement. "
                "Use the 'attach_image' parameter to include an image - either provide a description to generate a new image, or reference an existing media_id from your library. "
                "Recently generated media (within 5 minutes) will be automatically attached if no explicit attach_image is provided.")

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "channel_id": "string (Matrix room ID) - The room where the message should be sent",
            "message": "string - The message content to send (supports markdown formatting)",
            "format_as_markdown": "boolean (optional, default: true) - Whether to format the content as markdown",
            "attach_image": "string (optional) - Either a media_id from your library (e.g., 'media_img_1234567890') or a description to generate a new image (e.g., 'sunset over mountains')",
            "image_url": "string (optional) - Direct URL of an image to attach. If not provided, recently generated media will be auto-attached",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Matrix message action using the service layer.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Get Matrix messaging service from service registry
        matrix_service = context.get_messaging_service("matrix")
        if not matrix_service or not await matrix_service.is_available():
            error_msg = "Matrix messaging service is not available."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        room_id = params.get("room_id")
        content = params.get("message")
        format_as_markdown = params.get("format_as_markdown", True)
        attach_image = params.get("attach_image")  # New: either media_id or description
        image_url = params.get("image_url")

        missing_params = []
        if not room_id:
            missing_params.append("room_id")
        if not content:
            missing_params.append("message")

        if missing_params:
            error_msg = f"Missing required parameters for Matrix message: {', '.join(missing_params)}"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Handle attach_image parameter: could be media_id or description
        generated_image_info = None
        if attach_image:
            # Check if it's a media_id (starts with "media_")
            if attach_image.startswith("media_"):
                # It's a media_id, retrieve from library
                if context.world_state_manager:
                    image_url = context.world_state_manager.get_media_url_by_id(attach_image)
                    if image_url:
                        logger.info(f"Using existing image from library: {attach_image} -> {image_url}")
                    else:
                        logger.warning(f"Media ID {attach_image} not found in library")
            else:
                # It's a description, generate new image
                from ..message_enhancement import generate_image_from_description
                generated_image_info = await generate_image_from_description(attach_image, context)
                if generated_image_info:
                    image_url = generated_image_info["image_url"]
                    logger.info(f"Generated new image from description: '{attach_image}' -> {image_url}")
                else:
                    logger.warning(f"Failed to generate image from description: {attach_image}")

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
                            logger.info(f"Auto-attaching recently generated media to Matrix message: {image_url}")

        try:
            # Send message using the service layer
            result = await matrix_service.send_message(
                room_id=room_id,
                content=content
            )

            if result.get("status") == "success":
                # Handle auto-attached image
                image_event_id = None
                if image_url:
                    media_service = context.get_media_service("matrix")
                    if media_service:
                        image_result = await media_service.send_image(
                            channel_id=room_id,
                            image_url=image_url
                        )
                        if image_result.get("status") == "success":
                            image_event_id = image_result.get("event_id")
                            logger.info(f"Auto-attached image to Matrix message: {image_event_id}")
                
                result.update({
                    "auto_attached_image": image_url if image_url else None,
                    "image_event_id": image_event_id,
                    "sent_content": content,  # For AI Blindness Fix
                    "generated_image_info": generated_image_info,  # Include info about generated image
                    "attach_image_used": attach_image,  # Show what attach_image parameter was used
                })
            
            return result

        except Exception as e:
            error_msg = f"Error executing {self.name}: {str(e)}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
