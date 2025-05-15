import asyncio
import time
import os
import uuid
import json # Added for logging AI payload
# import aiohttp # No longer needed here for typing indicator

from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

from message_bus import MessageBus
from event_definitions import (
    MatrixMessageReceivedEvent, AIInferenceRequestEvent, AIInferenceResponseEvent,
    SendMatrixMessageCommand, ProcessMessageBatchCommand, ActivateListeningEvent,
    BotDisplayNameReadyEvent,
    SetTypingIndicatorCommand, SetPresenceCommand
)
import prompt_constructor # For building AI payload
import database # For database operations

load_dotenv()

class RoomLogicService:
    def __init__(self, message_bus: MessageBus, bot_display_name: str = "ChatBot"):
        self.bus = message_bus
        self.bot_display_name = bot_display_name # Set by BotDisplayNameReadyEvent
        self.room_activity_config: Dict[str, Dict[str, Any]] = {}
        self._stop_event = asyncio.Event()

        # Configurable values
        self.initial_interval = int(os.getenv("POLLING_INITIAL_INTERVAL", "10"))
        self.max_interval = int(os.getenv("POLLING_MAX_INTERVAL", "120"))
        self.inactivity_cycles = int(os.getenv("POLLING_INACTIVITY_DECAY_CYCLES", "3"))
        self.batch_delay = float(os.getenv("MESSAGE_BATCH_DELAY", "3.0"))
        self.short_term_memory_items = int(os.getenv("MAX_MESSAGES_PER_ROOM_MEMORY_ITEMS", "20"))
        self.openrouter_chat_model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
        self.openrouter_summary_model = os.getenv("OPENROUTER_SUMMARY_MODEL", os.getenv("OPENROUTER_MODEL", "openai/gpt-3.5-turbo")) # Added for summaries

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
        print(f"RoomLogic: Bot display name updated to '{self.bot_display_name}'")
        # Set presence to unavailable on startup
        await self._update_global_presence()

    async def _handle_matrix_message(self, event: MatrixMessageReceivedEvent):
        room_id = event.room_id
        config = self.room_activity_config.get(room_id)

        bot_name_lower = self.bot_display_name.lower()
        is_mention = bool(bot_name_lower and bot_name_lower in event.body.lower())

        if is_mention:
            # print(f"RoomLogic: [{room_id}] Mention detected.")
            activate_event = ActivateListeningEvent(
                room_id=room_id,
                triggering_event_id=event.event_id
            )
            await self.bus.publish(activate_event)

        config = self.room_activity_config.get(room_id) # Re-fetch in case it was just created
        if config and config.get('is_active_listening'):
            # print(f"RoomLogic: [{room_id}] Actively listening. Adding message to batch.")
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
                    print(f"RoomLogic: [{room_id}] Previous batch task raised {e} while being awaited after cancellation.")
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
        print(f"RoomLogic: [{room_id}] Listening activated/reset. Mem size: {len(config['memory'])}. Last DB summary event: {config.get('last_event_id_in_db_summary')}")


    async def _delayed_batch_processing_publisher(self, room_id: str, delay: float):
        try:
            await asyncio.sleep(delay)
            if asyncio.current_task().cancelled(): # type: ignore
                # print(f"RoomLogic: [{room_id}] Delayed batch publisher cancelled.")
                return
            await self.bus.publish(ProcessMessageBatchCommand(room_id=room_id))
        except asyncio.CancelledError:
            pass


    async def _handle_process_message_batch(self, command: ProcessMessageBatchCommand):
        room_id = command.room_id
        config = self.room_activity_config.get(room_id)
        if not config or not config.get('is_active_listening'): return

        pending_batch = list(config.get('pending_messages_for_batch', []))
        config['pending_messages_for_batch'] = []

        if not pending_batch: return

        # --- Tell Gateway to start typing ---
        await self.bus.publish(SetTypingIndicatorCommand(room_id=room_id, typing=True))

        short_term_memory = config.get('memory', [])
        summary_text_for_prompt, _ = database.get_summary(room_id) or (None, None)

        ai_payload = prompt_constructor.build_messages_for_ai(
            historical_messages=list(short_term_memory),
            current_batched_user_inputs=pending_batch,
            bot_display_name=self.bot_display_name,
            channel_summary=summary_text_for_prompt
        )

        request_id = str(uuid.uuid4())
        ai_request = AIInferenceRequestEvent(
            request_id=request_id,
            reply_to_service_event="ai_chat_response_received",
            original_request_payload={"room_id": room_id, "pending_batch_for_memory": pending_batch},
            model_name=self.openrouter_chat_model,
            messages_payload=ai_payload
        )
        await self.bus.publish(ai_request)


    async def _handle_ai_chat_response(self, response_event: AIInferenceResponseEvent):
        room_id = response_event.original_request_payload.get("room_id")
        if not room_id:
            print("RoomLogic: Error - AIResponse missing room_id in original_request_payload")
            return

        config = self.room_activity_config.get(room_id)
        if not config:
            print(f"RoomLogic: [{room_id}] Error - No config found for room after AIResponse")
            return

        # Ensure self.bot_display_name is a string and not None
        if not isinstance(self.bot_display_name, str) or self.bot_display_name is None:
            print(f"RoomLogic: [{room_id}] Error - self.bot_display_name is invalid: {self.bot_display_name}")
            # Fallback or error handling for bot_display_name
            # This should ideally not happen if BotDisplayNameReadyEvent works correctly.
            current_bot_name = "ChatBot" # Fallback
        else:
            current_bot_name = self.bot_display_name

        ai_text = "Sorry, I had a problem processing that."
        if response_event.success and response_event.text_response:
            ai_text = response_event.text_response
        elif response_event.error_message:
            ai_text = f"Sorry, AI error: {response_event.error_message}"

        # --- Tell Gateway to stop typing ---
        await self.bus.publish(SetTypingIndicatorCommand(room_id=room_id, typing=False))

        await self.bus.publish(SendMatrixMessageCommand(room_id=room_id, text=ai_text))

        # Update short-term memory
        short_term_memory = config.get('memory', [])
        pending_batch_for_memory = response_event.original_request_payload.get("pending_batch_for_memory", [])

        representative_event_id = None # Initialize to ensure it's always defined

        if pending_batch_for_memory:
            try:
                # Combine user messages for memory
                combined_user_content = "".join(f"{msg['name']}: {msg['content']}\n" for msg in pending_batch_for_memory)
                # Get the event_id of the *last* message in the user batch for reference
                representative_event_id = pending_batch_for_memory[-1]["event_id"]
                user_name_for_memory = pending_batch_for_memory[0]["name"]

                short_term_memory.append({
                    "role": "user",
                    "name": user_name_for_memory, 
                    "content": combined_user_content.strip(),
                    "event_id": representative_event_id 
                })
                config['new_turns_since_last_summary'] = config.get('new_turns_since_last_summary', 0) + 1
            except KeyError as e:
                print(f"RoomLogic: [{room_id}] KeyError when processing pending_batch_for_memory: {e}. Batch: {pending_batch_for_memory}")
            except IndexError as e:
                print(f"RoomLogic: [{room_id}] IndexError when processing pending_batch_for_memory: {e}. Batch: {pending_batch_for_memory}")


        if response_event.success and response_event.text_response:
            try:
                short_term_memory.append({
                    "role": "assistant", "name": current_bot_name, # Use validated current_bot_name
                    "content": response_event.text_response,
                    "event_id": representative_event_id # Will be None if pending_batch_for_memory was empty
                })
            except Exception as e:
                print(f"RoomLogic: [{room_id}] Error appending assistant message to memory: {e}")


        # Trim memory
        while len(short_term_memory) > self.short_term_memory_items:
            short_term_memory.pop(0)
        config['memory'] = short_term_memory

        # Trigger summary if needed
        if config.get('new_turns_since_last_summary', 0) >= int(os.getenv("SUMMARY_UPDATE_MESSAGE_TURNS", "7")):
            await self._request_ai_summary(room_id, force_update=False)


    async def _request_ai_summary(self, room_id: str, force_update: bool = False):
        config = self.room_activity_config.get(room_id)
        if not config:
            print(f"RoomLogic: [{room_id}] No config found, cannot request summary.")
            return

        short_term_memory = list(config.get('memory', []))
        previous_summary_text, last_event_id_summarized_in_db = database.get_summary(room_id) or (None, None)

        messages_for_this_summary_attempt = short_term_memory
        
        # Determine the event_id to anchor this summary to.
        event_id_for_this_summary: Optional[str] = None
        if messages_for_this_summary_attempt: # If there are new messages in memory
            event_id_for_this_summary = messages_for_this_summary_attempt[-1].get("event_id")
        elif force_update: # No new messages, but a forced update (e.g. deactivation, initial summary)
            event_id_for_this_summary = last_event_id_summarized_in_db or config.get('activation_trigger_event_id')

        if not event_id_for_this_summary:
            print(f"RoomLogic: [{room_id}] Cannot request summary: No valid event_id anchor could be determined. (Force: {force_update})")
            return

        # Allow empty messages_for_this_summary_attempt if force_update is True
        if not messages_for_this_summary_attempt and not force_update:
            print(f"RoomLogic: [{room_id}] No new messages to summarize and not a forced update. Skipping summary.")
            return

        ai_payload = prompt_constructor.build_summary_generation_payload(
            messages_to_summarize=messages_for_this_summary_attempt, # Can be empty if force_update
            bot_display_name=self.bot_display_name,
            previous_summary=previous_summary_text
        )

        # print(f"RoomLogic: [{room_id}] Summary Generation Payload for AI (model: {self.openrouter_summary_model}):\n{json.dumps(ai_payload, indent=2)}")

        request_id = str(uuid.uuid4())
        ai_request = AIInferenceRequestEvent(
            request_id=request_id,
            reply_to_service_event="ai_summary_response_received",
            original_request_payload={
                "room_id": room_id, 
                "event_id_of_last_message_in_summary_batch": event_id_for_this_summary
            },
            model_name=self.openrouter_summary_model,
            messages_payload=ai_payload
        )
        await self.bus.publish(ai_request)
        config['new_turns_since_last_summary'] = 0
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