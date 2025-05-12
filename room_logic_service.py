import asyncio
import time
import os
import uuid
# import aiohttp # No longer needed here for typing indicator

from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

from message_bus import MessageBus
from event_definitions import (
    MatrixMessageReceivedEvent, AIInferenceRequestEvent, AIInferenceResponseEvent,
    SendMatrixMessageCommand, ProcessMessageBatchCommand, ActivateListeningEvent,
    GenerateSummaryRequestEvent, BotDisplayNameReadyEvent,
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

        self._status_cache: Dict[str, Any] = {"value": None, "expires_at": 0.0}
        self.status_cache_ttl = int(os.getenv("AI_STATUS_TEXT_CACHE_TTL", "3600"))  # 1 hour default


    async def _handle_bot_display_name_ready(self, event: BotDisplayNameReadyEvent):
        self.bot_display_name = event.display_name
        print(f"RoomLogic: Bot display name updated to '{self.bot_display_name}'")

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
                'batch_response_task': None
            }
            self.room_activity_config[room_id] = config

        config.update({
            'is_active_listening': True,
            'current_interval': self.initial_interval,
            'last_message_timestamp': time.time(),
            'max_interval_no_activity_cycles': 0,
            'decay_task': asyncio.create_task(self._manage_room_decay(room_id))
        })

        await self.bus.publish(SetPresenceCommand(
            presence="online"
        ))

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
        if not room_id: return

        config = self.room_activity_config.get(room_id)
        if not config: return

        ai_text = "Sorry, I had a problem processing that."
        if response_event.success and response_event.text_response:
            ai_text = response_event.text_response
        elif response_event.error_message:
            ai_text = f"Sorry, AI error: {response_event.error_message}"

        # --- Tell Gateway to stop typing ---
        # Do this *before* sending the message for better perceived responsiveness
        await self.bus.publish(SetTypingIndicatorCommand(room_id=room_id, typing=False))

        await self.bus.publish(SendMatrixMessageCommand(room_id=room_id, text=ai_text))

        # Update short-term memory
        short_term_memory = config.get('memory', [])
        pending_batch_for_memory = response_event.original_request_payload.get("pending_batch_for_memory", [])

        if pending_batch_for_memory:
            # Combine user messages for memory
            combined_user_content = "".join(f"{msg['name']}: {msg['content']}\n" for msg in pending_batch_for_memory)
            # Get the event_id of the *last* message in the user batch for reference
            representative_event_id = pending_batch_for_memory[-1]["event_id"]

            short_term_memory.append({
                "role": "user",
                "name": pending_batch_for_memory[0]["name"], # Use name from first message in batch
                "content": combined_user_content.strip(),
                "event_id": representative_event_id # Store last event_id of the batch
            })
            config['new_turns_since_last_summary'] = config.get('new_turns_since_last_summary', 0) + 1

        if response_event.success and response_event.text_response:
             short_term_memory.append({
                "role": "assistant", "name": self.bot_display_name,
                "content": response_event.text_response,
                "event_id": representative_event_id # Associate AI response with the user turn it replies to
            })

        # Trim memory
        while len(short_term_memory) > self.short_term_memory_items:
            short_term_memory.pop(0)
        config['memory'] = short_term_memory

        # Trigger summary if needed
        if config.get('new_turns_since_last_summary', 0) >= int(os.getenv("SUMMARY_UPDATE_MESSAGE_TURNS", "7")):
            await self.bus.publish(GenerateSummaryRequestEvent(room_id=room_id, force_update=False))


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

                        await self.bus.publish(GenerateSummaryRequestEvent(room_id=room_id, force_update=True))

                        await self.bus.publish(SetPresenceCommand(
                            presence="unavailable"
                        ))

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