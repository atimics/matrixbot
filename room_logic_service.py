import asyncio
import time
import os
import uuid
import json  # Added for logging AI payload
import logging
import datetime  # Add this import

# Set up logger for this module
logger = logging.getLogger(__name__)

# import aiohttp # No longer needed here for typing indicator

from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# Tools that simply output text or reactions without affecting state.
SIMPLE_OUTPUT_TOOLS = {"send_reply", "send_message", "react_to_message", "do_not_respond"}

from message_bus import MessageBus
from event_definitions import (
    MatrixMessageReceivedEvent, AIInferenceRequestEvent, AIInferenceResponseEvent,
    OpenRouterInferenceRequestEvent, OllamaInferenceRequestEvent, # Added specific request events
    OpenRouterInferenceResponseEvent, OllamaInferenceResponseEvent, # ADDED specific response events
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
        # Use response_topic for filtering instead of original_request_payload
        if response_event.response_topic != "ai_chat_response_received": # MODIFIED
            return
        room_id = response_event.original_request_payload.get("room_id")
        if not room_id:
            logger.error("RLS: Error - AIResponse missing room_id in original_request_payload")
            return

        config = self.room_activity_config.get(room_id)
        if not config:
            logger.error(f"RLS: [{room_id}] Error - No config found for room after AIResponse")
            return

        logger.info(f"RLS: [{room_id}] Received AI chat response. Request ID: {response_event.request_id}, Success: {response_event.success}")

        current_bot_name = self.bot_display_name if isinstance(self.bot_display_name, str) else "ChatBot"
        last_user_event_id_in_batch = response_event.original_request_payload.get("last_user_event_id_in_batch")
        # Ensure bot typing indicator is turned off
        await self.bus.publish(SetTypingIndicatorCommand(room_id=room_id, typing=False))

        short_term_memory = config.get('memory', [])
        pending_batch_for_memory = response_event.original_request_payload.get("pending_batch_for_memory", [])
        
        # --- Logging for debugging user message addition to memory ---
        is_follow_up = response_event.original_request_payload.get("is_follow_up_after_tool_execution")
        is_delegated_follow_up = response_event.original_request_payload.get("is_follow_up_after_delegated_tool_call")
        turn_req_id_for_debug = response_event.original_request_payload.get("turn_request_id", "N/A")
        logger.debug(f"RLS: [{room_id}] In _handle_ai_chat_response for turn_request_id: {turn_req_id_for_debug}.")
        logger.debug(f"RLS: [{room_id}]   is_follow_up_after_tool_execution: {is_follow_up}")
        logger.debug(f"RLS: [{room_id}]   is_follow_up_after_delegated_tool_call: {is_delegated_follow_up}")
        logger.debug(f"RLS: [{room_id}]   pending_batch_for_memory is present: {bool(pending_batch_for_memory)}")
        if pending_batch_for_memory:
            logger.debug(f"RLS: [{room_id}]   First item in pending_batch_for_memory: {pending_batch_for_memory[0] if pending_batch_for_memory else 'Empty'}")
        # --- End logging for debugging ---

        if not is_follow_up and \
           not is_delegated_follow_up and \
           pending_batch_for_memory:
            logger.info(f"RLS: [{room_id}] Adding user messages from pending_batch_for_memory to short_term_memory for turn_request_id: {turn_req_id_for_debug}.") # MODIFIED to INFO for visibility
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
        # Define llm_provider_details here
        llm_provider_details = {
            "provider_name": llm_provider_for_this_turn,
            "model_name": response_event.original_request_payload.get("requested_model_name")
        }
        assistant_message_for_memory: Dict[str, Any] = {"role": "assistant", "name": current_bot_name}
        assistant_acted_this_turn = False

        if response_event.success:
            text_response_content = response_event.text_response
            tool_calls_from_llm = response_event.tool_calls
            logger.info(f"RLS: [{room_id}] AI Response Details - Text: '{text_response_content}', Tool Calls: {tool_calls_from_llm}")

            # I. Prioritize Tool Calls
            if tool_calls_from_llm: # Check if tool_calls is present and not empty
                logger.info(f"RLS: [{room_id}] Processing tool calls: {tool_calls_from_llm}")
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

                # Determine if all tool calls are simple output tools and no additional text was provided.
                tool_names_called = [tc.function.name for tc in tool_calls_from_llm if tc.function]
                is_simple_output_only = all(name in SIMPLE_OUTPUT_TOOLS for name in tool_names_called)
                ai_only_simple_output = (not text_response_content) or is_text_in_send_reply or text_response_content.strip() == ""


                ai_turn_key = response_event.original_request_payload.get("turn_request_id")
                if not ai_turn_key:
                    logger.error(f"RLS: [{room_id}] AIInferenceResponseEvent missing 'turn_request_id'. Cannot process tool calls reliably.")
                else:
                    # Snapshot history *before* this assistant's tool-calling message is added.
                    history_snapshot_for_tools = list(short_term_memory)
                    
                    # Store information needed for follow-up after ALL tools complete
                    self.pending_tool_calls_for_ai_turn[ai_turn_key] = {
                        "room_id": room_id,
                        "conversation_history_at_tool_call_time": history_snapshot_for_tools,
                        "assistant_message_with_tool_calls": dict(assistant_message_for_memory), # Store the full assistant message
                        "expected_tool_call_ids": [tc.id for tc in tool_calls_from_llm],
                        "received_tool_responses": [], # To store ToolExecutionResponse objects
                        "original_ai_response_payload": response_event.original_request_payload, # For model, provider, etc.
                        "skip_follow_up_if_simple_output": is_simple_output_only and ai_only_simple_output
                    }
                    logger.info(f"RLS: [{room_id}] Stored pending tool call info for turn_request_id: {ai_turn_key} with {len(tool_calls_from_llm)} expected tools.")

                    # Publish tool calls
                    for tool_call in tool_calls_from_llm:
                        execute_request = ExecuteToolRequest(
                            room_id=room_id,
                            tool_call=tool_call,
                            original_request_payload=response_event.original_request_payload,
                            llm_provider_info=llm_provider_details,
                            conversation_history_snapshot=history_snapshot_for_tools,
                            last_user_event_id=last_user_event_id_in_batch
                        )
                        logger.info(f"RLS: [{room_id}] Publishing ExecuteToolRequest for tool {tool_call.function.name} (Call ID: {tool_call.id}), Request ID: {execute_request.event_id}") # ADDED
                        await self.bus.publish(execute_request)

            # II. If no tool calls, handle text response
            elif text_response_content:
                logger.info(f"RLS: [{room_id}] Processing text response: '{text_response_content}'")
                assistant_acted_this_turn = True
                assistant_message_for_memory["content"] = text_response_content
                if last_user_event_id_in_batch: # Check if there is an event to reply to
                    await self.bus.publish(SendReplyCommand(
                        room_id=room_id,
                        text=text_response_content,
                        reply_to_event_id=last_user_event_id_in_batch
                    ))
                else: # Otherwise, send a regular message
                    await self.bus.publish(SendMatrixMessageCommand(
                        room_id=room_id,
                        text=text_response_content
                    ))
            else:
                logger.warning(f"RLS: [{room_id}] AI response was successful but had no text content and no tool calls.")
        else:
            logger.error(f"RLS: [{room_id}] AI response was not successful. Error: {response_event.error_message}")

        # If assistant acted, add to memory
        if assistant_acted_this_turn:
            short_term_memory.append(assistant_message_for_memory)
            if len(short_term_memory) > self.short_term_memory_items:
                short_term_memory.pop(0)  # Maintain memory size limit

        # Update the room's memory in the config
        config['memory'] = short_term_memory

        # Check if a summary is needed
        if config.get('new_turns_since_last_summary', 0) >= self.short_term_memory_items:
            await self._generate_and_store_summary(room_id)

    async def _generate_and_store_summary(self, room_id: str):
        config = self.room_activity_config.get(room_id)
        if not config:
            logger.error(f"RLS: [{room_id}] Error - No config found for room in _generate_and_store_summary")
            return

        short_term_memory = config.get('memory', [])
        if not short_term_memory:
            logger.info(f"RLS: [{room_id}] No short term memory to summarize.")
            return

        summary_payload = prompt_constructor.build_summary_payload(short_term_memory)
        turn_request_id = str(uuid.uuid4())

        model_to_use: str
        EventClass: type[AIInferenceRequestEvent] # Base type for annotation
        current_provider_name = self.primary_llm_provider

        if current_provider_name == "ollama":
            model_to_use = self.ollama_summary_model
            EventClass = OllamaInferenceRequestEvent # type: ignore
        else: # Default to openrouter
            model_to_use = self.openrouter_summary_model
            EventClass = OpenRouterInferenceRequestEvent # type: ignore

        summary_request = EventClass(
            request_id=turn_request_id,
            reply_to_service_event="ai_summary_response_received",
            original_request_payload={"room_id": room_id},
            model_name=model_to_use,
            messages_payload=summary_payload,
            tools=[],  # No tools needed for summary
            tool_choice="none"
        )
        await self.bus.publish(summary_request)

    async def _handle_ai_summary_response(self, response_event: AIInferenceResponseEvent):
        # Use response_topic for filtering instead of original_request_payload
        if response_event.response_topic != "ai_summary_response_received": # MODIFIED
            return
        room_id = response_event.original_request_payload.get("room_id")
        if not room_id:
            logger.error("RLS: Error - AIResponse missing room_id in original_request_payload")
            return

        config = self.room_activity_config.get(room_id)
        if not config:
            logger.error(f"RLS: [{room_id}] Error - No config found for room after AIResponse")
            return

        if response_event.success:
            summary_text = response_event.text_response
            if summary_text:
                last_event_id_in_summary = config['memory'][-1]["event_id"] if config['memory'] else None
                database.store_summary(self.db_path, room_id, summary_text, last_event_id_in_summary)
                config['new_turns_since_last_summary'] = 0
                logger.info(f"RLS: [{room_id}] Summary stored successfully.")
            else:
                logger.warning(f"RLS: [{room_id}] AIResponse for summary was successful but no text was returned.")
        else:
            logger.error(f"RLS: [{room_id}] AIResponse for summary failed. Error: {response_event.error_message}")

    async def _manage_room_decay(self, room_id: str):
        config = self.room_activity_config.get(room_id)
        if not config:
            logger.error(f"RLS: [{room_id}] Error - No config found for room in _manage_room_decay")
            return

        while config.get('is_active_listening'):
            await asyncio.sleep(config['current_interval'])
            if not config.get('is_active_listening'):
                break

            time_since_last_message = time.time() - config['last_message_timestamp']
            if time_since_last_message >= config['current_interval']:
                config['max_interval_no_activity_cycles'] += 1
                if config['max_interval_no_activity_cycles'] >= self.inactivity_cycles:
                    config['is_active_listening'] = False
                    await self._update_global_presence()
                    logger.info(f"RLS: [{room_id}] Listening deactivated due to inactivity.")
                    break

            config['current_interval'] = min(config['current_interval'] * 2, self.max_interval)

    async def _handle_tool_execution_response(self, response: ToolExecutionResponse):
        # Determine if the original AI response was *only* tool calls and had no direct text for the user.
        # ai_response_had_only_tool_calls_and_no_text_for_user = (
        #     original_ai_response_event.text_content is None or original_ai_response_event.text_content.strip() == ""
        # ) and bool(original_ai_response_event.tool_calls)

        # # Check if the only tool call was a "simple output tool" (e.g., send_reply, react_to_message)
        # is_simple_output_tool_only = False
        # if original_ai_response_event.tool_calls and len(original_ai_response_event.tool_calls) == 1:
        #     tool_name = original_ai_response_event.tool_calls[0].function.name
        #     if tool_name in [\"send_reply\", \"react_to_message\", \"do_not_respond\"]:\n        #         is_simple_output_tool_only = True

        # # If the AI only called a simple output tool (like send_reply) and it succeeded,
        # # and there was no other text from the AI, we might not need a follow-up AI call.
        # # The conversation can naturally proceed to the next user message.
        # if ai_response_had_only_tool_calls_and_no_text_for_user and is_simple_output_tool_only and tool_response_event.status == "success":
        #     logger.info(f"RLS: [{room_id}] Original AI response was effectively just a {tool_response_event.tool_name} tool call. Skipping follow-up AI call for turn {turn_request_id}.")
        #     self._clear_pending_tool_info(room_id, turn_request_id, "Follow-up skipped for simple output tool.")
        #     return # No further AI call needed for this turn.

        # If we are here, it means a follow-up AI call is needed.

        # Access room_id and turn_request_id from the original_request_payload of the ToolExecutionResponse
        # This original_request_payload was set by RoomLogicService when creating the ExecuteToolRequest,
        # and it originated from the AIInferenceResponseEvent.
        turn_request_id = response.original_request_payload.get("turn_request_id")
        room_id = response.original_request_payload.get("room_id")

        if not turn_request_id: # room_id might be absent if turn_request_id is, so check turn_request_id first
            logger.error(f"RLS: Error - ToolExecutionResponse missing 'turn_request_id' in original_request_payload. Payload: {response.original_request_payload}")
            return
        if not room_id: # Check room_id separately
             logger.error(f"RLS: Error - ToolExecutionResponse missing 'room_id' in original_request_payload (turn_request_id: {turn_request_id}). Payload: {response.original_request_payload}")
             return

        logger.info(f"RLS: [{room_id}] Proceeding to make a follow-up AI call for turn {turn_request_id} after tool execution.") # MOVED HERE

        config = self.room_activity_config.get(room_id)
        if not config:
            logger.error(f"RLS: [{room_id}] Error - No config found for room after ToolExecutionResponse")
            return

        pending_turn_info = self.pending_tool_calls_for_ai_turn.get(turn_request_id)
        if not pending_turn_info:
            logger.error(f"RLS: [{room_id}] Error - No pending tool call info found for turn_request_id: {turn_request_id}. This might happen if a tool responds very late or if there's a state mismatch.")
            return

        # Store this tool's response
        pending_turn_info["received_tool_responses"].append(response)
        logger.info(f"RLS: [{room_id}] Received tool response for {response.tool_name} (ID: {response.original_tool_call_id}) for turn {turn_request_id}. ({len(pending_turn_info['received_tool_responses'])}/{len(pending_turn_info['expected_tool_call_ids'])})")

        # Update tool states in the room's config (can be done for each tool as it completes)
        tool_states = config.get('tool_states', {})
        tool_states[response.tool_name] = response.result_for_llm_history 
        config['tool_states'] = tool_states

        # Check if all expected tool calls for this turn have responded
        if len(pending_turn_info["received_tool_responses"]) < len(pending_turn_info["expected_tool_call_ids"]):
            logger.info(f"RLS: [{room_id}] Still waiting for more tool responses for turn {turn_request_id}. Not making follow-up AI call yet.")
            return # Not all tools have responded yet

        # All tools for this turn have responded. Proceed with follow-up and memory update.
        logger.info(f"RLS: [{room_id}] All expected tools for turn {turn_request_id} have responded. Preparing follow-up AI call and updating memory.")

        history_at_tool_call_time = pending_turn_info['conversation_history_at_tool_call_time']
        assistant_message_with_tool_calls = pending_turn_info['assistant_message_with_tool_calls']

        # Prepare history for the follow-up AI call
        augmented_history_for_follow_up = list(history_at_tool_call_time) 
        augmented_history_for_follow_up.append(dict(assistant_message_with_tool_calls)) # Use a copy
        
        original_tool_call_pydantic_objects = assistant_message_with_tool_calls.get("tool_calls", [])
        responses_dict = {resp.original_tool_call_id: resp for resp in pending_turn_info["received_tool_responses"]}

        # Defensive logging for this specific turn completion
        assistant_tool_call_ids = [tc.id for tc in original_tool_call_pydantic_objects]
        received_tool_call_ids = list(responses_dict.keys())
        logger.debug(f"RLS: [{room_id}] Finalizing turn {turn_request_id}. Tool call IDs in assistant message: {assistant_tool_call_ids}")
        logger.debug(f"RLS: [{room_id}] Finalizing turn {turn_request_id}. Tool call IDs with responses: {received_tool_call_ids}")

        # Get a direct reference to the short-term memory list for modification
        short_term_memory_list = config.get('memory', [])

        for original_tc_obj in original_tool_call_pydantic_objects:
            tool_id = original_tc_obj.id 
            tool_exec_response = responses_dict.get(tool_id)
            
            tool_message_content_for_llm: str
            if tool_exec_response:
                tool_message_content_for_llm = tool_exec_response.result_for_llm_history
            else:
                logger.error(f"RLS: [{room_id}] Critical: Missing tool response for expected tool_call_id: {tool_id} when building follow-up history for turn {turn_request_id}. Adding placeholder.")
                tool_message_content_for_llm = f"[Error: Tool response for tool_call_id '{tool_id}' was not found or not recorded before follow-up. The tool may have failed silently, been skipped, or an internal error occurred.]"
            
            tool_message_for_history_and_memory = {
                "role": "tool",
                "tool_call_id": tool_id, 
                "content": tool_message_content_for_llm
            }
            augmented_history_for_follow_up.append(tool_message_for_history_and_memory)

            # Add to actual short-term memory.
            # The assistant's message (that called the tools) is already in memory from _handle_ai_chat_response.
            # We only need to add these tool responses here.
            short_term_memory_list.append(tool_message_for_history_and_memory)
        
        # After appending all tool messages, apply memory size limit to short_term_memory_list
        while len(short_term_memory_list) > self.short_term_memory_items:
            short_term_memory_list.pop(0)  # Maintain memory size limit
        config['memory'] = short_term_memory_list  # Ensure the config reflects the (potentially) trimmed list

        # Determine if a follow-up AI call is necessary. Recompute a safeguard
        # here in case the flag was not stored correctly when the AI response
        # was first handled.
        skip_follow_up = pending_turn_info.get("skip_follow_up_if_simple_output", False)
        assistant_content = assistant_message_with_tool_calls.get("content")
        tool_names = [tc.function.name for tc in original_tool_call_pydantic_objects if tc.function]
        dynamic_simple_output = (
            all(name in SIMPLE_OUTPUT_TOOLS for name in tool_names)
            and (not assistant_content or str(assistant_content).strip() == "")
        )

        if (skip_follow_up or dynamic_simple_output) and all(
            r.status == "success" for r in pending_turn_info["received_tool_responses"]
        ):
            if turn_request_id in self.pending_tool_calls_for_ai_turn:
                del self.pending_tool_calls_for_ai_turn[turn_request_id]
            logger.info(
                f"RLS: [{room_id}] Original AI response used only simple output tools with no extra text. "
                f"Skipping follow-up AI call for turn {turn_request_id}."
            )
            return

        # Now, prepare and publish the follow-up AI request using augmented_history_for_follow_up
        original_ai_payload_from_first_call = pending_turn_info["original_ai_response_payload"]
        current_user_ids_in_context = original_ai_payload_from_first_call.get("current_user_ids_in_context", [])
        current_channel_summary, _ = database.get_summary(self.db_path, room_id) or (None, None)

        follow_up_payload = prompt_constructor.build_messages_for_ai(
            historical_messages=augmented_history_for_follow_up,  # Use the history built in this block
            current_batched_user_inputs=[],
            bot_display_name=self.bot_display_name,
            db_path=self.db_path,
            channel_summary=current_channel_summary,
            tool_states=config.get('tool_states'),
            current_user_ids_in_context=current_user_ids_in_context,
            last_user_event_id_in_batch=None
        )

        # Clean up the pending tool call info for this turn_request_id
        if turn_request_id in self.pending_tool_calls_for_ai_turn:
            del self.pending_tool_calls_for_ai_turn[turn_request_id]
            logger.info(f"RLS: [{room_id}] Cleared pending tool call info for turn_request_id: {turn_request_id} after all tools processed.")

        follow_up_model_name = original_ai_payload_from_first_call.get("requested_model_name", self.openrouter_chat_model)
        follow_up_provider = original_ai_payload_from_first_call.get("current_llm_provider", self.primary_llm_provider)

        FollowUpEventClass: type[AIInferenceRequestEvent]
        if follow_up_provider == "ollama":
            FollowUpEventClass = OllamaInferenceRequestEvent  # type: ignore
        else:
            FollowUpEventClass = OpenRouterInferenceRequestEvent  # type: ignore

        new_original_payload_for_follow_up = {
            "room_id": room_id,
            "is_follow_up_after_tool_execution": True,
            "turn_request_id": turn_request_id,
            "requested_model_name": follow_up_model_name,
            "current_llm_provider": follow_up_provider,
            "current_user_ids_in_context": current_user_ids_in_context
        }

        follow_up_request = FollowUpEventClass(
            request_id=str(uuid.uuid4()),
            reply_to_service_event="ai_chat_response_received",
            original_request_payload=new_original_payload_for_follow_up,
            model_name=follow_up_model_name,
            messages_payload=follow_up_payload,
            tools=self.tool_registry.get_all_tool_definitions(),
            tool_choice="auto"
        )
        await self.bus.publish(follow_up_request)
        logger.info(f"RLS: [{room_id}] Published follow-up AI request for turn {turn_request_id} after processing all tool responses.")

    async def run(self):
        """Main run loop for the service, subscribing to events."""
        self.bus.subscribe(MatrixMessageReceivedEvent.model_fields['event_type'].default, self._handle_matrix_message)
        self.bus.subscribe(ActivateListeningEvent.model_fields['event_type'].default, self._handle_activate_listening)
        self.bus.subscribe(ProcessMessageBatchCommand.model_fields['event_type'].default, self._handle_process_message_batch)
        
        # Subscribe to specific AI response events for chat.
        # The _handle_ai_chat_response method itself checks response_event.response_topic.
        # By subscribing to specific event types, we ensure the handler gets the correctly typed event.
        # We remove the subscription to the generic AIInferenceResponseEvent for this handler
        # to prevent double calls if the message bus delivers an event to handlers for both
        # its specific type and its base type.
        self.bus.subscribe(OpenRouterInferenceResponseEvent.model_fields['event_type'].default, self._handle_ai_chat_response)
        self.bus.subscribe(OllamaInferenceResponseEvent.model_fields['event_type'].default, self._handle_ai_chat_response)
        # If other specific chat response events exist, they should be subscribed here.
        # A generic AIInferenceResponseEvent for chat, if not covered by specific types, would need careful handling
        # or a separate handler if it implies different processing. For now, assuming specific types cover chat.

        # Subscribe to specific AI response events for summary.
        # Similar to chat responses, removed generic subscription to avoid double calls.
        self.bus.subscribe(OpenRouterInferenceResponseEvent.model_fields['event_type'].default, self._handle_ai_summary_response)
        self.bus.subscribe(OllamaInferenceResponseEvent.model_fields['event_type'].default, self._handle_ai_summary_response)
    
        # Fallback subscriptions for truly generic AIInferenceResponseEvents,
        # only if they are not instances of the more specific types handled above
        # and require these handlers. The internal topic check in the handlers is crucial.
        # However, to definitively prevent double calls from the bus, it's better to ensure
        # that an event type isn't matched by multiple subscriptions leading to the same handler.
        # For now, we rely on the specific subscriptions and the internal topic checks.
        # The original generic subscriptions are removed to prevent the bus from causing double calls.
        # If a truly generic AIInferenceResponseEvent (that is not OpenRouter or Ollama) needs to be handled
        # for chat or summary, separate logic or a more sophisticated subscription mechanism might be needed.
        # Based on current usage, specific events are published by AIInferenceService.
        
        self.bus.subscribe(BotDisplayNameReadyEvent.model_fields['event_type'].default, self._handle_bot_display_name_ready)
        self.bus.subscribe(ToolExecutionResponse.model_fields['event_type'].default, self._handle_tool_execution_response)
        
        await self._stop_event.wait()

    async def stop(self):
        """Stops the service."""
        logger.info("RoomLogicService: Stop requested.")
        self._stop_event.set()
        
        # Unsubscribe from all events
        await self.bus.shutdown() # Replaced unsubscribe_all with shutdown
        logger.info("RoomLogicService: Unsubscribed from all events.")