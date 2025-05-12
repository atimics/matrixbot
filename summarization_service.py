import asyncio
import os
import uuid
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

from message_bus import MessageBus
from event_definitions import (
    GenerateSummaryRequestEvent, AIInferenceRequestEvent, AIInferenceResponseEvent,
    SummaryGeneratedEvent, BotDisplayNameReadyEvent
)
import database 
import prompt_constructor

load_dotenv()

class SummarizationService:
    def __init__(self, message_bus: MessageBus, bot_display_name: str = "ChatBot"):
        self.bus = message_bus
        self.bot_display_name = bot_display_name # Set by BotDisplayNameReadyEvent
        self._stop_event = asyncio.Event()
        self.openrouter_summary_model = os.getenv("OPENROUTER_MODEL", "openai/gpt-3.5-turbo")
        # This service needs access to the same room_activity_config or a way to get messages.
        # For this version, we'll assume it needs access to the RoomLogicService's memory.
        # This is a simplification; ideally, messages for summary would be passed in the event
        # or fetched from a persistent message store if one existed.
        # For now, this service will *not* directly access RoomLogicService's memory.
        # The GenerateSummaryRequestEvent should ideally carry the messages if they aren't in DB.
        # The current design: update_channel_summary_if_needed is in RoomLogic and *calls* AI
        # via an event. This service just handles the AI response part for summaries.
        # Let's adjust: This service *requests* the summary from AI and updates DB.
        # RoomLogicService will provide the necessary context (new messages, prev summary event_id)
        # via the GenerateSummaryRequestEvent.

    async def _handle_bot_display_name_ready(self, event: BotDisplayNameReadyEvent):
        self.bot_display_name = event.display_name
        print(f"SummarizationSvc: Bot display name updated to '{self.bot_display_name}'")

    async def _handle_generate_summary_request(self, request_event: GenerateSummaryRequestEvent):
        room_id = request_event.room_id
        # print(f"SummarizationSvc: [{room_id}] Received GenerateSummaryRequestEvent. Force: {request_event.force_update}")

        # This service needs the actual messages to summarize.
        # The GenerateSummaryRequestEvent should be enhanced, or this service needs
        # to coordinate with RoomLogicService to get the relevant short-term memory segment.
        # For this example, let's assume GenerateSummaryRequestEvent is a trigger,
        # and this service fetches what it needs from the database and potentially
        # short-term memory (though that breaks strict service separation unless memory is also event-sourced).

        # Let's stick to the plan: RoomLogicService determines new messages and sends them for summary.
        # This means GenerateSummaryRequestEvent needs to contain `new_messages_for_summary_prompt_data`
        # and `previous_summary_text`.
        
        # Re-thinking: The `update_channel_summary_if_needed` logic is complex and stateful (needs short-term memory).
        # It's better suited to live in `RoomLogicService`.
        # `RoomLogicService` will:
        # 1. Decide a summary is needed.
        # 2. Collect new messages from its short-term memory.
        # 3. Get previous summary text from DB (or this service can provide it via an event).
        # 4. Construct payload using prompt_constructor.
        # 5. Publish AIInferenceRequestEvent (for summary model).
        # This `SummarizationService` then primarily handles the *response* from the summary AI
        # and updates the database.

        # For this implementation, let RoomLogicService continue to determine what to summarize.
        # This service will subscribe to AIInferenceResponseEvents that are replies to summary requests.
        # The `reply_to_service_event` in AIInferenceRequestEvent will be key.
        pass # This handler will be removed if RoomLogic directly requests summary AI.

    async def _handle_ai_summary_response(self, response_event: AIInferenceResponseEvent):
        # This handler is specifically for SUMMARY responses.
        # original_request_payload should contain { room_id, event_id_of_last_message_in_summary_batch }
        room_id = response_event.original_request_payload.get("room_id")
        event_id_last_msg = response_event.original_request_payload.get("event_id_of_last_message_in_summary_batch")

        if not room_id or not event_id_last_msg:
            print(f"SummarizationSvc: Missing room_id or event_id_last_msg in AI summary response. Req ID: {response_event.request_id}")
            return
        
        # print(f"SummarizationSvc: [{room_id}] Received AI summary response for request {response_event.request_id}. Success: {response_event.success}")

        if response_event.success and response_event.text_response and response_event.text_response.strip():
            summary_text = response_event.text_response
            database.update_summary(room_id, summary_text, event_id_last_msg)
            print(f"SummarizationSvc: [{room_id}] DB summary updated. Last event: {event_id_last_msg}. Len: {len(summary_text)}")
            
            # Optionally publish SummaryGeneratedEvent
            await self.bus.publish(SummaryGeneratedEvent(
                room_id=room_id, 
                summary_text=summary_text,
                last_event_id_in_summary=event_id_last_msg
            ))
        elif not response_event.success:
            print(f"SummarizationSvc: [{room_id}] Failed to generate summary. Error: {response_event.error_message}")
        else:
            print(f"SummarizationSvc: [{room_id}] AI returned empty summary text.")


    async def run(self):
        print("SummarizationService: Starting...")
        self.bus.subscribe(BotDisplayNameReadyEvent.model_fields['event_type'].default, self._handle_bot_display_name_ready)
        # This service listens for AIInferenceResponseEvents that were intended for it (summary results)
        self.bus.subscribe("ai_summary_response_received", self._handle_ai_summary_response)
        # GenerateSummaryRequestEvent is now handled by RoomLogicService, which then makes an AIInferenceRequest.
        
        await self._stop_event.wait()
        print("SummarizationService: Stopped.")

    async def stop(self):
        print("SummarizationService: Stop requested.")
        self._stop_event.set()