import asyncio
import logging
from typing import Dict, Any

from message_bus import MessageBus
from event_definitions import AIInferenceResponseEvent, ToolExecutionResponse

logger = logging.getLogger(__name__)


class ImageAnalysisService:
    """Service to handle image analysis responses and convert them to tool results."""

    def __init__(self, message_bus: MessageBus):
        self.bus = message_bus
        self._stop_event = asyncio.Event()

    async def _handle_image_analysis_response(self, response: AIInferenceResponseEvent) -> None:
        if response.response_topic != "image_analysis_response":
            return

        original_payload = response.original_request_payload
        room_id = original_payload.get("room_id")
        tool_call_id = original_payload.get("tool_call_id")
        analysis_type = original_payload.get("analysis_type")

        if not room_id or not tool_call_id:
            logger.error("ImageAnalysisService: Missing room_id or tool_call_id in response")
            return

        if response.success and response.text_response:
            result_text = f"Image Analysis ({analysis_type}):\n{response.text_response}"
            status = "success"
            error_message = None
        else:
            result_text = f"[Image analysis failed: {response.error_message or 'Unknown error'}]"
            status = "failure"
            error_message = response.error_message

        tool_response = ToolExecutionResponse(
            original_tool_call_id=tool_call_id,
            tool_name="describe_image",
            status=status,
            result_for_llm_history=result_text,
            error_message=error_message,
            original_request_payload={"room_id": room_id},
            commands_to_publish=None,
        )

        await self.bus.publish(tool_response)
        logger.info(f"ImageAnalysisService: Published analysis result for room {room_id}")

    async def run(self) -> None:
        logger.info("ImageAnalysisService: Starting...")
        self.bus.subscribe("image_analysis_response", self._handle_image_analysis_response)
        await self._stop_event.wait()
        logger.info("ImageAnalysisService: Stopped.")

    async def stop(self) -> None:
        logger.info("ImageAnalysisService: Stop requested.")
        self._stop_event.set()
