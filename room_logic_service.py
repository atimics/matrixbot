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
    ReactToMessageCommand, SendReplyCommand # Added tool commands
)
import prompt_constructor # For building AI payload
import database # For database operations

load_dotenv()

class RoomLogicService:
    def __init__(self, message_bus: MessageBus, bot_display_name: str = "ChatBot"):
        """Service for managing room logic, batching, and AI interaction."""
        self.bus = message_bus
        self.bot_display_name = bot_display_name # Set by BotDisplayNameReadyEvent
        self.room_activity_config: Dict[str, Dict[str, Any]] = {}
        self._stop_event = asyncio.Event()
        self._service_start_time = time.time()

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

        self._available_tools = [
            {
                "type": "function",
                "function": {
                    "name": "send_reply",
                    "description": "Sends a textual reply message to the current room.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "The text content of the reply message."
                            },
                            "reply_to_event_id": {
                                "type": "string",
                                "description": "The event ID of the message to reply to. This visually quotes the original message."
                            }
                        },
                        "required": ["text", "reply_to_event_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "react_to_message",
                    "description": "Reacts to a specific message with an emoji or text.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_event_id": {
                                "type": "string",
                                "description": "The event ID of the message to react to."
                            },
                            "reaction_key": {
                                "type": "string",
                                "description": "The reaction emoji or key (e.g., '👍', '😄')."
                            }
                        },
                        "required": ["target_event_id", "reaction_key"]
                    }
                }
            }
        ]

        self._openrouter_tool_definition = {
            "type": "function",
            "function": {
                "name": "call_openrouter_llm",
                "description": "Delegates a complex query or a query requiring specific capabilities to a powerful cloud-based LLM (OpenRouter). Use this for tasks that local models might struggle with or for accessing specific proprietary models.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "model_name": {
                            "type": "string",
                            "description": "The specific OpenRouter model to use (e.g., \'openai/gpt-4o\', \'anthropic/claude-3-opus\'). If unsure, a default powerful model will be selected."
                        },
                        "messages_payload": {
                            "type": "array",
                            "description": "The conversation history and prompt to send to the OpenRouter LLM, in OpenAI message format.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "role": {"type": "string", "enum": ["system", "user", "assistant"]},
                                    "content": {"type": "string"}
                                },
                                "required": ["role", "content"]
                            }
                        },
                        "prompt_text": {
                            "type": "string",
                            "description": "Alternatively, provide a single prompt text. If \'messages_payload\' is given, this is ignored."
                        }
                        # We might also allow \'tools\' and \'tool_choice\' to be passed to OpenRouter
                    },
                    "required": [] # Make it flexible: either messages_payload or prompt_text
                }
            }
        }

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

        request_id = str(uuid.uuid4())
        
        original_payload_for_ai_response = {
            "room_id": room_id, 
            "pending_batch_for_memory": pending_batch,
            "last_user_event_id_in_batch": last_user_event_id_in_batch,
            "current_llm_provider": self.primary_llm_provider # Track which provider is active for this turn
        }

        target_model_name: str
        current_tools_for_llm: Optional[List[Dict[str, Any]]] = None
        request_event_class = None # Placeholder for the specific event class

        if self.primary_llm_provider == "ollama":
            target_model_name = self.ollama_chat_model
            # Offer the OpenRouter tool AND any existing tools (_available_tools) to Ollama
            current_tools_for_llm = (self._available_tools or []) + [self._openrouter_tool_definition]
            original_payload_for_ai_response["llm_service_target"] = "ollama" # For clarity
            request_event_class = OllamaInferenceRequestEvent
        else: # openrouter is primary
            target_model_name = self.openrouter_chat_model
            current_tools_for_llm = self._available_tools
            original_payload_for_ai_response["llm_service_target"] = "openrouter"
            request_event_class = OpenRouterInferenceRequestEvent

        ai_request = request_event_class(
            request_id=request_id,
            reply_to_service_event="ai_chat_response_received", # Both services will publish to this
            original_request_payload=original_payload_for_ai_response,
            model_name=target_model_name,
            messages_payload=ai_payload, # This is the constructed payload for the LLM
            tools=current_tools_for_llm,
            tool_choice="auto" # Or be more specific if needed
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

        # Request summary if conditions met, but not if we are in a multi-turn tool call sequence
        # (e.g. Ollama called OR, or Ollama/OR called a regular tool and is awaiting its own follow-up)
        is_intermediate_tool_step = response_event.original_request_payload.get("is_follow_up_after_tool_call") or \
                                    response_event.original_request_payload.get("is_follow_up_after_delegated_tool_call") or \
                                    (llm_provider_for_this_turn == "ollama" and any(tc.get("function",{}).get("name") == "call_openrouter_llm" for tc in (response_event.tool_calls or [])))
        
        if not is_intermediate_tool_step and assistant_acted: # Only consider summary if assistant took a meaningful action or completed a chain
            if config.get('new_turns_since_last_summary', 0) >= int(os.getenv("SUMMARY_UPDATE_MESSAGE_TURNS", "7")):
                await self._request_ai_summary(room_id, force_update=False)

    async def _handle_ollama_tool_openrouter_response(self, or_response_event: AIInferenceResponseEvent):
        original_ollama_payload = or_response_event.original_request_payload
        room_id = original_ollama_payload.get("room_id")
        ollama_tool_call_id = original_ollama_payload.get("original_ollama_tool_call_id")
        original_user_event_id = original_ollama_payload.get("original_user_event_id") # For context
        # The memory snapshot is taken *before* Ollama's tool call that triggered OpenRouter.
        # We need to append the result of the OpenRouter call to this snapshot.
        ollama_memory_snapshot = original_ollama_payload.get("ollama_conversation_memory_snapshot", [])

        if not room_id or not ollama_tool_call_id:
            logger.error(f"RLS: Missing room_id or ollama_tool_call_id in OpenRouter response for Ollama. Req ID: {or_response_event.request_id}")
            return

        logger.info(f"RLS: [{room_id}] Received OpenRouter response for Ollama tool call {ollama_tool_call_id}. Success: {or_response_event.success}")
        config = self.room_activity_config.get(room_id)
        if not config: return

        # short_term_memory = config.get('memory', []) # Use the snapshot instead of current live memory
        current_memory_for_ollama_follow_up = list(ollama_memory_snapshot) # Start with the snapshot

        tool_result_content_for_ollama: str

        if or_response_event.success:
            # Construct a single string result for Ollama, summarizing OpenRouter's actions.
            # If OpenRouter itself used tools, those would have been handled by AIInferenceService or this handler if OR called back to RLS.
            # For now, we assume OR gives a text response, or its tool calls are self-contained or simplified here.
            final_or_text = or_response_event.text_response or ""
            final_or_tool_calls_summary = ""
            if or_response_event.tool_calls:
                # This part needs to be careful: if OpenRouter calls *our* tools (send_reply, react_to_message),
                # those actions would have already been performed by the main _handle_ai_chat_response (if OR was primary)
                # or by a similar logic if AIInferenceService directly handles them.
                # For now, just summarize that OR suggested tools.
                final_or_tool_calls_summary = f" OpenRouter also suggested tool calls: {json.dumps(or_response_event.tool_calls)}"
            
            if final_or_text or final_or_tool_calls_summary:
                tool_result_content_for_ollama = f"{final_or_text}{final_or_tool_calls_summary}".strip()
            else:
                tool_result_content_for_ollama = "[OpenRouter returned no text and no tool calls]"
        else:
            tool_result_content_for_ollama = f"[OpenRouter call failed: {or_response_event.error_message or 'Unknown error'}]"

        # Add the "tool" role message (result of call_openrouter_llm) to Ollama's conversation history (the snapshot)
        current_memory_for_ollama_follow_up.append({
            "role": "tool",
            "tool_call_id": ollama_tool_call_id, 
            # "name": "call_openrouter_llm", # Not strictly needed by OpenAI if tool_call_id is present
            "content": tool_result_content_for_ollama
        })

        # Now, make a new request to Ollama with the updated history
        logger.info(f"RLS: [{room_id}] Sending follow-up request to Ollama after OpenRouter tool execution.")
        follow_up_payload = prompt_constructor.build_messages_for_ai(
            historical_messages=current_memory_for_ollama_follow_up,
            current_batched_user_inputs=[], 
            bot_display_name=self.bot_display_name,
            channel_summary=database.get_summary(room_id)[0] if database.get_summary(room_id) else None,
            last_user_event_id_in_batch=original_user_event_id, # from the original user turn
            include_system_prompt=False 
        )

        next_ollama_request_id = str(uuid.uuid4())
        payload_for_final_ollama_response = {
            "room_id": room_id,
            "pending_batch_for_memory": [], # No new user messages for this turn
            "last_user_event_id_in_batch": original_user_event_id,
            "current_llm_provider": "ollama",
            "is_follow_up_after_delegated_tool_call": True # Indicate this is the final response turn from Ollama
        }
        ollama_final_request = OllamaInferenceRequestEvent( # Explicitly Ollama
            request_id=next_ollama_request_id,
            reply_to_service_event="ai_chat_response_received", # Back to the main handler
            original_request_payload=payload_for_final_ollama_response,
            model_name=self.ollama_chat_model,
            messages_payload=follow_up_payload,
            tools=(self._available_tools or []) + [self._openrouter_tool_definition], # Offer tools again
            tool_choice="auto"
        )
        await self.bus.publish(ollama_final_request)
        # The live short_term_memory in config will be updated by _handle_ai_chat_response when Ollama's final response comes.
        # For now, we've used a snapshot and are sending it back to Ollama.
        # The key is that original_user_event_id and other context is preserved.
        config['memory'] = current_memory_for_ollama_follow_up # Persist the memory up to this point

    async def _request_ai_summary(self, room_id: str, force_update: bool = False):
        config = self.room_activity_config.get(room_id)
        if not config:
            logger.warning(f"RLS: [{room_id}] No config found, cannot request summary.")
            return

        messages_for_this_summary_attempt = list(config.get('memory', []))
        db_summary_info = database.get_summary(room_id) # Call once
        previous_summary_text, last_event_id_summarized_in_db = db_summary_info if db_summary_info else (None, None)

        # If not forcing an update, and there are no new messages in memory to summarize, skip.
        if not force_update and not messages_for_this_summary_attempt:
            logger.info(f"RLS: [{room_id}] No new messages to summarize and not a forced update. Skipping summary.")
            return

        event_id_for_this_summary: Optional[str] = None
        # Find the latest event_id from the messages to be summarized by looking backwards.
        for msg in reversed(messages_for_this_summary_attempt):
            if msg.get("event_id"):
                event_id_for_this_summary = msg.get("event_id")
                break
        
        # If no event_id found in current messages, and this is a forced update, try fallbacks.
        if not event_id_for_this_summary and force_update:
            event_id_for_this_summary = last_event_id_summarized_in_db or config.get('activation_trigger_event_id')

        # If still no anchor after all checks, we cannot proceed.
        if not event_id_for_this_summary:
            logger.warning(f"RLS: [{room_id}] Cannot request summary: No valid event_id anchor could be determined. (Force: {force_update}, Msgs in attempt: {len(messages_for_this_summary_attempt)})")
            return

        # If we are here, a summary will be attempted.
        ai_payload = prompt_constructor.build_summary_generation_payload(
            messages_to_summarize=messages_for_this_summary_attempt,
            bot_display_name=self.bot_display_name,
            previous_summary=previous_summary_text
        )

        request_id = str(uuid.uuid4())
        
        summary_model_to_use = self.ollama_summary_model if self.primary_llm_provider == "ollama" else self.openrouter_summary_model
        # Determine which provider and model to use for summarization
        # For now, let's assume summaries also follow PRIMARY_LLM_PROVIDER.
        # This could be made more specific with a dedicated SUMMARY_LLM_PROVIDER env var if needed.
        summary_request_event_class = OllamaInferenceRequestEvent if self.primary_llm_provider == "ollama" else OpenRouterInferenceRequestEvent

        ai_request = summary_request_event_class(
            request_id=request_id,
            reply_to_service_event="ai_summary_response_received",
            original_request_payload={
                "room_id": room_id, 
                "event_id_of_last_message_in_summary_batch": event_id_for_this_summary
            },
            model_name=summary_model_to_use, # Use the selected summary model
            messages_payload=ai_payload,
            tools=None,
            tool_choice=None
        )
        await self.bus.publish(ai_request)
        config['new_turns_since_last_summary'] = 0 # Reset counter as summary request was made
        logger.info(f"RLS: [{room_id}] Requested AI summary. Event anchor: {event_id_for_this_summary}. Msgs in batch: {len(messages_for_this_summary_attempt)}. Forced: {force_update}")

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

                        await self._request_ai_summary(room_id, force_update=True)
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
        self.bus.subscribe("ollama_tool_openrouter_response_received", self._handle_ollama_tool_openrouter_response)

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