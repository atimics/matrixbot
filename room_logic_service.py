import asyncio
import time
import os
import uuid
import json # Added for logging AI payload
import logging
import datetime # Add this import

# Set up logger for this module
logger = logging.getLogger(__name__)

# import aiohttp # No longer needed here for typing indicator

from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

from message_bus import MessageBus
from event_definitions import (
    MatrixMessageReceivedEvent, AIInferenceRequestEvent, AIInferenceResponseEvent,
    OpenRouterInferenceRequestEvent, OllamaInferenceRequestEvent, # Added specific request events
    SendMatrixMessageCommand, ProcessMessageBatchCommand, ActivateListeningEvent,
    BotDisplayNameReadyEvent,
    SetTypingIndicatorCommand, SetPresenceCommand,
    ReactToMessageCommand, SendReplyCommand, # Added tool commands
    ExecuteToolRequest, # Added ExecuteToolRequest
    ToolExecutionResponse, # Added ToolExecutionResponse
    BatchedUserMessage # Add this import
)
import prompt_constructor # For building AI payload
import database # For database operations
from tool_manager import ToolRegistry # Added

load_dotenv()

class RoomLogicService:
    def __init__(self, message_bus: MessageBus, tool_registry: ToolRegistry, db_path: str, bot_display_name: str = "ChatBot"): # Added db_path
        """Service for managing room logic, batching, and AI interaction."""
        self.bus = message_bus
        self.tool_registry = tool_registry # Store it
        self.db_path = db_path # Store db_path
        self.bot_display_name = bot_display_name # Set by BotDisplayNameReadyEvent
        self.room_activity_config: Dict[str, Dict[str, Any]] = {}
        self._stop_event = asyncio.Event()
        self._service_start_time = datetime.datetime.now(datetime.timezone.utc) # Changed to datetime object
        self.pending_tool_calls_for_ai_turn: Dict[str, Dict[str, Any]] = {} # Added for tool call state

        # Configurable values
        self.initial_interval = int(os.getenv("POLLING_INITIAL_INTERVAL", "10"))
        self.max_interval = int(os.getenv("POLLING_MAX_INTERVAL", "120"))
        self.inactivity_cycles = int(os.getenv("POLLING_INACTIVITY_DECAY_CYCLES", "3"))
        self.batch_delay = float(os.getenv("MESSAGE_BATCH_DELAY", "3.0"))
        self.short_term_memory_items = int(os.getenv("MAX_MESSAGES_PER_ROOM_MEMORY_ITEMS", "20"))
        self.openrouter_chat_model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4.1-mini")
        self.openrouter_summary_model = os.getenv("OPENROUTER_SUMMARY_MODEL", os.getenv("OPENROUTER_MODEL", "openai/gpt-4.1-mini")) # Added for summaries

        # Ollama Configuration
        self.primary_llm_provider = os.getenv("PRIMARY_LLM_PROVIDER", "openrouter").lower()
        self.ollama_chat_model = os.getenv("OLLAMA_DEFAULT_CHAT_MODEL", "qwen3")
        self.ollama_summary_model = os.getenv("OLLAMA_DEFAULT_SUMMARY_MODEL", self.ollama_chat_model)

        self._status_cache: Dict[str, Any] = {"value": None, "expires_at": 0.0}
        self.status_cache_ttl = int(os.getenv("AI_STATUS_TEXT_CACHE_TTL", "3600"))  # 1 hour default
        self._last_global_presence = None  # Track last global presence state


    async def _update_global_presence(self):
        """
        Sets presence: 'unavailable' on startup. 'online' if any room is active. 'unavailable' if no rooms are active (after startup).
        Only publishes SetPresenceCommand if the state changes.
        """
        desired_presence: str

        if self._last_global_presence is None:  # Initial startup
            desired_presence = "unavailable"
        else:
            any_active = any(cfg.get('is_active_listening') for cfg in self.room_activity_config.values())
            if any_active:
                desired_presence = "online"
            else:
                desired_presence = "unavailable"  # Change to unavailable if no rooms are active

        if self._last_global_presence != desired_presence:
            self._last_global_presence = desired_presence
            await self.bus.publish(SetPresenceCommand(presence=desired_presence))

    async def _handle_bot_display_name_ready(self, event: BotDisplayNameReadyEvent):
        self.bot_display_name = event.display_name
        logger.info(f"RoomLogic: Bot display name updated to '{self.bot_display_name}'")
        await self._update_global_presence()

    async def _handle_matrix_message(self, event: MatrixMessageReceivedEvent):
        # Ignore events that occurred before the service started (historical events)
        if hasattr(event, 'timestamp') and event.timestamp < self._service_start_time:
            return
        room_id = event.room_id
        # config = self.room_activity_config.get(room_id) # Moved down, not needed before mention check

        bot_name_lower = self.bot_display_name.lower()
        is_mention = bool(bot_name_lower and bot_name_lower in event.body.lower())

        if is_mention:
            logger.info(f"RoomLogic: [{room_id}] Mention detected.")
            activate_event = ActivateListeningEvent(
                room_id=room_id,
                activation_message_event_id=event.event_id_matrix, # Corrected field name and source
                triggering_sender_display_name=event.sender_display_name,
                triggering_message_body=event.body
            )
            await self.bus.publish(activate_event)
            return # The _handle_activate_listening will handle adding this message if needed

        config = self.room_activity_config.get(room_id) # Re-fetch in case it was just created
        if config and config.get('is_active_listening'):
            logger.info(f"RoomLogic: [{room_id}] Actively listening. Adding message to batch.")
            config['pending_messages_for_batch'].append({
                "name": event.sender_display_name,
                "content": event.body,
                "event_id": event.event_id_matrix # Changed from event.event_id
            })
            config['last_message_timestamp'] = time.time()
            config['current_interval'] = self.initial_interval # Reset decay polling
            config['max_interval_no_activity_cycles'] = 0

            # Debounce batch processing
            old_batch_task = config.get('batch_response_task')
            if old_batch_task and not old_batch_task.done():
                old_batch_task.cancel()
                try:
                    await old_batch_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"RoomLogic: [{room_id}] Previous batch task raised {e} while being awaited after cancellation.")
            config['batch_response_task'] = asyncio.create_task(
                self._delayed_batch_processing_publisher(room_id, self.batch_delay)
            )


    async def _handle_activate_listening(self, event: ActivateListeningEvent):
        room_id = event.room_id
        config = self.room_activity_config.get(room_id)

        if config and config.get('decay_task') and not config['decay_task'].done():
            config['decay_task'].cancel()
        if config and config.get('batch_response_task') and not config['batch_response_task'].done():
            config['batch_response_task'].cancel() # Cancel any pending batch from previous active period

        if not config:
            db_summary_info = database.get_summary(self.db_path, room_id) # Added self.db_path
            initial_last_event_id_db = db_summary_info[1] if db_summary_info else None

            config = {
                'memory': [], 'pending_messages_for_batch': [],
                'last_event_id_in_db_summary': initial_last_event_id_db,
                'new_turns_since_last_summary': 0,
                'batch_response_task': None,
                'activation_trigger_event_id': event.activation_message_event_id # Store the triggering event_id
            }
            self.room_activity_config[room_id] = config
        else:
            # If config exists, update the activation_trigger_event_id if this is a re-activation
            config['activation_trigger_event_id'] = event.activation_message_event_id

        config.update({
            'is_active_listening': True,
            'current_interval': self.initial_interval,
            'last_message_timestamp': time.time(),
            'max_interval_no_activity_cycles': 0,
            'decay_task': asyncio.create_task(self._manage_room_decay(room_id))
        })

        # If activation was triggered by a message, add it to the batch and schedule processing
        if event.triggering_message_body and event.triggering_sender_display_name:
            logger.info(f"RoomLogic: [{room_id}] Activation by message. Adding triggering message to batch.")
            config['pending_messages_for_batch'].append({
                "name": event.triggering_sender_display_name,
                "content": event.triggering_message_body,
                "event_id": event.activation_message_event_id
            })
            # Ensure batch processing is scheduled for this message
            old_batch_task = config.get('batch_response_task')
            if old_batch_task and not old_batch_task.done():
                old_batch_task.cancel()
                try: await old_batch_task
                except asyncio.CancelledError: pass
            config['batch_response_task'] = asyncio.create_task(
                self._delayed_batch_processing_publisher(room_id, self.batch_delay)
            )

        await self._update_global_presence()
        logger.info(f"RoomLogic: [{room_id}] Listening activated/reset. Mem size: {len(config['memory'])}. Last DB summary event: {config.get('last_event_id_in_db_summary')}")


    async def _delayed_batch_processing_publisher(self, room_id: str, delay: float):
        try:
            await asyncio.sleep(delay)
            if asyncio.current_task().cancelled(): # type: ignore
                logger.info(f"RoomLogic: [{room_id}] Delayed batch publisher cancelled.")
                return

            config = self.room_activity_config.get(room_id)
            if not config:
                logger.warning(f"RoomLogic: [{room_id}] Config not found in _delayed_batch_processing_publisher. Cannot send batch.")
                return

            pending_messages = config.get('pending_messages_for_batch', [])
            if not pending_messages:
                logger.info(f"RoomLogic: [{room_id}] No pending messages in _delayed_batch_processing_publisher. Nothing to send.")
                return

            # Convert pending_messages to BatchedUserMessage instances
            # Assuming pending_messages are dicts like: {"name": sender_display_name, "content": body, "event_id": event_id}
            # BatchedUserMessage expects: {"user_id": str, "content": str, "event_id": str}
            # We'll use "name" as "user_id" for now, though this might need refinement if a more persistent user_id is available.
            messages_to_batch: List[BatchedUserMessage] = []
            for msg_data in pending_messages:
                try:
                    messages_to_batch.append(BatchedUserMessage(
                        user_id=msg_data.get("name", "Unknown User"), # Using 'name' as 'user_id'
                        content=msg_data.get("content", ""),
                        event_id=msg_data.get("event_id", "")
                    ))
                except Exception as e:
                    logger.error(f"RoomLogic: [{room_id}] Error converting message to BatchedUserMessage: {msg_data}. Error: {e}")
                    continue # Skip malformed messages

            if not messages_to_batch:
                logger.info(f"RoomLogic: [{room_id}] No valid messages to batch after conversion. Nothing to send.")
                return

            await self.bus.publish(ProcessMessageBatchCommand(room_id=room_id, messages_in_batch=messages_to_batch))
            # The handler _handle_process_message_batch is responsible for clearing config['pending_messages_for_batch']
            # This ensures messages are only cleared if the command is successfully published and then processed.

        except asyncio.CancelledError:
            logger.info(f"RoomLogic: [{room_id}] Delayed batch publisher cancelled by exception.")
        except Exception as e:
            logger.error(f"RoomLogic: [{room_id}] Unexpected error in _delayed_batch_processing_publisher: {e}", exc_info=True)


    async def _handle_process_message_batch(self, command: ProcessMessageBatchCommand):
        room_id = command.room_id
        config = self.room_activity_config.get(room_id)
        if not config or not config.get('is_active_listening'): return

        # The command now carries the messages.
        # We should use command.messages_in_batch instead of config['pending_messages_for_batch']
        # And clear the config's pending_messages_for_batch as it's now been "picked up" by this command.

        # It's important to clear the original source of these messages from the config
        # to prevent reprocessing if another trigger occurs before this handler completes fully.
        # However, the messages for AI processing are now directly from the command.
        pending_batch_from_command = command.messages_in_batch
        
        # Clear the config's list as these messages are now being processed.
        config['pending_messages_for_batch'] = []


        if not pending_batch_from_command:
            logger.info(f"RoomLogic: [{room_id}] ProcessMessageBatchCommand received with no messages. Nothing to process.")
            return

        logger.info(f"RoomLogic: [{room_id}] Processing message batch of size {len(pending_batch_from_command)} from command.")

        # --- Tell Gateway to start typing ---
        await self.bus.publish(SetTypingIndicatorCommand(room_id=room_id, typing=True))

        short_term_memory = config.get('memory', [])
        summary_text_for_prompt, _ = database.get_summary(self.db_path, room_id) or (None, None)

        last_user_event_id_in_batch = None
        # Convert BatchedUserMessage back to the dict format expected by build_messages_for_ai
        # and also for adding to memory later.
        # build_messages_for_ai expects: List[Dict[str, str]] where dicts are {"name": ..., "content": ..., "event_id": ...}
        processed_pending_batch_for_ai: List[Dict[str, str]] = []
        current_user_ids: List[str] = [] # ADDED: For collecting user IDs

        for bum in pending_batch_from_command:
            processed_pending_batch_for_ai.append({
                "name": bum.user_id, # Map back from user_id to name
                "content": bum.content,
                "event_id": bum.event_id
            })
            if bum.user_id not in current_user_ids: # ADDED: Collect unique user IDs
                current_user_ids.append(bum.user_id)
        
        if processed_pending_batch_for_ai:
            last_user_event_id_in_batch = processed_pending_batch_for_ai[-1].get("event_id")

        # Fetch tool_states from the room's config.
        # This assumes tool_states are stored/updated in the config dictionary.
        # If tool_states are managed differently (e.g., globally or fetched from DB directly),
        # this logic would need to be adjusted.
        tool_states_for_prompt: Optional[Dict[str, Any]] = config.get('tool_states')


        ai_payload = prompt_constructor.build_messages_for_ai(
            historical_messages=list(short_term_memory),
            current_batched_user_inputs=processed_pending_batch_for_ai, # Use the converted batch
            bot_display_name=self.bot_display_name,
            db_path=self.db_path, # ADDED
            channel_summary=summary_text_for_prompt,
            tool_states=tool_states_for_prompt, # ADDED (Can be None)
            current_user_ids_in_context=current_user_ids, # ADDED
            last_user_event_id_in_batch=last_user_event_id_in_batch
        )

        turn_request_id = str(uuid.uuid4())
        original_payload_for_ai_response = {
            "room_id": room_id,
            "pending_batch_for_memory": processed_pending_batch_for_ai, # Use the converted batch for memory
            "last_user_event_id_in_batch": last_user_event_id_in_batch,
            "turn_request_id": turn_request_id,
        }

        model_to_use: str
        EventClass: type[AIInferenceRequestEvent] # Base type for annotation
        current_provider_name = self.primary_llm_provider

        if current_provider_name == "ollama":
            model_to_use = self.ollama_chat_model
            EventClass = OllamaInferenceRequestEvent # type: ignore
        else: # Default to openrouter
            model_to_use = self.openrouter_chat_model
            EventClass = OpenRouterInferenceRequestEvent # type: ignore

        original_payload_for_ai_response["requested_model_name"] = model_to_use
        original_payload_for_ai_response["current_llm_provider"] = current_provider_name

        ai_request = EventClass(
            request_id=turn_request_id,
            reply_to_service_event="ai_chat_response_received",
            original_request_payload=original_payload_for_ai_response,
            model_name=model_to_use,
            messages_payload=ai_payload,
            tools=self.tool_registry.get_all_tool_definitions(),
            tool_choice="auto" 
        )
        await self.bus.publish(ai_request)


    async def _handle_ai_chat_response(self, response_event: AIInferenceResponseEvent): # Renamed from _handle_ai_inference_response
        room_id = response_event.original_request_payload.get("room_id")
        if not room_id:
            logger.error("RLS: Error - AIResponse missing room_id in original_request_payload")
            return

        config = self.room_activity_config.get(room_id)
        if not config:
            logger.error(f"RLS: [{room_id}] Error - No config found for room after AIResponse")
            return

        current_bot_name = self.bot_display_name if isinstance(self.bot_display_name, str) else "ChatBot"
        last_user_event_id_in_batch = response_event.original_request_payload.get("last_user_event_id_in_batch")

        await self.bus.publish(SetTypingIndicatorCommand(room_id=room_id, typing=False))

        short_term_memory = config.get('memory', [])
        pending_batch_for_memory = response_event.original_request_payload.get("pending_batch_for_memory", [])
        
        if not response_event.original_request_payload.get("is_follow_up_after_tool_execution") and \
           not response_event.original_request_payload.get("is_follow_up_after_delegated_tool_call") and \
           pending_batch_for_memory:
            try:
                combined_user_content = "".join(f"{msg['name']}: {msg['content']}\n" for msg in pending_batch_for_memory)
                representative_event_id_for_user_turn = pending_batch_for_memory[-1]["event_id"]
                user_name_for_memory = pending_batch_for_memory[0]["name"]

                short_term_memory.append({
                    "role": "user",
                    "name": user_name_for_memory,
                    "content": combined_user_content.strip(),
                    "event_id": representative_event_id_for_user_turn
                })
                config['new_turns_since_last_summary'] = config.get('new_turns_since_last_summary', 0) + 1
            except (KeyError, IndexError) as e:
                logger.error(f"RLS: [{room_id}] Error processing pending_batch_for_memory for memory: {e}. Batch: {pending_batch_for_memory}")

        llm_provider_for_this_turn = response_event.original_request_payload.get("current_llm_provider", "openrouter")
        assistant_message_for_memory: Dict[str, Any] = {"role": "assistant", "name": current_bot_name}
        assistant_acted_this_turn = False

        if response_event.success:
            text_response_content = response_event.text_response
            tool_calls_from_llm = response_event.tool_calls

            # I. Prioritize Tool Calls
            if tool_calls_from_llm: # Check if tool_calls is present and not empty
                assistant_acted_this_turn = True
                if text_response_content:
                    logger.warning(f"RLS: [{room_id}] LLM provided both text_response ('{text_response_content}') and tool_calls. Prioritizing tool_calls. Direct text will be ignored.")
                
                assistant_message_for_memory["tool_calls"] = tool_calls_from_llm
                # Content for memory is None if only tool calls, or if text is part of send_reply
                is_text_in_send_reply = False
                if text_response_content:
                    for tc in tool_calls_from_llm:
                        if tc.function and tc.function.name == "send_reply":
                            try:
                                args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
                                if args.get("text") == text_response_content:
                                    is_text_in_send_reply = True
                                    break
                            except Exception: pass
                if text_response_content and not is_text_in_send_reply:
                     assistant_message_for_memory["content"] = text_response_content
                else:
                     assistant_message_for_memory["content"] = None


                ai_turn_key = response_event.original_request_payload.get("turn_request_id")
                if not ai_turn_key:
                    logger.error(f"RLS: [{room_id}] AIInferenceResponseEvent missing 'turn_request_id'. Cannot process tool calls reliably.")
                else:
                    history_snapshot_for_tools = list(short_term_memory)
                    current_assistant_turn_message_dict = dict(assistant_message_for_memory)

                    self.pending_tool_calls_for_ai_turn[ai_turn_key] = {
                        "room_id": room_id,
                        "conversation_history_at_tool_call_time": history_snapshot_for