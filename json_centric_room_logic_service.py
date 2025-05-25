import asyncio
import time
import os
import uuid
import json
import logging
import datetime

logger = logging.getLogger(__name__)

from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

from message_bus import MessageBus
from event_definitions import (
    MatrixMessageReceivedEvent, MatrixImageReceivedEvent,
    ProcessMessageBatchCommand, ActivateListeningEvent,
    BotDisplayNameReadyEvent,
    SetTypingIndicatorCommand, SetPresenceCommand,
    ThinkingRequestEvent, ThinkingResponseEvent,
    StructuredPlanningRequestEvent, StructuredPlanningResponseEvent,
    ChannelContext, ChannelContextBatch, AIThoughts,
    SendMatrixMessageCommand
)
from action_registry_service import ActionRegistryService
from action_execution_service import ActionExecutionService
from json_centric_ai_service import JsonCentricAIService
import database
import prompt_constructor

load_dotenv()

class JsonCentricRoomLogicService:
    """New Room Logic Service using JSON-centric orchestration with two-step AI processing."""
    
    def __init__(self, message_bus: MessageBus, action_registry: ActionRegistryService, 
                 action_executor: ActionExecutionService, ai_service: JsonCentricAIService,
                 db_path: str, bot_display_name: str = "ChatBot", matrix_client=None):
        self.bus = message_bus
        self.action_registry = action_registry
        self.action_executor = action_executor
        self.ai_service = ai_service
        self.db_path = db_path
        self.bot_display_name = bot_display_name
        self.matrix_client = matrix_client
        self.room_activity_config: Dict[str, Dict[str, Any]] = {}
        self._stop_event = asyncio.Event()
        self._service_start_time = datetime.datetime.now(datetime.timezone.utc)

        # Configurable values
        self.initial_interval = int(os.getenv("POLLING_INITIAL_INTERVAL", "10"))
        self.max_interval = int(os.getenv("POLLING_MAX_INTERVAL", "120"))
        self.inactivity_cycles = int(os.getenv("POLLING_INACTIVITY_DECAY_CYCLES", "3"))
        self.batch_delay = float(os.getenv("MESSAGE_BATCH_DELAY", "3.0"))
        self.short_term_memory_items = int(os.getenv("MAX_MESSAGES_PER_ROOM_MEMORY_ITEMS", "20"))
        
        # Model configuration for two-step processing
        self.thinker_model = os.getenv("THINKER_MODEL", "anthropic/claude-3-haiku")
        self.planner_model = os.getenv("PLANNER_MODEL", "openai/gpt-4o")

        self._status_cache: Dict[str, Any] = {"value": None, "expires_at": 0.0}
        self.status_cache_ttl = int(os.getenv("AI_STATUS_TEXT_CACHE_TTL", "3600"))
        self._last_global_presence = None

    async def _handle_bot_display_name_ready(self, event: BotDisplayNameReadyEvent):
        """Handle bot display name being ready."""
        self.bot_display_name = event.display_name
        logger.info(f"JsonCentricRLS: Bot display name set to: {self.bot_display_name}")

    async def _handle_matrix_message(self, event: MatrixMessageReceivedEvent):
        """Handle Matrix message events by adding them to the conversation batch."""
        room_id = event.room_id
        self._ensure_room_config(room_id)
        config = self.room_activity_config[room_id]

        # Add message to pending batch
        config.setdefault("pending_batch", []).append({
            "user_id": event.sender_id,
            "name": event.sender_display_name,
            "content": event.body,
            "event_id": event.event_id_matrix,
            "timestamp": event.timestamp.timestamp()
        })

        logger.info(f"JsonCentricRLS: [{room_id}] Added message to batch from {event.sender_display_name}")
        
        # Schedule batch processing
        await self._schedule_batch_processing(room_id)

    async def _handle_matrix_image(self, event: MatrixImageReceivedEvent):
        """Handle Matrix image events by adding them to the conversation batch."""
        room_id = event.room_id
        self._ensure_room_config(room_id)
        config = self.room_activity_config[room_id]

        # Add image message to pending batch with image URL
        config.setdefault("pending_batch", []).append({
            "user_id": event.sender_id,
            "name": event.sender_display_name,
            "content": event.body or "",
            "event_id": event.event_id_matrix,
            "timestamp": event.timestamp.timestamp(),
            "image_url": event.image_url
        })

        logger.info(f"JsonCentricRLS: [{room_id}] Added image message to batch from {event.sender_display_name}")
        
        # Schedule batch processing
        await self._schedule_batch_processing(room_id)

    async def _handle_activate_listening(self, event: ActivateListeningEvent):
        """Handle activation of listening for a room."""
        room_id = event.room_id
        self._ensure_room_config(room_id)
        config = self.room_activity_config[room_id]
        config['is_active'] = True
        config['last_activity'] = time.time()
        logger.info(f"JsonCentricRLS: [{room_id}] Activated listening")

    def _ensure_room_config(self, room_id: str):
        """Ensure room configuration exists."""
        if room_id not in self.room_activity_config:
            self.room_activity_config[room_id] = {
                'is_active': False,
                'pending_batch': [],
                'memory': [],
                'last_activity': time.time(),
                'polling_interval': self.initial_interval,
                'inactive_cycles': 0,
                'new_turns_since_last_summary': 0
            }

    async def _schedule_batch_processing(self, room_id: str):
        """Schedule batch processing for a room."""
        config = self.room_activity_config[room_id]
        config['last_activity'] = time.time()
        
        # Cancel existing scheduled task if any
        if 'batch_task' in config:
            config['batch_task'].cancel()
        
        # Schedule new batch processing
        config['batch_task'] = asyncio.create_task(
            self._delayed_batch_processing(room_id, self.batch_delay)
        )

    async def _delayed_batch_processing(self, room_id: str, delay: float):
        """Process message batch after delay."""
        await asyncio.sleep(delay)
        await self._process_message_batch(room_id)

    async def _process_message_batch(self, room_id: str):
        """Process the batched messages for a room using JSON-centric orchestration."""
        config = self.room_activity_config.get(room_id)
        if not config or not config.get('pending_batch'):
            return

        logger.info(f"JsonCentricRLS: [{room_id}] Processing batch with {len(config['pending_batch'])} messages")

        # Set typing indicator
        await self.bus.publish(SetTypingIndicatorCommand(room_id=room_id, typing=True))

        try:
            # Build channel context
            channel_context = await self._build_channel_context(room_id, config)
            context_batch = ChannelContextBatch(channel_contexts=[channel_context])

            # Step 1: Send to Thinker AI
            thinking_request_id = str(uuid.uuid4())
            thinking_request = ThinkingRequestEvent(
                request_id=thinking_request_id,
                context_batch=context_batch,
                model_name=self.thinker_model
            )

            # Store context for later use
            config['current_turn_context'] = {
                'thinking_request_id': thinking_request_id,
                'context_batch': context_batch,
                'pending_batch': config['pending_batch'].copy()
            }

            await self.bus.publish(thinking_request)
            logger.info(f"JsonCentricRLS: [{room_id}] Sent thinking request {thinking_request_id}")

        except Exception as e:
            logger.error(f"JsonCentricRLS: [{room_id}] Error processing batch: {e}")
            await self.bus.publish(SetTypingIndicatorCommand(room_id=room_id, typing=False))

    async def _build_channel_context(self, room_id: str, config: Dict[str, Any]) -> ChannelContext:
        """Build the channel context for AI processing."""
        # Get the current user input
        pending_batch = config['pending_batch']
        last_message = pending_batch[-1]
        
        # Build current user input in OpenRouter format
        current_user_input = {
            "sender_id": last_message["user_id"],
            "sender_name": last_message["name"],
            "event_id": last_message["event_id"],
            "timestamp": last_message["timestamp"]
        }

        # Build content array in OpenRouter multi-part format
        content = []
        for msg in pending_batch:
            # Add text content
            if msg.get("content"):
                content.append({
                    "type": "text",
                    "text": f"{msg['name']}: {msg['content']}"
                })
            
            # Add image content if present
            if msg.get("image_url"):
                # Convert Matrix mxc:// URL to S3 URL using image cache service
                # This would be handled by the image cache service
                content.append({
                    "type": "image_url",
                    "image_url": {"url": msg["image_url"]}  # Will be processed by AI service
                })

        # Get message history in OpenRouter format
        message_history = await self._build_message_history(room_id, config)

        # Get channel summary
        channel_summary = None
        summary_data = await database.get_summary(self.db_path, room_id)
        if summary_data:
            channel_summary = summary_data[0]

        # Get user memories for users in context
        current_user_ids = list(set(msg["user_id"] for msg in pending_batch))
        user_memories = []
        for user_id in current_user_ids:
            memories = await database.get_user_memories(self.db_path, user_id)
            if memories:
                for memory in memories:
                    user_memories.append({
                        "user_id": user_id,
                        "memory_text": memory[2],
                        "created_at": memory[3]
                    })

        return ChannelContext(
            channel_id=room_id,
            current_user_input=current_user_input,
            sender_id=last_message["user_id"],
            event_id=last_message["event_id"],
            content=content,
            message_history=message_history,
            channel_summary=channel_summary,
            tool_states=None,  # Could be populated with relevant tool states
            user_memories=user_memories,
            pdf_annotations=None  # Could be populated with PDF annotations if any
        )

    async def _build_message_history(self, room_id: str, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build message history in OpenRouter format."""
        memory = config.get('memory', [])
        history = []

        for msg in memory:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            name = msg.get('name', '')

            if role == 'user':
                # Check if this message had an image
                if msg.get('image_url'):
                    history.append({
                        "role": "user",
                        "name": name,
                        "content": [
                            {"type": "text", "text": content},
                            {"type": "image_url", "image_url": {"url": msg['image_url']}}
                        ]
                    })
                else:
                    history.append({
                        "role": "user",
                        "name": name,
                        "content": content
                    })
            elif role == 'assistant':
                history.append({
                    "role": "assistant",
                    "name": name,
                    "content": content
                })

        return history

    async def _handle_thinking_response(self, event: ThinkingResponseEvent):
        """Handle response from Thinker AI."""
        # Find the room that initiated this thinking request
        room_id = None
        config = None
        
        for rid, cfg in self.room_activity_config.items():
            turn_context = cfg.get('current_turn_context', {})
            if turn_context.get('thinking_request_id') == event.request_id:
                room_id = rid
                config = cfg
                break

        if not room_id or not config:
            logger.error(f"JsonCentricRLS: Could not find room for thinking response {event.request_id}")
            return

        if not event.success:
            logger.error(f"JsonCentricRLS: [{room_id}] Thinking failed: {event.error_message}")
            await self.bus.publish(SetTypingIndicatorCommand(room_id=room_id, typing=False))
            return

        logger.info(f"JsonCentricRLS: [{room_id}] Received thinking response, proceeding to planning")

        try:
            # Step 2: Send to Planner AI
            planning_request_id = str(uuid.uuid4())
            actions_schema = self.action_registry.generate_planner_schema()

            planning_request = StructuredPlanningRequestEvent(
                request_id=planning_request_id,
                thoughts=event.thoughts,
                original_context=config['current_turn_context']['context_batch'],
                model_name=self.planner_model,
                actions_schema=actions_schema
            )

            # Update context for planning
            config['current_turn_context']['planning_request_id'] = planning_request_id
            config['current_turn_context']['thoughts'] = event.thoughts

            await self.bus.publish(planning_request)
            logger.info(f"JsonCentricRLS: [{room_id}] Sent planning request {planning_request_id}")

        except Exception as e:
            logger.error(f"JsonCentricRLS: [{room_id}] Error in planning step: {e}")
            await self.bus.publish(SetTypingIndicatorCommand(room_id=room_id, typing=False))

    async def _handle_structured_planning_response(self, event: StructuredPlanningResponseEvent):
        """Handle response from Planner AI and execute actions."""
        # Find the room that initiated this planning request
        room_id = None
        config = None
        
        for rid, cfg in self.room_activity_config.items():
            turn_context = cfg.get('current_turn_context', {})
            if turn_context.get('planning_request_id') == event.request_id:
                room_id = rid
                config = cfg
                break

        if not room_id or not config:
            logger.error(f"JsonCentricRLS: Could not find room for planning response {event.request_id}")
            return

        # Turn off typing indicator
        await self.bus.publish(SetTypingIndicatorCommand(room_id=room_id, typing=False))

        if not event.success:
            logger.error(f"JsonCentricRLS: [{room_id}] Planning failed: {event.error_message}")
            return

        logger.info(f"JsonCentricRLS: [{room_id}] Received action plan, executing actions")

        try:
            # Execute actions for this room
            if event.action_plan and event.action_plan.channel_responses:
                for channel_response in event.action_plan.channel_responses:
                    if channel_response.channel_id == room_id:
                        # Execute the action plan for this channel
                        results = await self.action_executor.execute_action_plan(
                            event.action_plan,
                            request_id=event.request_id
                        )
                        
                        # Log results
                        for channel_result in results.get("channel_results", []):
                            if channel_result["channel_id"] == room_id:
                                for action_result in channel_result.get("action_results", []):
                                    if action_result.get("success"):
                                        logger.info(f"JsonCentricRLS: [{room_id}] Action {action_result['action_name']} succeeded")
                                    else:
                                        logger.error(f"JsonCentricRLS: [{room_id}] Action {action_result['action_name']} failed: {action_result.get('error', 'Unknown error')}")
                        break  # Only process actions for this room

            # Update memory with the turn
            await self._update_memory_after_turn(room_id, config)

            # Clear pending batch and turn context
            config['pending_batch'].clear()
            config.pop('current_turn_context', None)

            # Check if summary is needed
            if config.get('new_turns_since_last_summary', 0) >= self.short_term_memory_items:
                await self._generate_and_store_summary(room_id)

        except Exception as e:
            logger.error(f"JsonCentricRLS: [{room_id}] Error executing actions: {e}")

    async def _update_memory_after_turn(self, room_id: str, config: Dict[str, Any]):
        """Update memory after completing an AI turn."""
        turn_context = config.get('current_turn_context', {})
        pending_batch = turn_context.get('pending_batch', [])
        thoughts = turn_context.get('thoughts', [])

        short_term_memory = config.get('memory', [])

        # Add user messages to memory
        for msg in pending_batch:
            user_message = {
                "role": "user",
                "name": msg["name"],
                "content": msg["content"],
                "event_id": msg["event_id"],
                "timestamp": msg["timestamp"]
            }
            if msg.get("image_url"):
                user_message["image_url"] = msg["image_url"]
            
            short_term_memory.append(user_message)

        # Add assistant response to memory (based on thoughts/reasoning)
        if thoughts:
            assistant_message = {
                "role": "assistant",
                "name": self.bot_display_name,
                "content": f"AI reasoning: {thoughts[0].thoughts_text if thoughts else 'Processed request'}",
                "timestamp": time.time()
            }
            short_term_memory.append(assistant_message)

        # Trim memory if needed
        while len(short_term_memory) > self.short_term_memory_items:
            short_term_memory.pop(0)

        config['memory'] = short_term_memory
        config['new_turns_since_last_summary'] = config.get('new_turns_since_last_summary', 0) + 1

    async def _generate_and_store_summary(self, room_id: str):
        """Generate and store a summary for the room."""
        # This would use the existing summarization logic
        # For now, just log that it would happen
        logger.info(f"JsonCentricRLS: [{room_id}] Summary generation needed (not implemented yet)")

    async def run(self):
        """Main run loop for the service."""
        logger.info("JsonCentricRoomLogicService: Starting...")
        
        self.bus.subscribe(MatrixMessageReceivedEvent.get_event_type(), self._handle_matrix_message)
        self.bus.subscribe(MatrixImageReceivedEvent.get_event_type(), self._handle_matrix_image)
        self.bus.subscribe(ActivateListeningEvent.get_event_type(), self._handle_activate_listening)
        self.bus.subscribe(BotDisplayNameReadyEvent.get_event_type(), self._handle_bot_display_name_ready)
        
        # Subscribe to AI response events
        self.bus.subscribe(ThinkingResponseEvent.get_event_type(), self._handle_thinking_response)
        self.bus.subscribe(StructuredPlanningResponseEvent.get_event_type(), self._handle_structured_planning_response)
        
        await self._stop_event.wait()
        logger.info("JsonCentricRoomLogicService: Stopped.")

    async def stop(self):
        """Stop the service."""
        logger.info("JsonCentricRoomLogicService: Stop requested.")
        self._stop_event.set()