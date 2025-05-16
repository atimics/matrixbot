import asyncio
import time
import os
import uuid
import json # Added for logging AI payload
import logging

# Set up logger for this module
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# import aiohttp # No longer needed here for typing indicator

from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

from message_bus import MessageBus
from event_definitions import (
    MatrixMessageReceivedEvent, AIInferenceRequestEvent, AIInferenceResponseEvent,
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
        self.openrouter_chat_model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
        self.openrouter_summary_model = os.getenv("OPENROUTER_SUMMARY_MODEL", os.getenv("OPENROUTER_MODEL", "openai/gpt-3.5-turbo")) # Added for summaries

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


        # Modify the system prompt or add a user message to guide the LLM about available event_ids for tools
        # For now, we'll rely on the LLM to infer from context or we can add a specific message.
        # Example of adding context for tool use (can be refined):
        # tool_guidance_messages = []
        # if last_user_event_id_in_batch:
        #     tool_guidance_messages.append({
        #         "role": "system", # Or a specific "tool_context" role if supported/useful
        #         "content": f"Context for tool use: The most recent user message ID is {last_user_event_id_in_batch}. If you need to reply or react to it, use this ID."
        #     })

        ai_payload = prompt_constructor.build_messages_for_ai(
            historical_messages=list(short_term_memory), # + tool_guidance_messages, # Optionally add guidance
            current_batched_user_inputs=pending_batch,
            bot_display_name=self.bot_display_name,
            channel_summary=summary_text_for_prompt,
            last_user_event_id_in_batch=last_user_event_id_in_batch
            # global_summary_text can be added here if implemented
        )

        request_id = str(uuid.uuid4())
        
        # Prepare original_request_payload with any info needed by _handle_ai_chat_response
        # including the last_user_event_id_in_batch for potential default reply/reaction target.
        original_payload_for_ai_response = {
            "room_id": room_id, 
            "pending_batch_for_memory": pending_batch,
            "last_user_event_id_in_batch": last_user_event_id_in_batch
        }

        ai_request = AIInferenceRequestEvent(
            request_id=request_id,
            reply_to_service_event="ai_chat_response_received",
            original_request_payload=original_payload_for_ai_response,
            model_name=self.openrouter_chat_model,
            messages_payload=ai_payload,
            tools=self._available_tools, # Pass defined tools
            tool_choice="auto" # Let the LLM decide
        )
        await self.bus.publish(ai_request)


    async def _handle_ai_chat_response(self, response_event: AIInferenceResponseEvent):
        room_id = response_event.original_request_payload.get("room_id")
        if not room_id:
            logger.error("RoomLogic: Error - AIResponse missing room_id in original_request_payload")
            return

        config = self.room_activity_config.get(room_id)
        if not config:
            logger.error(f"RoomLogic: [{room_id}] Error - No config found for room after AIResponse")
            return

        current_bot_name = self.bot_display_name if isinstance(self.bot_display_name, str) else "ChatBot"
        last_user_event_id_in_batch = response_event.original_request_payload.get("last_user_event_id_in_batch")

        await self.bus.publish(SetTypingIndicatorCommand(room_id=room_id, typing=False))

        short_term_memory = config.get('memory', [])
        pending_batch_for_memory = response_event.original_request_payload.get("pending_batch_for_memory", [])
        representative_event_id_for_user_turn = None

        if pending_batch_for_memory:
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
                logger.error(f"RoomLogic: [{room_id}] Error processing pending_batch_for_memory for memory: {e}. Batch: {pending_batch_for_memory}")

        # Always define assistant_message_for_memory before use
        assistant_message_for_memory: Dict[str, Any] = {"role": "assistant", "name": current_bot_name}
        assistant_acted = False

        # Add the assistant's response (text and/or tool_calls) to memory

        # --- LOGGING: Tool call handling ---
        if response_event.tool_calls:
            logger.info(f"[{room_id}] LLM tool_calls: {json.dumps(response_event.tool_calls, indent=2)}")

        if response_event.success:
            if response_event.text_response:
                assistant_message_for_memory["content"] = response_event.text_response
                # Publish text response to Matrix
                await self.bus.publish(SendMatrixMessageCommand(room_id=room_id, text=response_event.text_response))
                assistant_acted = True
            
            if response_event.tool_calls:
                assistant_message_for_memory["tool_calls"] = response_event.tool_calls
                # This assistant message (now potentially with content and tool_calls) is added ONCE.
                # Subsequent "role": "tool" messages will provide results for these calls.
                assistant_acted = True # Even if content is null, tool_calls mean action

                # Add assistant message to memory BEFORE processing tool results
                # This ensures the "assistant" message with "tool_calls" precedes "tool" role messages
                if assistant_message_for_memory.get("content") or assistant_message_for_memory.get("tool_calls"):
                    short_term_memory.append(assistant_message_for_memory)

                # Process Tool Calls and add their results to memory
                for tool_call in response_event.tool_calls:
                    tool_name = tool_call.get("function", {}).get("name")
                    tool_call_id = tool_call.get("id")
                    try:
                        tool_args_raw = tool_call.get("function", {}).get("arguments", "{}")
                        tool_args = json.loads(tool_args_raw)
                        # --- Post-process event_id fields to replace placeholders ---
                        if tool_name == "send_reply":
                            reply_to_event_id = tool_args.get("reply_to_event_id")
                            if reply_to_event_id and reply_to_event_id.startswith("$event"):
                                tool_args["reply_to_event_id"] = last_user_event_id_in_batch
                        elif tool_name == "react_to_message":
                            target_event_id = tool_args.get("target_event_id")
                            if target_event_id and target_event_id.startswith("$event"):
                                tool_args["target_event_id"] = last_user_event_id_in_batch
                        logger.info(f"[{room_id}] Tool call '{tool_name}' args: {tool_args}")
                    except json.JSONDecodeError:
                        logger.error(f"[{room_id}] Invalid JSON arguments for tool {tool_name}: {tool_call.get('function', {}).get('arguments')}")
                        # Add a "tool" role message indicating failure for this specific tool_call_id
                        if tool_call_id:
                            short_term_memory.append({
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": f"[Tool {tool_name} execution failed: Invalid arguments]"
                            })
                        continue 

                    # Log fallback usage for event IDs
                    if tool_name == "send_reply":
                        text = tool_args.get("text")
                        reply_to_event_id = tool_args.get("reply_to_event_id") or last_user_event_id_in_batch
                        if text and reply_to_event_id:
                            await self.bus.publish(SendReplyCommand(room_id=room_id, text=text, reply_to_event_id=reply_to_event_id))
                            tool_result_content = f"[Tool {tool_name} executed: Sent reply]"
                            tool_executed_successfully = True
                        else:
                            print(f"RoomLogic: [{room_id}] Missing text or reply_to_event_id for send_reply tool. Args: {tool_args}")
                            tool_result_content = f"[Tool {tool_name} failed: Missing arguments]"
                            if not reply_to_event_id:
                                logger.warning(f"[{room_id}] send_reply: LLM did not provide reply_to_event_id, using fallback: {last_user_event_id_in_batch}")
                    
                    elif tool_name == "react_to_message":
                        target_event_id = tool_args.get("target_event_id") or last_user_event_id_in_batch
                        reaction_key = tool_args.get("reaction_key")
                        if target_event_id and reaction_key:
                            await self.bus.publish(ReactToMessageCommand(room_id=room_id, target_event_id=target_event_id, reaction_key=reaction_key))
                            tool_result_content = f"[Tool {tool_name} executed: Sent reaction \'{reaction_key}\']"
                            tool_executed_successfully = True
                        else:
                            print(f"RoomLogic: [{room_id}] Missing target_event_id or reaction_key for react_to_message. Args: {tool_args}")
                            tool_result_content = f"[Tool {tool_name} failed: Missing arguments]"
                            if not target_event_id:
                                logger.warning(f"[{room_id}] react_to_message: LLM did not provide target_event_id, using fallback: {last_user_event_id_in_batch}")
                    else:
                        print(f"RoomLogic: [{room_id}] Unknown tool requested: {tool_name}")
                        tool_result_content = f"[Tool {tool_name} failed: Unknown tool]"

                    # Add "tool" role message to memory with the result
                    if tool_call_id:
                        short_term_memory.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            # "name": tool_name, # OpenAI does not expect 'name' here, it's inferred from tool_call_id
                            "content": tool_result_content
                        })
            
            else: # No tool_calls, only text_response (or neither if LLM chose to say nothing with success=true)
                if assistant_message_for_memory.get("content"): # If there was a text response
                     short_term_memory.append(assistant_message_for_memory)
                elif not assistant_acted : # Success true, but no text and no tools
                    print(f"RoomLogic: [{room_id}] AI returned success but no text and no tool calls.")
                    short_term_memory.append({
                        "role": "assistant", "name": current_bot_name,
                        "content": "[The AI chose not to send a message or use a tool in this turn.]",
                        "event_id": representative_event_id_for_user_turn
                    })


        elif not response_event.success: # AI call failed
            ai_text = f"Sorry, AI error: {response_event.error_message or 'Unknown error'}"
            await self.bus.publish(SendMatrixMessageCommand(room_id=room_id, text=ai_text))
            short_term_memory.append({"role": "assistant", "name": current_bot_name, "content": ai_text, "event_id": representative_event_id_for_user_turn})

        # Trim memory
        while len(short_term_memory) > self.short_term_memory_items:
            short_term_memory.pop(0)
        config['memory'] = short_term_memory

        if config.get('new_turns_since_last_summary', 0) >= int(os.getenv("SUMMARY_UPDATE_MESSAGE_TURNS", "7")):
            await self._request_ai_summary(room_id, force_update=False)

    async def _request_ai_summary(self, room_id: str, force_update: bool = False):
        config = self.room_activity_config.get(room_id)
        if not config:
            print(f"RoomLogic: [{room_id}] No config found, cannot request summary.")
            return

        messages_for_this_summary_attempt = list(config.get('memory', []))
        db_summary_info = database.get_summary(room_id) # Call once
        previous_summary_text, last_event_id_summarized_in_db = db_summary_info if db_summary_info else (None, None)

        # If not forcing an update, and there are no new messages in memory to summarize, skip.
        if not force_update and not messages_for_this_summary_attempt:
            print(f"RoomLogic: [{room_id}] No new messages to summarize and not a forced update. Skipping summary.")
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
            print(f"RoomLogic: [{room_id}] Cannot request summary: No valid event_id anchor could be determined. (Force: {force_update}, Msgs in attempt: {len(messages_for_this_summary_attempt)})")
            return

        # If we are here, a summary will be attempted.
        ai_payload = prompt_constructor.build_summary_generation_payload(
            messages_to_summarize=messages_for_this_summary_attempt,
            bot_display_name=self.bot_display_name,
            previous_summary=previous_summary_text
        )

        request_id = str(uuid.uuid4())
        ai_request = AIInferenceRequestEvent(
            request_id=request_id,
            reply_to_service_event="ai_summary_response_received",
            original_request_payload={
                "room_id": room_id, 
                "event_id_of_last_message_in_summary_batch": event_id_for_this_summary
            },
            model_name=self.openrouter_summary_model,
            messages_payload=ai_payload,
            tools=None,
            tool_choice=None
        )
        await self.bus.publish(ai_request)
        config['new_turns_since_last_summary'] = 0 # Reset counter as summary request was made
        print(f"RoomLogic: [{room_id}] Requested AI summary. Event anchor: {event_id_for_this_summary}. Msgs in batch: {len(messages_for_this_summary_attempt)}. Forced: {force_update}")

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
                        print(f"RoomLogic: [{room_id}] Deactivating listening due to inactivity.")

                        batch_task = config.get('batch_response_task')
                        if batch_task and not batch_task.done():
                            print(f"RoomLogic: [{room_id}] Decay: awaiting final batch task.")
                            try:
                                await asyncio.wait_for(batch_task, timeout=self.batch_delay + 2.0)
                            except (asyncio.TimeoutError, asyncio.CancelledError): pass

                        await self._request_ai_summary(room_id, force_update=True)
                        await self._update_global_presence()
                        break
                else: # Activity occurred
                    config['max_interval_no_activity_cycles'] = 0
        except asyncio.CancelledError:
            print(f"RoomLogic: [{room_id}] Decay manager cancelled.")


    async def run(self):
        print("RoomLogicService: Starting...")
        self.bus.subscribe(BotDisplayNameReadyEvent.model_fields['event_type'].default, self._handle_bot_display_name_ready)
        self.bus.subscribe(MatrixMessageReceivedEvent.model_fields['event_type'].default, self._handle_matrix_message)
        self.bus.subscribe(ActivateListeningEvent.model_fields['event_type'].default, self._handle_activate_listening)
        self.bus.subscribe(ProcessMessageBatchCommand.model_fields['event_type'].default, self._handle_process_message_batch)
        self.bus.subscribe("ai_chat_response_received", self._handle_ai_chat_response)

        await self._stop_event.wait()
        # Cleanup internal tasks
        for room_id, config in list(self.room_activity_config.items()): # Iterate over a copy
            if config.get('decay_task') and not config['decay_task'].done(): config['decay_task'].cancel()
            if config.get('batch_response_task') and not config['batch_response_task'].done(): config['batch_response_task'].cancel()
            # Await cancellations if necessary, or manage cleanup more robustly
        print("RoomLogicService: Stopped.")

    async def stop(self):
        print("RoomLogicService: Stop requested.")
        self._stop_event.set()