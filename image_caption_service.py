import asyncio
import os
import uuid
import logging
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

    def __init__(self, message_bus: MessageBus):
        self.bus = message_bus
        self.openrouter_vision_model = os.getenv("OPENROUTER_VISION_MODEL", "openai/gpt-4o")
        self._stop_event = asyncio.Event()

    async def _handle_image_message(self, event: MatrixImageReceivedEvent) -> None:
        messages_payload: List[Dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image."},
                    {"type": "image_url", "image_url": {"url": event.image_url}},
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
        self.bus.subscribe("image_caption_response", self._handle_caption_response)
        await self._stop_event.wait()
        logger.info("ImageCaptionService: Stopped.")

    async def stop(self) -> None:
        logger.info("ImageCaptionService: Stop requested.")
        self._stop_event.set()
