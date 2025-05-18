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
        for bum in pending_batch_from_command:
            processed_pending_batch_for_ai.append({
                "name": bum.user_id, # Map back from user_id to name
                "content": bum.content,
                "event_id": bum.event_id
            })
        
        if processed_pending_batch_for_ai:
            last_user_event_id_in_batch = processed_pending_batch_for_ai[-1].get("event_id")


        ai_payload = prompt_constructor.build_messages_for_ai(
            historical_messages=list(short_term_memory),
            current_batched_user_inputs=processed_pending_batch_for_ai, # Use the converted batch
            bot_display_name=self.bot_display_name,
            channel_summary=summary_text_for_prompt,
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


    async def _handle_ai_chat_response(self, response_event: AIInferenceResponseEvent):
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
        representative_event_id_for_user_turn = None 

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

        if response_event.success:
            text_response_content = response_event.text_response 
            should_send_text_response_directly = bool(text_response_content) 

            if text_response_content and response_event.tool_calls:
                # Convert ToolCall objects to JSON-serializable dicts for logging
                tool_calls_for_logging = [tc.model_dump(mode='json') for tc in response_event.tool_calls]
                logger.info(f"RLS: [{room_id}] LLM ({llm_provider_for_this_turn}) requested tool_calls: {json.dumps(tool_calls_for_logging, indent=2)}")

                for tool_call_model in response_event.tool_calls: # tool_call_model is a ToolCall Pydantic object
                    function_data = tool_call_model.function # Access as attribute
                    try:
                        # arguments_str = function_data.get("arguments", "{}") # Original
                        arguments_str = function_data.arguments if function_data else "{}"
                        arguments = json.loads(arguments_str)
                        # if arguments.get("text") == text_response_content: # Original
                        if arguments.get("text") == text_response_content and tool_call_model.function.name == "send_reply":
                            logger.info(f"RLS: [{room_id}] Suppressing direct sending of text_response as it matches send_reply tool's text.")
                            should_send_text_response_directly = False
                            break 
                    except json.JSONDecodeError:
                        logger.warning(f"RLS: [{room_id}] Failed to parse arguments for tool call while checking for duplicates: {arguments_str}")
                    except Exception as e:
                            logger.error(f"RLS: [{room_id}] Error comparing text_response to args: {e}", exc_info=True)

            assistant_message_for_memory: Dict[str, Any] = {"role": "assistant", "name": current_bot_name}
            assistant_acted = False

            if text_response_content: 
                assistant_message_for_memory["content"] = text_response_content

            if should_send_text_response_directly: 
                await self.bus.publish(SendMatrixMessageCommand(room_id=room_id, text=text_response_content))
                assistant_acted = True
            
            if response_event.tool_calls:
                # Correctly serialize for logging
                tool_calls_for_logging = [tc.model_dump(mode='json') for tc in response_event.tool_calls]
                logger.info(f"RLS: [{room_id}] LLM ({llm_provider_for_this_turn}) requested tool_calls: {json.dumps(tool_calls_for_logging, indent=2)}")

                for tool_call_model in response_event.tool_calls: # tool_call_model is a ToolCall Pydantic object
                    # Ensure 'id' is present. ToolCall model requires it, so it should be there.
                    # The original code generated an ID if missing, assuming tool_call was a dict.
                    # If ToolCall objects are guaranteed to have an ID by their creator, this check might be simplified.
                    # For now, log an error if a ToolCall model somehow lacks an ID.
                    if not tool_call_model.id:
                        # This case should ideally not happen if ToolCall models are validated upon creation.
                        # If it can, the ID generation should be here or upstream.
                        # For now, log an error if a ToolCall model somehow lacks an ID.
                        logger.error(f"RLS: [{room_id}] Tool call from LLM is missing 'id'. Skipping. Tool: {tool_call_model.model_dump_json()}")
                        # Potentially decrement expected_count for pending_tool_calls_for_ai_turn
                        if ai_turn_key and ai_turn_key in self.pending_tool_calls_for_ai_turn:
                            self.pending_tool_calls_for_ai_turn[ai_turn_key]["expected_count"] -= 1
                            if self.pending_tool_calls_for_ai_turn[ai_turn_key]["expected_count"] <= 0:
                                del self.pending_tool_calls_for_ai_turn[ai_turn_key]
                        continue
                
                assistant_message_for_memory["tool_calls"] = response_event.tool_calls
                if not assistant_message_for_memory.get("content"): # If no text part (e.g. it was suppressed or never there)
                    assistant_message_for_memory["content"] = None # Ensure content is None if only tool_calls

                assistant_acted = True 

                # Add assistant message with tool_calls to memory BEFORE dispatching tool execution requests.
                # This is done here to ensure the conversation_history_at_tool_call_time is accurate.
                # The 'if assistant_message_for_memory.get("content") or assistant_message_for_memory.get("tool_calls")'
                # check below will handle adding it.

                ai_turn_key = response_event.original_request_payload.get("turn_request_id")
                if not ai_turn_key:
                    logger.error(f"RLS: [{room_id}] AIInferenceResponseEvent missing 'turn_request_id'. Cannot process tool calls reliably.")
                else:
                    # Temporarily remove the assistant message if it was just added, to rebuild history correctly for this specific point.
                    # This is a bit tricky: short_term_memory should reflect history *before* this assistant turn's tool_calls message.
                    # So, we build assistant_message_for_memory, then use a snapshot of short_term_memory *before* adding it.
                    # Then, after setting up pending_tool_calls_for_ai_turn, we add assistant_message_for_memory.

                    history_snapshot_for_tools = list(short_term_memory) # History *before* this assistant's message

                    self.pending_tool_calls_for_ai_turn[ai_turn_key] = {
                        "room_id": room_id,
                        # Use history_snapshot_for_tools, then append assistant_message_for_memory to it for the *actual* history sent to LLM for follow-up
                        "conversation_history_at_tool_call_time": history_snapshot_for_tools + [dict(assistant_message_for_memory)],
                        "expected_count": len(response_event.tool_calls),
                        "accumulated_tool_messages_for_llm": [],
                        "original_ai_response_payload": dict(response_event.original_request_payload),
                        "llm_provider_for_this_turn": llm_provider_for_this_turn
                    }
                
                # Now, add the assistant's message (which might include text and tool_calls) to the main short_term_memory
                # This was previously inside the tool_calls block but should be outside to cover all cases of assistant action.
                # Moved to after tool_calls block.

                for tool_call_model in response_event.tool_calls:
                    # If ToolCall model guarantees these, checks might be simpler.
                    # ToolCall.id is required. ToolCall.function is required. ToolFunction.name is required. ToolFunction.arguments is required string.

                    if not tool_call_model.id or not tool_call_model.function or not tool_call_model.function.name:
                        logger.error(f"RLS: [{room_id}] Invalid ToolCall object received. Skipping. Tool call: {tool_call_model.model_dump_json(indent=2)}")
                        if ai_turn_key and ai_turn_key in self.pending_tool_calls_for_ai_turn:
                             self.pending_tool_calls_for_ai_turn[ai_turn_key]["expected_count"] -=1
                             if self.pending_tool_calls_for_ai_turn[ai_turn_key]["expected_count"] <= 0: 
                                 del self.pending_tool_calls_for_ai_turn[ai_turn_key] 
                        continue
                    
                    # Arguments are part of the tool_call_model.function.arguments (as a string)
                    # ToolExecutionService will need to parse them if it receives the ToolCall object.
                    # The ExecuteToolRequest takes the full tool_call_model.

                    conversation_history_for_tool_execution_context = []
                    if ai_turn_key and ai_turn_key in self.pending_tool_calls_for_ai_turn:
                        # This snapshot is what the LLM will see on follow-up, it includes the current assistant message with tool calls
                        conversation_history_for_tool_execution_context = list(self.pending_tool_calls_for_ai_turn[ai_turn_key]["conversation_history_at_tool_call_time"])
                    else:
                        logger.error(f"RLS: [{room_id}] ai_turn_key missing when preparing ExecuteToolRequest. Using current short_term_memory + assistant_message as fallback.")
                        # Ensure assistant_message_for_memory is a dict that HistoricalMessage can parse
                        cloned_assistant_message = dict(assistant_message_for_memory)
                        if cloned_assistant_message.get("tool_calls") and isinstance(cloned_assistant_message["tool_calls"], list):
                            # Ensure tool_calls within are also appropriate for HistoricalMessage (i.e., ToolCall objects)
                            # This should be fine as assistant_message_for_memory["tool_calls"] = response_event.tool_calls (List[ToolCall])
                            pass
                        conversation_history_for_tool_execution_context = list(short_term_memory) + [cloned_assistant_message]


                    execute_tool_request = ExecuteToolRequest(
                        room_id=room_id,
                        tool_call=tool_call_model, # Pass the ToolCall Pydantic model directly
                        original_request_payload=dict(response_event.original_request_payload),
                        llm_provider_info={
                            "name": llm_provider_for_this_turn,
                            "model": response_event.original_request_payload.get("actual_model_name_used", 
                                     response_event.original_request_payload.get("requested_model_name"))
                        },
                        conversation_history_snapshot=conversation_history_for_tool_execution_context,
                        last_user_event_id=last_user_event_id_in_batch 
                    )
                    await self.bus.publish(execute_tool_request)
                    logger.info(f"RLS: [{room_id}] Published ExecuteToolRequest for tool: {tool_call_model.function.name}, call_id: {tool_call_model.id}")
            
            # Add assistant's complete message (text and/or tool_calls) to memory
            # This should happen if the assistant acted (sent text, called tools, or both)
            if assistant_acted: # assistant_acted is true if text was sent OR if tool_calls were made
                # Ensure content is None if only tool_calls are present and no actual text_response_content
                if not text_response_content and assistant_message_for_memory.get("tool_calls"):
                    assistant_message_for_memory["content"] = None
                
                # Only add to memory if there's something to add (content or tool_calls)
                if assistant_message_for_memory.get("content") is not None or assistant_message_for_memory.get("tool_calls"):
                    # Avoid duplicate if already added by a more specific path (though current logic should prevent this)
                    if not short_term_memory or short_term_memory[-1] != assistant_message_for_memory:
                        short_term_memory.append(dict(assistant_message_for_memory))
            
            if not assistant_acted:
                 logger.info(f"RLS: [{room_id}] AI ({llm_provider_for_this_turn}) reported success but produced no text and no tool calls.")
                 if not short_term_memory or short_term_memory[-1]["role"] != "assistant":
                    short_term_memory.append({"role": "assistant", "name": current_bot_name, "content": "[AI chose to do nothing this turn]"})

        elif not response_event.success: 
            ai_error_text = f"Sorry, AI error: {response_event.error_message or 'Unknown error'}"
            await self.bus.publish(SendMatrixMessageCommand(room_id=room_id, text=ai_error_text))
            short_term_memory.append({"role": "assistant", "name": current_bot_name, "content": ai_error_text, "event_id": representative_event_id_for_user_turn})
            assistant_acted = True 

        while len(short_term_memory) > self.short_term_memory_items:
            short_term_memory.pop(0)
        config['memory'] = short_term_memory

    async def _handle_tool_execution_response(self, exec_response: ToolExecutionResponse):
        orp = exec_response.original_request_payload # This is AIInferenceResponseEvent's original_request_payload
        ai_turn_key = orp.get("turn_request_id")
        room_id = orp.get("room_id")

        if not ai_turn_key or not room_id:
            logger.error(f"RoomLogic: Received ToolExecutionResponse with missing turn_request_id or room_id. Ignoring. Payload: {orp}") # Changed print to logger.error
            return

        turn_state = self.pending_tool_calls_for_ai_turn.get(ai_turn_key)
        if not turn_state:
            logger.warning(f"RoomLogic: [{room_id}] Received ToolExecutionResponse for unknown/completed AI turn {ai_turn_key}. Ignoring.") # Changed print to logger.warning
            return

        config = self.room_activity_config.get(room_id)
        if not config: 
            logger.error(f"RoomLogic: [{room_id}] Config not found for tool execution response. AI Turn: {ai_turn_key}. Ignoring.") # Changed print to logger.error
            if ai_turn_key in self.pending_tool_calls_for_ai_turn:
                del self.pending_tool_calls_for_ai_turn[ai_turn_key]
            return
        
        short_term_memory = config.get('memory', [])

        tool_message_for_llm = {
            "role": "tool",
            "tool_call_id": exec_response.original_tool_call_id,
            "content": exec_response.result_for_llm_history
        }
        short_term_memory.append(tool_message_for_llm)
        turn_state["accumulated_tool_messages_for_llm"].append(tool_message_for_llm)
        
        logger.info(f"RoomLogic: [{room_id}] Tool '{exec_response.tool_name}' result processed for AI turn {ai_turn_key}.") # Corrected: Use exec_response.tool_name

        if len(turn_state["accumulated_tool_messages_for_llm"]) == turn_state["expected_count"]:
            logger.info(f"RoomLogic: [{room_id}] All {turn_state['expected_count']} tool results received for AI turn {ai_turn_key}. Requesting follow-up LLM call.") # Changed print to logger.info
            
            final_messages_for_follow_up = turn_state["conversation_history_at_tool_call_time"] + turn_state["accumulated_tool_messages_for_llm"]
            follow_up_ai_request_id = str(uuid.uuid4())
            
            original_ai_payload_from_initial_response = turn_state["original_ai_response_payload"]
            follow_up_original_payload = dict(original_ai_payload_from_initial_response) 
            follow_up_original_payload["is_follow_up_after_tool_execution"] = True
            follow_up_original_payload["previous_ai_turn_id"] = ai_turn_key
            follow_up_original_payload["turn_request_id"] = follow_up_ai_request_id 

            provider_for_follow_up = turn_state.get("llm_provider_for_this_turn", self.primary_llm_provider)
            model_for_follow_up: str
            FollowUpEventClass: type[AIInferenceRequestEvent]

            if provider_for_follow_up == "ollama":
                model_for_follow_up = original_ai_payload_from_initial_response.get("actual_model_name_used", 
                                           original_ai_payload_from_initial_response.get("requested_model_name", self.ollama_chat_model))
                FollowUpEventClass = OllamaInferenceRequestEvent
            else: # Default to openrouter
                model_for_follow_up = original_ai_payload_from_initial_response.get("actual_model_name_used", 
                                           original_ai_payload_from_initial_response.get("requested_model_name", self.openrouter_chat_model))
                FollowUpEventClass = OpenRouterInferenceRequestEvent

            follow_up_original_payload["requested_model_name"] = model_for_follow_up 
            follow_up_original_payload["current_llm_provider"] = provider_for_follow_up

            ai_follow_up_request = FollowUpEventClass(
                request_id=follow_up_ai_request_id,
                reply_to_service_event="ai_chat_response_received", 
                original_request_payload=follow_up_original_payload,
                model_name=model_for_follow_up,
                messages_payload=final_messages_for_follow_up,
                tools=self.tool_registry.get_all_tool_definitions(), 
                tool_choice="auto" 
            )
            await self.bus.publish(ai_follow_up_request)
            
            del self.pending_tool_calls_for_ai_turn[ai_turn_key] 

        while len(short_term_memory) > self.short_term_memory_items:
            short_term_memory.pop(0)
        config['memory'] = short_term_memory
        # logger.info(f"RoomLogic: [{room_id}] Memory updated after tool response. Size: {len(short_term_memory)}.") # Changed print to logger.info, and commented out as it might be too verbose

    async def _manage_room_decay(self, room_id: str):
        try:
            while not self._stop_event.is_set():
                config = self.room_activity_config.get(room_id)
                if not config or not config.get('is_active_listening'): break

                await asyncio.sleep(config['current_interval'])

                config = self.room_activity_config.get(room_id) # Re-fetch
                if not config or not config.get('is_active_listening'): break

                if (time.time() - config['last_message_timestamp']) >= config['current_interval']:
                    new_interval = min(config['current_interval'] * 2, self.max_interval)
                    config['current_interval'] = new_interval
                    if new_interval == self.max_interval: config['max_interval_no_activity_cycles'] +=1
                    else: config['max_interval_no_activity_cycles'] = 0

                    if config['max_interval_no_activity_cycles'] >= self.inactivity_cycles:
                        config['is_active_listening'] = False
                        logger.info(f"RLS: [{room_id}] Deactivating listening due to inactivity.")

                        batch_task = config.get('batch_response_task')
                        if batch_task and not batch_task.done():
                            logger.info(f"RLS: [{room_id}] Decay: awaiting final batch task.")
                            try:
                                await asyncio.wait_for(batch_task, timeout=self.batch_delay + 2.0)
                            except (asyncio.TimeoutError, asyncio.CancelledError): pass
                        
                        # Instead of calling self._request_ai_summary directly,
                        # The ManageChannelSummaryTool should be invoked by the LLM if a summary is desired upon deactivation.
                        # For a forced summary on deactivation, this might require a specific system event or logic
                        # if the LLM isn't expected to manage this. For now, direct call is removed.
                        # Consider if a specific "RequestFinalSummaryCommand" should be published here, 
                        # which the ManageChannelSummaryTool could listen for, or if LLM is solely responsible.
                        # For now, relying on LLM to call manage_channel_summary tool with action="request_update"
                        # if it deems a summary is needed based on conversation context before prolonged inactivity.
                        logger.info(f"RLS: [{room_id}] Listening deactivated. Summary will be handled by LLM via tool if needed.")

                        await self._update_global_presence()
                        break
                else: # Activity occurred
                    config['max_interval_no_activity_cycles'] = 0
        except asyncio.CancelledError:
            logger.info(f"RLS: [{room_id}] Decay manager cancelled.")


    async def run(self):
        logger.info("RoomLogicService: Starting...")
        self.bus.subscribe(BotDisplayNameReadyEvent.model_fields['event_type'].default, self._handle_bot_display_name_ready)
        self.bus.subscribe(MatrixMessageReceivedEvent.model_fields['event_type'].default, self._handle_matrix_message)
        self.bus.subscribe(ActivateListeningEvent.model_fields['event_type'].default, self._handle_activate_listening)
        self.bus.subscribe(ProcessMessageBatchCommand.model_fields['event_type'].default, self._handle_process_message_batch)
        self.bus.subscribe("ai_chat_response_received", self._handle_ai_chat_response)
        self.bus.subscribe(ToolExecutionResponse.model_fields['event_type'].default, self._handle_tool_execution_response) # Added

        await self._stop_event.wait()
        # Cleanup internal tasks
        for room_id, config in list(self.room_activity_config.items()): # Iterate over a copy
            if config.get('decay_task') and not config['decay_task'].done(): config['decay_task'].cancel()
            if config.get('batch_response_task') and not config['batch_response_task'].done(): config['batch_response_task'].cancel()
            # Await cancellations if necessary, or manage cleanup more robustly
        logger.info("RoomLogicService: Stopped.")

    async def stop(self):
        logger.info("RoomLogicService: Stop requested.")
        self._stop_event.set()