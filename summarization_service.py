import asyncio
import os
import uuid
import logging
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

from message_bus import MessageBus
from event_definitions import (
    AIInferenceRequestEvent, AIInferenceResponseEvent, 
    SummaryGeneratedEvent, BotDisplayNameReadyEvent
)
import database 
import prompt_constructor

logger = logging.getLogger(__name__)

load_dotenv()

class SummarizationService:
    def __init__(self, message_bus: MessageBus, bot_display_name: str = "ChatBot"):
        """Service for handling AI-generated conversation summaries."""
        self.bus = message_bus
        self.bot_display_name = bot_display_name
        self._stop_event = asyncio.Event()
        self.openrouter_summary_model = os.getenv("OPENROUTER_MODEL", "openai/gpt-3.5-turbo")

    async def _handle_bot_display_name_ready(self, event: BotDisplayNameReadyEvent) -> None:
        self.bot_display_name = event.display_name
        logger.info(f"SummarizationSvc: Bot display name updated to '{self.bot_display_name}'")

    async def _handle_ai_summary_response(self, response_event: AIInferenceResponseEvent) -> None:
        room_id = response_event.original_request_payload.get("room_id")
        event_id_last_msg = response_event.original_request_payload.get("event_id_of_last_message_in_summary_batch")
        if not room_id or not event_id_last_msg:
            logger.error(f"SummarizationSvc: Missing room_id or event_id_last_msg in AI summary response. Req ID: {response_event.request_id}")
            return
        if response_event.success and response_event.text_response and response_event.text_response.strip():
            summary_text = response_event.text_response
            database.update_summary(room_id, summary_text, event_id_last_msg)
            logger.info(f"SummarizationSvc: [{room_id}] DB summary updated. Last event: {event_id_last_msg}. Len: {len(summary_text)}")
            await self.bus.publish(SummaryGeneratedEvent(
                room_id=room_id, 
                summary_text=summary_text,
                last_event_id_in_summary=event_id_last_msg
            ))
        elif not response_event.success:
            logger.error(f"SummarizationSvc: [{room_id}] Failed to generate summary. Error: {response_event.error_message}")
        else:
            logger.warning(f"SummarizationSvc: [{room_id}] AI returned empty summary text.")

    async def run(self) -> None:
        logger.info("SummarizationService: Starting...")
        self.bus.subscribe(BotDisplayNameReadyEvent.model_fields['event_type'].default, self._handle_bot_display_name_ready)
        self.bus.subscribe("ai_summary_response_received", self._handle_ai_summary_response)
        await self._stop_event.wait()
        logger.info("SummarizationService: Stopped.")

    async def stop(self) -> None:
        logger.info("SummarizationService: Stop requested.")
        self._stop_event.set()