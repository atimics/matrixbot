import asyncio
import os
import uuid
import logging
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

from message_bus import MessageBus
from event_definitions import (
    AIInferenceRequestEvent, AIInferenceResponseEvent, 
    SummaryGeneratedEvent, BotDisplayNameReadyEvent,
    RequestAISummaryCommand, # Added
    OllamaInferenceRequestEvent, OpenRouterInferenceRequestEvent # Added
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
        
        # Initialize database path (same as orchestrator)
        self.db_path = os.getenv("DATABASE_PATH", "matrix_bot_soa.db")
        # Ensure database is initialized if not already (idempotent)
        database.initialize_database(self.db_path)

        # LLM Configuration for summaries
        self.primary_llm_provider = os.getenv("PRIMARY_LLM_PROVIDER", "openrouter").lower()
        self.openrouter_summary_model = os.getenv("OPENROUTER_SUMMARY_MODEL", os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"))
        self.ollama_summary_model = os.getenv("OLLAMA_DEFAULT_SUMMARY_MODEL", os.getenv("OLLAMA_DEFAULT_CHAT_MODEL", "qwen2"))

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
            await asyncio.to_thread(database.update_summary, self.db_path, room_id, summary_text, event_id_last_msg)
            logger.info(f"SummarizationSvc: [{room_id}] DB summary updated. Last event: {event_id_last_msg}. Len: {len(summary_text)}")
            await self.bus.publish(SummaryGeneratedEvent(
                room_id=room_id, 
                summary_text=summary_text,
                last_event_id_summarized=event_id_last_msg
            ))
        elif not response_event.success:
            logger.error(f"SummarizationSvc: [{room_id}] Failed to generate summary. Error: {response_event.error_message}")
        else:
            logger.warning(f"SummarizationSvc: [{room_id}] AI returned empty summary text.")

    async def _handle_request_ai_summary_command(self, command: RequestAISummaryCommand) -> None:
        room_id = command.room_id
        messages_to_summarize = command.messages_to_summarize
        force_update = command.force_update # Though ManageChannelSummaryTool might not use this directly

        logger.info(f"SummarizationSvc: [{room_id}] Received RequestAISummaryCommand. Messages count: {len(messages_to_summarize)}. Force: {force_update}")

        if not messages_to_summarize and not force_update:
            logger.info(f"SummarizationSvc: [{room_id}] No messages to summarize and not a forced update. Skipping.")
            return

        previous_summary_text, _ = await asyncio.to_thread(database.get_summary, self.db_path, room_id) or (None, None)
        
        # Determine the event_id of the last message in the batch to be summarized
        event_id_of_last_message_in_summary_batch: Optional[str] = None
        if messages_to_summarize:
            for msg in reversed(messages_to_summarize):
                # messages_to_summarize contains HistoricalMessage objects
                if msg.event_id: # Direct attribute access
                    event_id_of_last_message_in_summary_batch = msg.event_id
                    break
        
        if not event_id_of_last_message_in_summary_batch and command.last_event_id_in_messages:
            # Fallback to the event_id provided in the command itself if not found in messages
            event_id_of_last_message_in_summary_batch = command.last_event_id_in_messages
            logger.info(f"SummarizationSvc: [{room_id}] Using last_event_id_in_messages from command as fallback: {event_id_of_last_message_in_summary_batch}")


        if not event_id_of_last_message_in_summary_batch:
            # This case should ideally be handled by the tool sending the command,
            # ensuring messages_to_summarize is not empty or providing a fallback.
            # If ManageChannelSummaryTool sends a snapshot, it should have event_ids.
            logger.warning(f"SummarizationSvc: [{room_id}] No event_id found in messages_to_summarize for summary request. Cannot anchor summary.")
            # Potentially, we could try to get the latest from DB if forced, but command should provide context.
            # For now, if no messages, and no event_id, we can't proceed reliably.
            if not force_update: # If forced, we might allow proceeding without new messages if a previous summary exists.
                 return

        # Convert messages to transcript string
        transcript_parts = []
        for msg in messages_to_summarize:
            sender_name = getattr(msg, "name", None) or "Unknown User"
            content = msg.content if msg.content else ""
            transcript_parts.append(f"{sender_name}: {content}")
        transcript_for_summarization = "\n".join(transcript_parts)

        ai_payload = prompt_constructor.build_summary_generation_payload(
            transcript_for_summarization=transcript_for_summarization, # MODIFIED
            db_path=self.db_path, # ADDED for prompt_constructor
            bot_display_name=self.bot_display_name,
            previous_summary=previous_summary_text
        )

        request_id = str(uuid.uuid4())
        
        # Determine which provider and model to use for summarization
        summary_model_to_use: str
        summary_request_event_class: type[AIInferenceRequestEvent]

        if self.primary_llm_provider == "ollama":
            summary_model_to_use = self.ollama_summary_model
            summary_request_event_class = OllamaInferenceRequestEvent
        else: # Default to openrouter
            summary_model_to_use = self.openrouter_summary_model
            summary_request_event_class = OpenRouterInferenceRequestEvent

        original_payload_for_ai_response = {
            "room_id": room_id,
            "event_id_of_last_message_in_summary_batch": event_id_of_last_message_in_summary_batch,
            "is_summary_request": True # For AIInferenceService logging/metrics if needed
        }

        ai_request = summary_request_event_class(
            request_id=request_id,
            reply_to_service_event="ai_summary_response_received", # Existing handler
            original_request_payload=original_payload_for_ai_response,
            model_name=summary_model_to_use,
            messages_payload=ai_payload,
            tools=None, 
            tool_choice=None 
        )
        await self.bus.publish(ai_request)
        logger.info(f"SummarizationSvc: [{room_id}] AI summary request published to {self.primary_llm_provider} ({summary_model_to_use}). Event anchor: {event_id_of_last_message_in_summary_batch}. Msgs: {len(messages_to_summarize)}")

    async def run(self) -> None:
        logger.info("SummarizationService: Starting...")
        self.bus.subscribe(
            BotDisplayNameReadyEvent.model_fields["event_type"].default,
            self._handle_bot_display_name_ready,
        )
        # Listen for inference responses from both providers
        self.bus.subscribe(
            OpenRouterInferenceResponseEvent.model_fields["event_type"].default,
            self._handle_ai_summary_response,
        )
        self.bus.subscribe(
            OllamaInferenceResponseEvent.model_fields["event_type"].default,
            self._handle_ai_summary_response,
        )
        self.bus.subscribe(
            RequestAISummaryCommand.model_fields["event_type"].default,
            self._handle_request_ai_summary_command,
        )
        await self._stop_event.wait()
        logger.info("SummarizationService: Stopped.")

    async def stop(self) -> None:
        logger.info("SummarizationService: Stop requested.")
        self._stop_event.set()