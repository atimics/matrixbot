"""
Send Matrix Video Tool - Send Videos to Matrix Channels

Tool for sending video files to Matrix channels.
Uses ServiceRegistry abstraction for clean platform integration.
"""

import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class SendMatrixVideoTool(ToolInterface):
    """
    Tool for sending video files to Matrix channels.
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
            "channel_id": "string - The unique identifier of the Matrix room where the video should be sent",
            "video_url": "string - The public URL of the video to send",
            "caption": "string (optional) - Optional text caption for the video",
            "filename": "string (optional) - Optional filename for the video",
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """
        Execute the Matrix video sending action using ServiceRegistry.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")
        
        # Get Matrix observer from service registry (for now, until we have a video service)
        matrix_observer = context.service_registry.get_service("matrix_observer")
        if not matrix_observer:
            error_msg = "Matrix observer not available in ServiceRegistry."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        # Accept both 'channel_id' and 'room_id' for better LLM tolerance
        # This prevents errors when LLMs use 'room_id' based on the Matrix context
        room_id = params.get("channel_id") or params.get("room_id")
        video_url = params.get("video_url")
        caption = params.get("caption")
        filename = params.get("filename", "video.mp4")

        if not room_id or not video_url:
            return {"status": "failure", "error": "Missing required parameters: channel_id and video_url"}

        try:
            # Download the video data from the URL
            import httpx
            
            # Define browser-like headers to bypass WAF rules
            browser_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
            }
            
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                response = await client.get(video_url, headers=browser_headers)
                response.raise_for_status()
                video_data = response.content
                
                # Get content type from HTTP response headers
                response_content_type = response.headers.get('content-type', '').split(';')[0].strip()

            # Determine MIME type for the video file
            import mimetypes
            mime_type, _ = mimetypes.guess_type(filename)
            
            # Prefer HTTP response content type if it's a video type
            if response_content_type and response_content_type.startswith('video/'):
                mime_type = response_content_type
                logger.info(f"Using content-type from HTTP response: {mime_type}")
            elif not mime_type or not mime_type.startswith('video/'):
                # Fallback to file extension detection
                lower_filename = filename.lower()
                if lower_filename.endswith('.webm'):
                    mime_type = "video/webm"
                elif lower_filename.endswith('.mov'):
                    mime_type = "video/quicktime"
                elif lower_filename.endswith('.avi'):
                    mime_type = "video/avi"
                elif lower_filename.endswith('.mkv'):
                    mime_type = "video/x-matroska"
                else:
                    mime_type = "video/mp4"  # Default fallback
            
            logger.info(f"Final detected video MIME type: {mime_type} for file: {filename}")

            # Upload the video to Matrix media repository
            from nio import UploadResponse, UploadError
            upload_response = await matrix_observer.client.upload(
                data_provider=lambda _, __: video_data,
                content_type=mime_type,
                filename=filename,
                filesize=len(video_data)
            )

            if isinstance(upload_response, UploadError):
                raise Exception(f"Failed to upload video to Matrix: {upload_response.message}")
            if not isinstance(upload_response, UploadResponse):
                raise Exception(f"Unexpected upload response type: {type(upload_response)}")

            # Send the video message
            content = {
                "body": caption or filename,
                "msgtype": "m.video",
                "url": upload_response.content_uri,
                "info": {
                    "mimetype": mime_type,
                    "size": len(video_data),
                    # Future enhancement: Add duration, thumbnail_url, w, h
                }
            }
            send_response = await matrix_observer.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content=content
            )
            
            from nio import RoomSendResponse
            if isinstance(send_response, RoomSendResponse):
                # Record this action success in world state
                if context.world_state_manager:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={
                            "room_id": room_id,
                            "video_url": video_url,
                            "caption": caption,
                        },
                        result="success",
                    )

                return {
                    "status": "success", 
                    "event_id": send_response.event_id,
                    "message": f"Successfully sent video to Matrix room {room_id}",
                    "timestamp": time.time()
                }
            else:
                raise Exception(f"Failed to send video message: {send_response}")

        except Exception as e:
            logger.error(f"Error sending Matrix video: {e}", exc_info=True)
            
            # Record this action failure in world state
            if context.world_state_manager:
                context.world_state_manager.add_action_result(
                    action_type=self.name,
                    parameters={
                        "room_id": room_id,
                        "video_url": video_url,
                    },
                    result=f"failure: {str(e)}",
                )
            
            return {"status": "failure", "error": str(e), "timestamp": time.time()}
