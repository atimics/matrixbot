import asyncio
import os
import uuid
import logging
import httpx
from typing import List, Dict, Any

from message_bus import MessageBus
from event_definitions import (
    MatrixImageReceivedEvent,
    OpenRouterInferenceRequestEvent,
    AIInferenceResponseEvent,
    SendReplyCommand,
    ImageCaptionGeneratedEvent,
)

logger = logging.getLogger(__name__)

class ImageCaptionService:
    """Service that automatically generates captions for received images."""

    def __init__(self, message_bus: MessageBus, matrix_gateway=None):
        self.bus = message_bus
        self.matrix_gateway = matrix_gateway  # Reference to MatrixGatewayService for centralized media conversion
        self.openrouter_vision_model = os.getenv("OPENROUTER_VISION_MODEL", "openai/gpt-4o")
        self.matrix_homeserver = os.getenv("MATRIX_HOMESERVER")
        self._stop_event = asyncio.Event()

    async def _handle_image_message(self, event: MatrixImageReceivedEvent) -> None:
        # Use centralized Matrix Gateway service for media conversion if available
        if self.matrix_gateway:
            converted_url = await self.matrix_gateway.convert_mxc_to_http_with_fallback(event.image_url)
        else:
            # Fallback to local method if Matrix Gateway is not available
            logger.warning("ImageCaptionService: Matrix Gateway not available, using local fallback conversion")
            converted_url = await self._convert_mxc_to_http_with_fallback(event.image_url)
        
        messages_payload: List[Dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image."},
                    {"type": "image_url", "image_url": {"url": converted_url}},
                ],
            }
        ]
        if event.body:
            messages_payload[0]["content"].insert(0, {"type": "text", "text": event.body})

        request_id = str(uuid.uuid4())
        original_payload = {
            "room_id": event.room_id,
            "reply_to_event_id": event.event_id_matrix,
        }
        ai_request = OpenRouterInferenceRequestEvent(
            request_id=request_id,
            reply_to_service_event="image_caption_response",
            original_request_payload=original_payload,
            model_name=self.openrouter_vision_model,
            messages_payload=messages_payload,
            tools=None,
            tool_choice=None,
        )
        await self.bus.publish(ai_request)

    # Keep the fallback methods for backward compatibility in case Matrix Gateway is not available
    async def _convert_mxc_to_http_with_fallback(self, mxc_url: str) -> str:
        """Convert an MXC URI to an HTTP download URL using fallback API versions."""
        if not mxc_url.startswith("mxc://"):
            return mxc_url
        
        try:
            # Extract server and media_id from mxc://server/media_id format
            parts = mxc_url[6:].split("/", 1)  # Remove "mxc://" and split
            if len(parts) != 2:
                logger.error(f"ImageCaptionService: Invalid MXC URL format: {mxc_url}")
                return mxc_url
            
            server, media_id = parts
            
            # Try multiple Matrix media API versions as fallbacks
            api_versions = ["v3", "v1", "r0"]
            
            for version in api_versions:
                matrix_http_url = f"https://{server}/_matrix/media/{version}/download/{server}/{media_id}"
                logger.info(f"ImageCaptionService: Trying Matrix media API {version}: {matrix_http_url}")
                
                # Test if the URL is accessible by making a HEAD request
                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        response = await client.head(matrix_http_url)
                        if response.status_code == 200:
                            logger.info(f"ImageCaptionService: Successfully validated Matrix media API {version}")
                            return matrix_http_url
                        else:
                            logger.warning(f"ImageCaptionService: Matrix media API {version} returned status {response.status_code}")
                except Exception as e:
                    logger.warning(f"ImageCaptionService: Failed to validate Matrix media API {version}: {e}")
                    continue
            
            # If all versions fail, return the v3 URL as fallback (original behavior)
            fallback_url = f"https://{server}/_matrix/media/v3/download/{server}/{media_id}"
            logger.error(f"ImageCaptionService: All Matrix media API versions failed, using v3 fallback: {fallback_url}")
            return fallback_url
            
        except Exception as e:
            logger.error(f"ImageCaptionService: Failed to convert MXC URL '{mxc_url}': {e}")
            return mxc_url

    def _convert_mxc_to_http(self, mxc_url: str) -> str:
        """Convert an MXC URI to an HTTP download URL using fallback API versions."""
        if not mxc_url.startswith("mxc://"):
            return mxc_url
        
        try:
            # Extract server and media_id from mxc://server/media_id format
            parts = mxc_url[6:].split("/", 1)  # Remove "mxc://" and split
            if len(parts) != 2:
                logger.error(f"ImageCaptionService: Invalid MXC URL format: {mxc_url}")
                return mxc_url
            
            server, media_id = parts
            
            # Use server from MXC URL instead of MATRIX_HOMESERVER for direct conversion
            # Try v3 first (most current), but could be extended to use fallbacks like the main system
            return f"https://{server}/_matrix/media/v3/download/{server}/{media_id}"
        except Exception as e:
            logger.error(f"ImageCaptionService: Failed to convert MXC URL '{mxc_url}': {e}")
            return mxc_url

    async def _handle_caption_response(self, response: AIInferenceResponseEvent) -> None:
        if response.response_topic != "image_caption_response":
            return
        room_id = response.original_request_payload.get("room_id")
        reply_to_event_id = response.original_request_payload.get("reply_to_event_id")
        if not room_id or not reply_to_event_id:
            logger.error("ImageCaptionService: Missing room_id or reply_to_event_id in response payload")
            return
        caption_text = response.text_response if response.success and response.text_response else "[Image could not be interpreted]"
        await self.bus.publish(SendReplyCommand(room_id=room_id, text=caption_text, reply_to_event_id=reply_to_event_id))
        await self.bus.publish(ImageCaptionGeneratedEvent(room_id=room_id, caption_text=caption_text, original_event_id=reply_to_event_id))

    async def run(self) -> None:
        logger.info("ImageCaptionService: Starting...")
        self.bus.subscribe(MatrixImageReceivedEvent.get_event_type(), self._handle_image_message)
        # Subscribe to the proper OpenRouter response event type instead of the custom string
        from event_definitions import OpenRouterInferenceResponseEvent
        self.bus.subscribe(OpenRouterInferenceResponseEvent.get_event_type(), self._handle_caption_response)
        await self._stop_event.wait()
        logger.info("ImageCaptionService: Stopped.")

    async def stop(self) -> None:
        logger.info("ImageCaptionService: Stop requested.")
        self._stop_event.set()
