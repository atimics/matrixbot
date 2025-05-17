import asyncio
import time
import os
import uuid
import json # Added for logging AI payload
import logging

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
    ToolExecutionResponse # Added ToolExecutionResponse
)
import prompt_constructor # For building AI payload
import database # For database operations
from tool_manager import ToolRegistry # Added

load_dotenv()

class RoomLogicService:
    def __init__(self, message_bus: MessageBus, tool_registry: ToolRegistry, bot_display_name: str = "ChatBot"): # Added tool_registry
        """Service for managing room logic, batching, and AI interaction."""
        self.bus = message_bus
        self.tool_registry = tool_registry # Store it
        self.bot_display_name = bot_display_name # Set by BotDisplayNameReadyEvent
        self.room_activity_config: Dict[str, Dict[str, Any]] = {}
        self._stop_event = asyncio.Event()
        self._service_start_time = time.time()
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
        config = self.room_activity_config.get(room_id)

        bot_name_lower = self.bot_display_name.lower()
        is_mention = bool(bot_name_lower and bot_name_lower in event.body.lower())

        if is_mention:
            logger.info(f"RoomLogic: [{room_id}] Mention detected.")
            activate_event = ActivateListeningEvent(
                room_id=room_id,
                triggering_event_id=event.event_id
            )
            await self.bus.publish(activate_event)

        config = self.room_activity_config.get(room_id) # Re-fetch in case it was just created
        if config and config.get('is_active_listening'):
            logger.info(f"RoomLogic: [{room_id}] Actively listening. Adding message to batch.")
            config['pending_messages_for_batch'].append({
                "name": event.sender_display_name,
                "content": event.body,
                "event_id": event.event_id
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
            db_summary_info = database.get_summary(room_id) # Assuming database.py is available
            initial_last_event_id_db = db_summary_info[1] if db_summary_info else None

            config = {
                'memory': [], 'pending_messages_for_batch': [],
                'last_event_id_in_db_summary': initial_last_event_id_db,
                'new_turns_since_last_summary': 0,
                'batch_response_task': None,
                'activation_trigger_event_id': event.triggering_event_id # Store the triggering event_id
            }
            self.room_activity_config[room_id] = config
        else:
            # If config exists, update the activation_trigger_event_id if this is a re-activation
            config['activation_trigger_event_id'] = event.triggering_event_id

        config.update({
            'is_active_listening': True,
            'current_interval': self.initial_interval,
            'last_message_timestamp': time.time(),
            'max_interval_no_activity_cycles': 0,
            'decay_task': asyncio.create_task(self._manage_room_decay(room_id))
        })
        await self._update_global_presence()
        logger.info(f"RoomLogic: [{room_id}] Listening activated/reset. Mem size: {len(config['memory'])}. Last DB summary event: {config.get('last_event_id_in_db_summary')}")


    async def _delayed_batch_processing_publisher(self, room_id: str, delay: float):
        try:
            await asyncio.sleep(delay)
            if asyncio.current_task().cancelled(): # type: ignore
                logger.info(f"RoomLogic: [{room_id}] Delayed batch publisher cancelled.")
                return
            await self.bus.publish(ProcessMessageBatchCommand(room_id=room_id))
        except asyncio.CancelledError:
            logger.info(f"RoomLogic: [{room_id}] Delayed batch publisher cancelled by exception.")


    async def _handle_process_message_batch(self, command: ProcessMessageBatchCommand):
        room_id = command.room_id
        config = self.room_activity_config.get(room_id)
        if not config or not config.get('is_active_listening'): return

        pending_batch = list(config.get('pending_messages_for_batch', []))
        config['pending_messages_for_batch'] = []

        if not pending_batch: return

        logger.info(f"RoomLogic: [{room_id}] Processing message batch of size {len(pending_batch)}.")

        # --- Tell Gateway to start typing ---
        await self.bus.publish(SetTypingIndicatorCommand(room_id=room_id, typing=True))

        short_term_memory = config.get('memory', [])
        summary_text_for_prompt, _ = database.get_summary(room_id) or (None, None)
        
        # Determine the event_id of the last user message in the batch to suggest as a reply target
        last_user_event_id_in_batch = None
        if pending_batch:
            last_user_event_id_in_batch = pending_batch[-1].get("event_id")


        ai_payload = prompt_constructor.build_messages_for_ai(
            historical_messages=list(short_term_memory), 
            current_batched_user_inputs=pending_batch,
            bot_display_name=self.bot_display_name,
            channel_summary=summary_text_for_prompt,
            last_user_event_id_in_batch=last_user_event_id_in_batch
        )

        turn_request_id = str(uuid.uuid4())
        # This payload is passed through to AIInferenceResponseEvent.original_request_payload
        # and then to ExecuteToolRequest.original_request_payload
        # and then to ToolExecutionResponse.original_request_payload
        original_payload_for_ai_response = {
            "room_id": room_id, 
            "pending_batch_for_memory": pending_batch,
            "last_user_event_id_in_batch": last_user_event_id_in_batch,
            "turn_request_id": turn_request_id, # Key for pending_tool_calls state
            "requested_model_name": self.openrouter_chat_model # Model requested
            # AIInferenceService should add actual_model_name_used and actual_llm_provider_name if different
        }

        ai_request = AIInferenceRequestEvent(
            request_id=turn_request_id,
            reply_to_service_event="ai_chat_response_received",
            original_request_payload=original_payload_for_ai_response,
            model_name=self.openrouter_chat_model, # TODO: Allow Ollama/other models
            messages_payload=ai_payload,
            tools=self.tool_registry.get_all_tool_definitions() # Pass available tools
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
        representative_event_id_for_user_turn = None # Will be the event_id of the last message in user batch

        # Add user messages from the processed batch to memory
        if not response_event.original_request_payload.get("is_follow_up_after_tool_call") and \
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
        assistant_acted = False

        if response_event.success:
            if response_event.text_response:
                assistant_message_for_memory["content"] = response_event.text_response
                # Send text response immediately if it exists
                await self.bus.publish(SendMatrixMessageCommand(room_id=room_id, text=response_event.text_response))
                assistant_acted = True

            if response_event.tool_calls:
                logger.info(f"RLS: [{room_id}] LLM ({llm_provider_for_this_turn}) tool_calls: {json.dumps(response_event.tool_calls, indent=2)}")
                assistant_message_for_memory["tool_calls"] = response_event.tool_calls
                assistant_acted = True # Assistant acted by calling tools

                # Add assistant message with tool_calls to memory BEFORE processing them.
                # This is important for the conversation flow.
                if assistant_message_for_memory.get("content") or assistant_message_for_memory.get("tool_calls"):
                    # Ensure content is None if only tool_calls are present, to match OpenAI spec
                    if not assistant_message_for_memory.get("content") and assistant_message_for_memory.get("tool_calls"):
                        assistant_message_for_memory["content"] = None
                    short_term_memory.append(dict(assistant_message_for_memory)) 

                pending_follow_up_llm_request = False

                for tool_call in response_event.tool_calls:
                    tool_function_data = tool_call.get("function", {})
                    tool_name = tool_function_data.get("name")
                    tool_call_id = tool_call.get("id") or f"ollama_tool_{uuid.uuid4()}" # Ollama might not provide an ID

                    try:
                        raw_arguments = tool_function_data.get("arguments", {})
                        if isinstance(raw_arguments, str): # From OpenRouter
                            tool_args = json.loads(raw_arguments)
                        else: # From Ollama (already a dict)
                            tool_args = raw_arguments
                    except json.JSONDecodeError:
                        logger.error(f"RLS: [{room_id}] Invalid JSON arguments for tool {tool_name}: {raw_arguments}")
                        short_term_memory.append({
                            "role": "tool", "tool_call_id": tool_call_id,
                            "name": tool_name, 
                            "content": f"[Tool {tool_name} execution failed: Invalid arguments]"
                        })
                        if llm_provider_for_this_turn == "ollama": pending_follow_up_llm_request = True
                        continue

                    # --- Handle the "call_openrouter_llm" tool specifically ---
                    if tool_name == "call_openrouter_llm" and llm_provider_for_this_turn == "ollama":
                        logger.info(f"RLS: [{room_id}] Ollama wants to call OpenRouter. Args: {tool_args}")

                        or_model_name = tool_args.get("model_name") or self.openrouter_chat_model
                        or_messages = tool_args.get("messages_payload")
                        or_prompt = tool_args.get("prompt_text")

                        if not or_messages and or_prompt:
                            or_messages = [{"role": "user", "content": or_prompt}]
                        elif not or_messages and not or_prompt:
                            logger.warning(f"RLS: [{room_id}] call_openrouter_llm: Missing 'messages_payload' or 'prompt_text'.")
                            short_term_memory.append({
                                "role": "tool", "tool_call_id": tool_call_id, "name": tool_name,
                                "content": f"[Tool {tool_name} failed: Missing prompt or messages_payload]"
                            })
                            pending_follow_up_llm_request = True
                            continue
                        
                        delegated_request_id = str(uuid.uuid4())
                        payload_for_or_response_handler = {
                            "room_id": room_id,
                            "original_ollama_tool_call_id": tool_call_id,
                            "original_user_event_id": last_user_event_id_in_batch, 
                            "ollama_conversation_memory_snapshot": list(short_term_memory) # Memory up to Ollama's tool request
                        }

                        openrouter_request = OpenRouterInferenceRequestEvent( # Explicitly OpenRouter
                            request_id=delegated_request_id,
                            reply_to_service_event="ollama_tool_openrouter_response_received",
                            original_request_payload=payload_for_or_response_handler,
                            model_name=or_model_name,
                            messages_payload=or_messages,
                            tools=self._available_tools, 
                            tool_choice="auto"
                        )
                        await self.bus.publish(openrouter_request)
                        logger.info(f"RLS: [{room_id}] Delegated to OpenRouter (Req ID: {delegated_request_id}) for Ollama tool call {tool_call_id}")
                        pending_follow_up_llm_request = False # Follow-up handled by OR response handler
                        continue # Next tool call or finish

                    # --- Handle other tools (send_reply, react_to_message) ---
                    else: 
                        tool_result_content = f"[Tool {tool_name} execution started]"
                        # Resolve event_id placeholders
                        if tool_name == "send_reply":
                            reply_to_event_id_arg = tool_args.get("reply_to_event_id")
                            if reply_to_event_id_arg and isinstance(reply_to_event_id_arg, str) and reply_to_event_id_arg.startswith("$event"):
                                tool_args["reply_to_event_id"] = last_user_event_id_in_batch
                            elif not reply_to_event_id_arg and last_user_event_id_in_batch:
                                logger.warning(f"RLS: [{room_id}] send_reply by {llm_provider_for_this_turn}: LLM did not provide reply_to_event_id, using fallback: {last_user_event_id_in_batch}")
                                tool_args["reply_to_event_id"] = last_user_event_id_in_batch
                        elif tool_name == "react_to_message":
                            target_event_id_arg = tool_args.get("target_event_id")
                            if target_event_id_arg and isinstance(target_event_id_arg, str) and target_event_id_arg.startswith("$event"):
                                tool_args["target_event_id"] = last_user_event_id_in_batch
                            elif not target_event_id_arg and last_user_event_id_in_batch:
                                logger.warning(f"RLS: [{room_id}] react_to_message by {llm_provider_for_this_turn}: LLM did not provide target_event_id, using fallback: {last_user_event_id_in_batch}")

                        if tool_name == "send_reply":
                            text = tool_args.get("text")
                            reply_to_event_id = tool_args.get("reply_to_event_id")
                            if text and reply_to_event_id:
                                await self.bus.publish(SendReplyCommand(room_id=room_id, text=text, reply_to_event_id=reply_to_event_id))
                                tool_result_content = f"[Tool {tool_name} executed: Sent reply]"
                            else: 
                                tool_result_content = f"[Tool {tool_name} failed: Missing arguments]"
                                logger.warning(f"RLS: [{room_id}] send_reply failed. Args: {tool_args}")
                        elif tool_name == "react_to_message":
                            target_event_id = tool_args.get("target_event_id")
                            reaction_key = tool_args.get("reaction_key")
                            if target_event_id and reaction_key:
                                await self.bus.publish(ReactToMessageCommand(room_id=room_id, target_event_id=target_event_id, reaction_key=reaction_key))
                                tool_result_content = f"[Tool {tool_name} executed: Sent reaction '{reaction_key}']"
                            else: 
                                tool_result_content = f"[Tool {tool_name} failed: Missing arguments]"
                                logger.warning(f"RLS: [{room_id}] react_to_message failed. Args: {tool_args}")
                        else:
                            logger.warning(f"RLS: [{room_id}] Unknown tool requested by {llm_provider_for_this_turn}: {tool_name}")
                            tool_result_content = f"[Tool {tool_name} failed: Unknown tool]"

                        short_term_memory.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "name": tool_name, # OpenAI requires name for role:tool if id is from assistant
                            "content": tool_result_content
                        })
                        if llm_provider_for_this_turn == "ollama" or llm_provider_for_this_turn == "openrouter": # OpenRouter might also need follow-up if it uses tools
                            pending_follow_up_llm_request = True
                
                # If LLM made standard tool calls (not call_openrouter_llm that defers the follow-up),
                # we need to send another request to LLM with the tool results.
                if pending_follow_up_llm_request:
                    logger.info(f"RLS: [{room_id}] Sending follow-up request to {llm_provider_for_this_turn} with tool results.")
                    follow_up_payload = prompt_constructor.build_messages_for_ai(
                        historical_messages=list(short_term_memory),
                        current_batched_user_inputs=[], 
                        bot_display_name=self.bot_display_name,
                        channel_summary=database.get_summary(room_id)[0] if database.get_summary(room_id) else None,
                        last_user_event_id_in_batch=last_user_event_id_in_batch,
                        include_system_prompt=False 
                    )
                    follow_up_request_id = str(uuid.uuid4())
                    original_payload_for_follow_up = {
                        "room_id": room_id,
                        "pending_batch_for_memory": [], 
                        "last_user_event_id_in_batch": last_user_event_id_in_batch,
                        "current_llm_provider": llm_provider_for_this_turn,
                        "is_follow_up_after_tool_call": True
                    }
                    
                    target_model_for_follow_up = self.ollama_chat_model if llm_provider_for_this_turn == "ollama" else self.openrouter_chat_model
                    tools_for_follow_up = (self._available_tools or []) + ([self._openrouter_tool_definition] if llm_provider_for_this_turn == "ollama" else [])

                    follow_up_request_event_class = OllamaInferenceRequestEvent if llm_provider_for_this_turn == "ollama" else OpenRouterInferenceRequestEvent

                    ai_request = follow_up_request_event_class(
                        request_id=follow_up_request_id,
                        reply_to_service_event="ai_chat_response_received",
                        original_request_payload=original_payload_for_follow_up,
                        model_name=target_model_for_follow_up, 
                        messages_payload=follow_up_payload,
                        tools=tools_for_follow_up,
                        tool_choice="auto"
                    )
                    await self.bus.publish(ai_request)
                    # Current handler execution finishes. Bot's final text response comes from next LLM turn.

            elif not response_event.tool_calls and response_event.text_response: # Simple text response, no tools
                # Assistant message (text only) already added to memory if assistant_acted was true.
                # If assistant_acted was false (e.g. error in AI service before producing text), this won't run.
                # If assistant_acted is true, and text_response is present, it means it was already added.
                # This case is for when there is ONLY a text response and NO tool calls.
                # The initial assistant_message_for_memory would have content, and assistant_acted would be true.
                # We need to ensure it's added to memory if it hasn't been (e.g. if it was a direct text response).
                if not assistant_message_for_memory.get("tool_calls") and assistant_message_for_memory.get("content"):
                    # Check if it's already the last message to avoid duplicates if already added
                    if not short_term_memory or short_term_memory[-1] != assistant_message_for_memory:
                         short_term_memory.append(dict(assistant_message_for_memory))
            
            # If assistant_acted is false at this point, it means AI success but no text and no tools.
            # This is unusual but possible. Log it. Memory update handled by initial check.
            if not assistant_acted:
                 logger.info(f"RLS: [{room_id}] AI ({llm_provider_for_this_turn}) reported success but produced no text and no tool calls.")
                 # Add a placeholder to memory if nothing else was added for assistant turn
                 if not short_term_memory or short_term_memory[-1]["role"] != "assistant":
                    short_term_memory.append({"role": "assistant", "name": current_bot_name, "content": "[AI chose to do nothing this turn]"})


        elif not response_event.success: # AI call failed
            ai_error_text = f"Sorry, AI error: {response_event.error_message or 'Unknown error'}"
            await self.bus.publish(SendMatrixMessageCommand(room_id=room_id, text=ai_error_text))
            short_term_memory.append({"role": "assistant", "name": current_bot_name, "content": ai_error_text, "event_id": representative_event_id_for_user_turn})
            assistant_acted = True # Considered an action (informing user of error)

        # Trim memory
        while len(short_term_memory) > self.short_term_memory_items:
            short_term_memory.pop(0)
        config['memory'] = short_term_memory

    async def _handle_tool_execution_response(self, exec_response: ToolExecutionResponse):
        orp = exec_response.original_request_payload # This is AIInferenceResponseEvent's original_request_payload
        ai_turn_key = orp.get("turn_request_id")
        room_id = orp.get("room_id")

        if not ai_turn_key or not room_id:
            print(f"RoomLogic: Received ToolExecutionResponse with missing turn_request_id or room_id. Ignoring. Payload: {orp}")
            return

        turn_state = self.pending_tool_calls_for_ai_turn.get(ai_turn_key)
        if not turn_state:
            print(f"RoomLogic: [{room_id}] Received ToolExecutionResponse for unknown/completed AI turn {ai_turn_key}. Ignoring.")
            return

        config = self.room_activity_config.get(room_id)
        if not config: 
            print(f"RoomLogic: [{room_id}] Config not found for tool execution response. AI Turn: {ai_turn_key}. Ignoring.")
            # Clean up orphan state if necessary
            if ai_turn_key in self.pending_tool_calls_for_ai_turn:
                del self.pending_tool_calls_for_ai_turn[ai_turn_key]
            return
        
        short_term_memory = config.get('memory', [])

        # 1. Create and add tool message to short-term memory and turn state
        tool_message_for_llm = {
            "role": "tool",
            "tool_call_id": exec_response.original_tool_call_id,
            "name": exec_response.tool_name,
            "content": exec_response.result_for_llm_history
            # No event_id for tool messages as per OpenAI spec
        }
        short_term_memory.append(tool_message_for_llm)
        turn_state["accumulated_tool_messages_for_llm"].append(tool_message_for_llm)
        
        print(f"RoomLogic: [{room_id}] Tool '{exec_response.tool_name}' result processed for AI turn {ai_turn_key}.")

        # 2. Check if all tool calls for this AI turn have been processed
        if len(turn_state["accumulated_tool_messages_for_llm"]) == turn_state["expected_count"]:
            print(f"RoomLogic: [{room_id}] All {turn_state['expected_count']} tool results received for AI turn {ai_turn_key}. Requesting follow-up LLM call.")
            
            # Prepare messages for the follow-up LLM call
            # History already includes user msg, assistant msg with tool_calls. Now add tool results.
            messages_for_follow_up = list(turn_state["conversation_history_at_tool_call_time"]) # This snapshot includes the assistant message with tool_calls
            # The tool messages were individually added to short_term_memory already.
            # For the follow-up, we need the history *up to* the assistant's tool_call message,
            # then all the tool responses.
            # The `conversation_history_at_tool_call_time` is correct as it was taken *after* assistant msg.
            # Now, we need to ensure the `accumulated_tool_messages_for_llm` are appended to *that specific snapshot*
            # for the AI call, not necessarily to the live `short_term_memory` if other things happened.
            # However, `short_term_memory` was updated sequentially, so it should be fine.
            # The prompt says: messages_payload: Will be the conversation_history_snapshot ... plus the original assistant message with its tool_calls object, PLUS all the new role: "tool" messages.
            # `turn_state["conversation_history_at_tool_call_time"]` IS this history.
            # And `turn_state["accumulated_tool_messages_for_llm"]` are the new tool messages.
            
            final_messages_for_follow_up = turn_state["conversation_history_at_tool_call_time"] + turn_state["accumulated_tool_messages_for_llm"]

            follow_up_ai_request_id = str(uuid.uuid4())
            
            # Use original provider details for follow-up, but mark as follow-up
            original_ai_payload = turn_state["original_ai_response_payload"]
            follow_up_original_payload = dict(original_ai_payload) # shallow copy
            follow_up_original_payload["is_follow_up_after_tool_execution"] = True
            follow_up_original_payload["previous_ai_turn_id"] = ai_turn_key
            follow_up_original_payload["turn_request_id"] = follow_up_ai_request_id # New turn_request_id for this specific request

            # Determine model for follow-up (e.g., from original request)
            model_for_follow_up = original_ai_payload.get("actual_model_name_used", original_ai_payload.get("requested_model_name", self.openrouter_chat_model))

            ai_follow_up_request = AIInferenceRequestEvent(
                request_id=follow_up_ai_request_id,
                reply_to_service_event="ai_chat_response_received", # Back to the same handler
                original_request_payload=follow_up_original_payload,
                model_name=model_for_follow_up,
                messages_payload=final_messages_for_follow_up,
                tools=self.tool_registry.get_all_tool_definitions(), # LLM might call more tools
                tool_choice="auto" # Or "none" if tools are not expected after this
            )
            await self.bus.publish(ai_follow_up_request)
            
            del self.pending_tool_calls_for_ai_turn[ai_turn_key] # Clean up state

        # Memory trimming and persistence (happens after each tool result or after follow-up is sent)
        while len(short_term_memory) > self.short_term_memory_items:
            short_term_memory.pop(0)
        config['memory'] = short_term_memory
        # print(f"RoomLogic: [{room_id}] Memory updated after tool response. Size: {len(short_term_memory)}.")

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