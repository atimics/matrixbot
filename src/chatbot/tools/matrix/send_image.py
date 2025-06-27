"""
Send Matrix Image Tool - Send Images to Matrix Channels

Tool for sending images to Matrix channels.
Uses ServiceRegistry abstraction for clean platform integration.
"""

import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class SendMatrixImageTool(ToolInterface):
    """
    Tool for sending images to Matrix channels.
    """

    @property
    def name(self) -> str:
        return "send_matrix_image"

    @property
    def description(self) -> str:
        return "Send an image to a Matrix room. Use this to share generated images or other images with Matrix users."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "channel_id": "string - The unique identifier of the Matrix room where the image should be sent",
            "image_url": "string - The URL of the image to send (must be publicly accessible, such as Arweave URLs from image generation)",
            "caption": "string (optional) - Optional text caption or description for the image",
            "filename": "string (optional) - Optional filename for the image (will be auto-detected if not provided)",
            "raw_image_data": "bytes (optional) - Raw image bytes for direct upload (optimization to avoid download)",
            "image_mime_type": "string (optional) - MIME type when raw_image_data is provided",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Matrix image sending action using ServiceRegistry.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Get Matrix messaging service from registry
        matrix_service = context.service_registry.get_messaging_service("matrix")
        if not matrix_service:
            error_msg = "Matrix messaging service not available in ServiceRegistry."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        # Accept both 'channel_id' and 'room_id' for better LLM tolerance
        # This prevents errors when LLMs use 'room_id' based on the Matrix context
        room_id = params.get("channel_id") or params.get("room_id")
        image_url = params.get("image_url")
        caption = params.get("caption")
        filename = params.get("filename")
        raw_image_data = params.get("raw_image_data")  # NEW: Raw image bytes for optimization
        image_mime_type = params.get("image_mime_type")  # NEW: MIME type for raw data

        # Validate required parameters
        missing_params = []
        if not room_id:
            missing_params.append("channel_id")
        if not image_url and not raw_image_data:
            missing_params.append("image_url or raw_image_data")

        if missing_params:
            error_msg = f"Missing required parameters for Matrix image: {', '.join(missing_params)}"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # OPTIMIZATION: Check for recent image generation in world state context
            # If raw image data is available, use it directly to bypass download
            if not raw_image_data and context.world_state_manager:
                # Check if there's recent generated media with raw data
                recent_media = context.world_state_manager.get_last_generated_media_with_raw_data()
                if recent_media and recent_media.get("raw_image_data"):
                    raw_image_data = recent_media["raw_image_data"]
                    image_mime_type = recent_media.get("image_mime_type", "image/png")
                    logger.info("Using raw image data from recent generation for Matrix optimization")

            # Use the messaging service's send_image method with optimization
            if raw_image_data and image_mime_type:
                # Use optimized path with raw data
                result = await matrix_service.send_image(
                    room_id, image_url=image_url, caption=caption, filename=filename,
                    image_data=raw_image_data, mime_type=image_mime_type
                )
                logger.info(f"Matrix messaging service send_image (optimized) returned: {result}")
            else:
                # Fallback to URL-based upload
                result = await matrix_service.send_image(
                    room_id, image_url, caption=caption, filename=filename
                )
                logger.info(f"Matrix messaging service send_image (URL-based) returned: {result}")

            if result.get("success"):
                event_id = result.get("event_id", "unknown")
                success_msg = f"Sent Matrix image to {room_id} (event: {event_id})"
                logger.info(success_msg)

                # Record this action in world state
                if context.world_state_manager:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={
                            "room_id": room_id,
                            "image_url": image_url,
                            "caption": caption,
                        },
                        result="success",
                    )

                return {
                    "status": "success",
                    "message": success_msg,
                    "event_id": event_id,
                    "room_id": room_id,
                    "image_url": image_url,
                    "filename": result.get("filename"),
                    "timestamp": time.time(),
                }
            else:
                error_msg = f"Failed to send Matrix image via service: {result.get('error', 'unknown error')}"
                logger.error(error_msg)

                # Record this action failure in world state
                if context.world_state_manager:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={
                            "room_id": room_id,
                            "image_url": image_url,
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
                        "image_url": image_url,
                    },
                    result=f"failure: {str(e)}",
                )

            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
