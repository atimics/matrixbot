"""
Matrix media tools - Send images and videos using the service layer.
"""
import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class SendMatrixImageTool(ToolInterface):
    """
    Tool for sending images to Matrix channels using the service layer.
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
            "channel_id": "string (Matrix room ID) - The room where the image should be sent",
            "image_url": "string - The URL of the image to send (must be publicly accessible, such as Arweave URLs from image generation)",
            "caption": "string (optional) - Optional text caption or description for the image",
            "filename": "string (optional) - Optional filename for the image (will be auto-detected if not provided)",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Matrix image sending action using the service layer.
        """
        logger.debug(f"Executing tool '{self.name}' with params: {params}")

        # Get Matrix media service from service registry
        media_service = context.get_media_service("matrix")
        if not media_service or not await media_service.is_available():
            error_msg = "Matrix media service is not available."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        room_id = params.get("channel_id")
        image_url = params.get("image_url")
        caption = params.get("caption")
        filename = params.get("filename")

        missing_params = []
        if not room_id:
            missing_params.append("channel_id")
        if not image_url:
            missing_params.append("image_url")

        if missing_params:
            error_msg = f"Missing required parameters for Matrix image: {', '.join(missing_params)}"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Use the service layer
            result = await media_service.send_image(
                channel_id=room_id, 
                image_url=image_url, 
                caption=caption
            )
            
            # Log action in world state regardless of success/failure
            if context.world_state_manager:
                if result.get("status") == "success":
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"room_id": room_id, "image_url": image_url, "caption": caption},
                        result="success",
                    )
                else:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"room_id": room_id, "image_url": image_url},
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
                    parameters={"room_id": room_id, "image_url": image_url},
                    result=f"failure: {str(e)}",
                )

            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class SendMatrixVideoTool(ToolInterface):
    """
    Tool for sending video files to Matrix channels using the service layer.
    """

    @property
    def name(self) -> str:
        return "send_matrix_video"

    @property
    def description(self) -> str:
        return "Uploads a video from a URL and sends it to a Matrix room. Use this for sharing generated videos."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "channel_id": "string (Matrix room ID) - The room where the video should be sent",
            "video_url": "string - The public URL of the video to send",
            "caption": "string (optional) - Optional text caption for the video",
            "filename": "string (optional) - Optional filename for the video",
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """
        Execute the Matrix video sending action using the service layer.
        """
        logger.debug(f"Executing tool '{self.name}' with params: {params}")

        # Get Matrix media service from service registry
        media_service = context.get_media_service("matrix")
        if not media_service or not await media_service.is_available():
            error_msg = "Matrix media service is not available."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        room_id = params.get("channel_id")
        video_url = params.get("video_url")
        caption = params.get("caption")
        filename = params.get("filename", "video.mp4")

        if not room_id or not video_url:
            error_msg = "Missing required parameters: channel_id and video_url"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Use the service layer
            result = await media_service.send_video(
                channel_id=room_id, 
                video_url=video_url, 
                caption=caption
            )
            
            # Log action in world state regardless of success/failure
            if context.world_state_manager:
                if result.get("status") == "success":
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"room_id": room_id, "video_url": video_url, "caption": caption},
                        result="success",
                    )
                else:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"room_id": room_id, "video_url": video_url},
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
                    parameters={"room_id": room_id, "video_url": video_url},
                    result=f"failure: {str(e)}",
                )
            
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class SendMatrixVideoLinkTool(ToolInterface):
    """
    Tool for sharing video links in Matrix channels using the service layer.
    This avoids Matrix upload issues by sending the video as a rich text message with embedded link.
    """

    @property
    def name(self) -> str:
        return "send_matrix_video_link"

    @property
    def description(self) -> str:
        return "Share a video link in a Matrix room using Arweave URL. Avoids Matrix video upload issues."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "channel_id": "string (Matrix room ID) - The room where the video link should be sent",
            "video_url": "string - The Arweave URL of the video to share",
            "caption": "string (optional) - Optional text caption for the video",
            "title": "string (optional) - Optional title for the video link",
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """
        Execute the Matrix video link sharing action using the service layer.
        """
        logger.debug(f"Executing tool '{self.name}' with params: {params}")
        
        # Get Matrix messaging service from service registry
        messaging_service = context.get_messaging_service("matrix")
        if not messaging_service or not await messaging_service.is_available():
            error_msg = "Matrix messaging service is not available."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        room_id = params.get("channel_id")
        video_url = params.get("video_url")
        caption = params.get("caption", "")
        title = params.get("title", "Video")

        if not room_id or not video_url:
            error_msg = "Missing required parameters: channel_id and video_url"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Create rich text message with embedded video link
            if caption:
                message_text = f"🎥 **{title}**\n\n{caption}\n\n[📺 Watch Video]({video_url})"
            else:
                message_text = f"🎥 **{title}**\n\n[📺 Watch Video]({video_url})"
            
            # Use the service layer to send the message
            result = await messaging_service.send_message(
                channel_id=room_id,
                content=message_text,
                format_as_markdown=True
            )
            
            # Log action in world state regardless of success/failure
            if context.world_state_manager:
                if result.get("status") == "success":
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"room_id": room_id, "video_url": video_url, "caption": caption},
                        result="success",
                    )
                else:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"room_id": room_id, "video_url": video_url},
                        result=f"failure: {result.get('error', 'unknown error')}",
                    )
            
            return result

        except Exception as e:
            error_msg = f"Error sending Matrix video link: {str(e)}"
            logger.exception(error_msg)
            
            # Record this action failure in world state
            if context.world_state_manager:
                context.world_state_manager.add_action_result(
                    action_type=self.name,
                    parameters={"room_id": room_id, "video_url": video_url},
                    result=f"failure: {str(e)}",
                )
            
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
