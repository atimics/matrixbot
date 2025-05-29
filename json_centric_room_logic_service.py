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
    SendMatrixMessageCommand,
    ImageCacheRequestEvent, ImageCacheResponseEvent,  # Added for image processing
    ActionFeedbackRequestEvent, ActionFeedbackResponseEvent,
    FollowUpThinkingRequestEvent, FollowUpPlanningRequestEvent
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

        # Follow-up processing configuration
        self.max_follow_up_phases = int(os.getenv("MAX_FOLLOW_UP_PHASES", "3"))
        self.enable_action_feedback = os.getenv("ENABLE_ACTION_FEEDBACK", "true").lower() == "true"

        self._status_cache: Dict[str, Any] = {"value": None, "expires_at": 0.0}
        self.status_cache_ttl = int(os.getenv("AI_STATUS_TEXT_CACHE_TTL", "3600"))
        self._last_global_presence = None

    async def _get_s3_url_for_image(self, image_url: str) -> Optional[str]:
        """
        Request S3 URL for an image through the image cache service.
        """
        try:
            request_id = str(uuid.uuid4())
            
            # Create a future to wait for the response
            response_future = asyncio.Future()
            
            # Subscribe to the response temporarily
            async def handle_response(event: ImageCacheResponseEvent):
                if event.request_id == request_id:
                    if not response_future.done():
                        response_future.set_result(event)
            
            self.bus.subscribe(ImageCacheResponseEvent.get_event_type(), handle_response)
            
            try:
                # Send the request
                cache_request = ImageCacheRequestEvent(
                    request_id=request_id,
                    image_url=image_url
                )
                await self.bus.publish(cache_request)
                
                # Wait for response with timeout
                response = await asyncio.wait_for(response_future, timeout=30.0)
                
                if response.success and response.s3_url:
                    logger.info(f"JsonCentricRLS: Successfully got S3 URL for image: {image_url} -> {response.s3_url}")
                    return response.s3_url
                else:
                    logger.error(f"JsonCentricRLS: Failed to get S3 URL for image: {image_url}, error: {response.error_message}")
                    return None
                    
            finally:
                # Unsubscribe from the response
                self.bus.unsubscribe(ImageCacheResponseEvent.get_event_type(), handle_response)
                
        except asyncio.TimeoutError:
            logger.error(f"JsonCentricRLS: Timeout waiting for image cache response for: {image_url}")
            return None
        except Exception as e:
            logger.error(f"JsonCentricRLS: Error getting S3 URL for image {image_url}: {e}")
            return None

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

        # Check if there's already a turn in progress
        existing_turn_context = config.get('current_turn_context')
        if existing_turn_context:
            thinking_request_id = existing_turn_context.get('thinking_request_id')
            planning_request_id = existing_turn_context.get('planning_request_id')
            follow_up_context = existing_turn_context.get('follow_up_context', {})
            follow_up_thinking_id = follow_up_context.get('follow_up_thinking_request_id')
            follow_up_planning_id = follow_up_context.get('follow_up_planning_request_id')
            
            logger.info(f"JsonCentricRLS: [{room_id}] Overlap check - existing context with thinking_id={thinking_request_id}, planning_id={planning_request_id}, follow_up_thinking={follow_up_thinking_id} (deprecated), follow_up_planning={follow_up_planning_id}")
            
            if thinking_request_id or planning_request_id or follow_up_thinking_id or follow_up_planning_id:
                pending_requests = []
                if thinking_request_id:
                    pending_requests.append(f"thinking {thinking_request_id}")
                if planning_request_id:
                    pending_requests.append(f"planning {planning_request_id}")
                if follow_up_thinking_id:
                    pending_requests.append(f"follow-up thinking {follow_up_thinking_id} (deprecated)")
                if follow_up_planning_id:
                    pending_requests.append(f"follow-up planning {follow_up_planning_id}")
                
                logger.info(f"JsonCentricRLS: [{room_id}] Delaying batch processing - existing turn in progress with: {', '.join(pending_requests)}")
                
                # Cancel any existing batch task and reschedule processing for later
                if 'batch_task' in config:
                    config['batch_task'].cancel()
                    
                config['batch_task'] = asyncio.create_task(
                    self._delayed_batch_processing(room_id, 2.0)
                )
                return
        else:
            logger.info(f"JsonCentricRLS: [{room_id}] No existing turn context found, proceeding with new turn")

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
            
            logger.info(f"JsonCentricRLS: [{room_id}] Created new turn context with thinking_request_id={thinking_request_id}")

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

        # Build content array in proper OpenRouter multi-part format
        # Each message should be a separate entry with proper structure
        content = []
        
        for msg in pending_batch:
            # Build content parts for this message
            message_content = []
            
            # Add text content if present
            if msg.get("content"):
                message_content.append({
                    "type": "text",
                    "text": msg['content']  # Just the content, not prefixed with name
                })
            
            # Add image content if present - convert Matrix URLs to S3 URLs
            if msg.get("image_url"):
                logger.info(f"JsonCentricRLS: [{room_id}] Processing image URL: {msg['image_url']}")
                
                # Convert Matrix mxc:// URL to S3 URL using image cache service
                s3_url = await self._get_s3_url_for_image(msg["image_url"])
                if s3_url:
                    logger.info(f"JsonCentricRLS: [{room_id}] Successfully converted image to S3: {s3_url}")
                    message_content.append({
                        "type": "image_url",
                        "image_url": {"url": s3_url}
                    })
                else:
                    logger.error(f"JsonCentricRLS: [{room_id}] Failed to convert image to S3, adding text description instead")
                    # Fallback to text description if image processing fails
                    message_content.append({
                        "type": "text",
                        "text": f"[Image failed to process: {msg.get('content', 'No description available')}]"
                    })
            
            # Add this message to content as a properly structured user message
            if message_content:
                content.append({
                    "role": "user",
                    "name": msg['name'],
                    "content": message_content,
                    "timestamp": msg['timestamp'],
                    "event_id": msg['event_id']
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
                    # Convert historical image URLs to S3 URLs too
                    s3_url = await self._get_s3_url_for_image(msg['image_url'])
                    if s3_url:
                        logger.info(f"JsonCentricRLS: [{room_id}] Converted historical image to S3: {s3_url}")
                        history.append({
                            "role": "user",
                            "name": name,
                            "content": [
                                {"type": "text", "text": content},
                                {"type": "image_url", "image_url": {"url": s3_url}}
                            ]
                        })
                    else:
                        logger.error(f"JsonCentricRLS: [{room_id}] Failed to convert historical image, using text only")
                        history.append({
                            "role": "user",
                            "name": name,
                            "content": f"{content} [Historical image failed to process]"
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
            else:
                logger.warning(f"JsonCentricRLS: [{room_id}] Unknown message role in history: {role}")
        
        return history

    async def _handle_thinking_response(self, event: ThinkingResponseEvent):
        """Handle response from Thinker AI (both regular and follow-up)."""
        # Check if this is a follow-up thinking response
        if event.original_request_payload.get("follow_up_type") == "thinking":
            await self._handle_follow_up_thinking_response(event)
            return

        # Find the room that initiated this thinking request
        room_id = None
        config = None
        
        logger.info(f"JsonCentricRLS: Looking for thinking response {event.request_id} in room contexts")
        
        for rid, cfg in self.room_activity_config.items():
            turn_context = cfg.get('current_turn_context', {})
            current_thinking_id = turn_context.get('thinking_request_id')
            logger.info(f"JsonCentricRLS: Room {rid} has thinking_request_id={current_thinking_id}")
            
            if current_thinking_id == event.request_id:
                room_id = rid
                config = cfg
                logger.info(f"JsonCentricRLS: Found matching room {room_id} for thinking response {event.request_id}")
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
        """Handle response from Planner AI and execute actions (both regular and follow-up)."""
        # Check if this is a follow-up planning response
        if event.original_request_payload.get("is_follow_up"):
            logger.debug(f"JsonCentricRLS: Routing follow-up planning response {event.request_id} to follow-up handler")
            try:
                await self._handle_follow_up_planning_response(event)
                return
            except Exception as e:
                logger.error(f"JsonCentricRLS: Error in follow-up planning handler: {e}")
                return

        logger.debug(f"JsonCentricRLS: Processing regular planning response {event.request_id}")

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
                        
                        # Extract action results for potential follow-up processing
                        action_results_for_follow_up = []
                        for channel_result in results.get("channel_results", []):
                            if channel_result["channel_id"] == room_id:
                                action_results_for_follow_up = channel_result.get("action_results", [])
                                
                                # Log results
                                for action_result in action_results_for_follow_up:
                                    if action_result.get("success"):
                                        logger.info(f"JsonCentricRLS: [{room_id}] Action {action_result['action_name']} succeeded")
                                    else:
                                        logger.error(f"JsonCentricRLS: [{room_id}] Action {action_result['action_name']} failed: {action_result.get('error', 'Unknown error')}")
                                break

                        # Initiate follow-up processing if enabled and actions were executed
                        if action_results_for_follow_up and self.enable_action_feedback:
                            await self._initiate_follow_up_processing(
                                room_id, 
                                action_results_for_follow_up, 
                                event.request_id,
                                phase_number=1
                            )
                        else:
                            # No follow-up needed, complete the turn normally
                            await self._complete_turn_processing(room_id, config)
                        break  # Only process actions for this room
            else:
                # No actions executed, complete the turn normally
                await self._complete_turn_processing(room_id, config)

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

    async def _cancel_all_pending_tasks(self):
        """Cancel all pending tasks across all rooms to ensure clean startup."""
        logger.info("JsonCentricRLS: Cancelling all pending tasks from previous sessions...")
        
        cancelled_count = 0
        for room_id, config in self.room_activity_config.items():
            try:
                # Cancel batch processing tasks
                if 'batch_task' in config:
                    batch_task = config['batch_task']
                    if not batch_task.done():
                        batch_task.cancel()
                        logger.info(f"JsonCentricRLS: [{room_id}] Cancelled pending batch task")
                        cancelled_count += 1
                    config.pop('batch_task', None)
                
                # Clear any turn contexts that might have pending requests
                turn_context = config.get('current_turn_context')
                if turn_context:
                    thinking_id = turn_context.get('thinking_request_id')
                    planning_id = turn_context.get('planning_request_id')
                    follow_up_context = turn_context.get('follow_up_context', {})
                    follow_up_thinking_id = follow_up_context.get('follow_up_thinking_request_id')
                    follow_up_planning_id = follow_up_context.get('follow_up_planning_request_id')
                    
                    if thinking_id or planning_id or follow_up_thinking_id or follow_up_planning_id:
                        pending_requests = []
                        if thinking_id:
                            pending_requests.append(f"thinking {thinking_id}")
                        if planning_id:
                            pending_requests.append(f"planning {planning_id}")
                        if follow_up_thinking_id:
                            pending_requests.append(f"follow-up thinking {follow_up_thinking_id}")
                        if follow_up_planning_id:
                            pending_requests.append(f"follow-up planning {follow_up_planning_id}")
                        
                        logger.info(f"JsonCentricRLS: [{room_id}] Clearing orphaned turn context with pending: {', '.join(pending_requests)}")
                        config.pop('current_turn_context', None)
                        cancelled_count += 1
                
                # Clear pending batches to prevent stale processing
                if config.get('pending_batch'):
                    batch_size = len(config['pending_batch'])
                    config['pending_batch'].clear()
                    logger.info(f"JsonCentricRLS: [{room_id}] Cleared {batch_size} pending messages from previous session")
                
            except Exception as e:
                logger.error(f"JsonCentricRLS: Error cancelling tasks for room {room_id}: {e}")
        
        if cancelled_count > 0:
            logger.info(f"JsonCentricRLS: Successfully cancelled {cancelled_count} pending tasks/contexts")
        else:
            logger.info("JsonCentricRLS: No pending tasks found to cancel")

    async def run(self):
        """Main run loop for the service."""
        logger.info("JsonCentricRoomLogicService: Starting...")
        
        # Cancel all pending tasks from previous sessions to ensure clean startup
        await self._cancel_all_pending_tasks()
        
        self.bus.subscribe(MatrixMessageReceivedEvent.get_event_type(), self._handle_matrix_message)
        self.bus.subscribe(MatrixImageReceivedEvent.get_event_type(), self._handle_matrix_image)
        self.bus.subscribe(ActivateListeningEvent.get_event_type(), self._handle_activate_listening)
        self.bus.subscribe(BotDisplayNameReadyEvent.get_event_type(), self._handle_bot_display_name_ready)
        
        # Subscribe to AI response events (handles both regular and follow-up)
        self.bus.subscribe(ThinkingResponseEvent.get_event_type(), self._handle_thinking_response)
        self.bus.subscribe(StructuredPlanningResponseEvent.get_event_type(), self._handle_structured_planning_response)
        
        # Subscribe to follow-up processing events
        self.bus.subscribe(ActionFeedbackResponseEvent.get_event_type(), self._handle_action_feedback_response)
        
        await self._stop_event.wait()
        logger.info("JsonCentricRoomLogicService: Stopped.")

    async def stop(self):
        """Stop the service and cancel all pending tasks."""
        logger.info("JsonCentricRoomLogicService: Stop requested.")
        
        # Cancel all pending tasks before stopping
        await self._cancel_all_pending_tasks()
        
        self._stop_event.set()

    async def _initiate_follow_up_processing(self, room_id: str, action_results: List[Dict[str, Any]], 
                                           original_request_id: str, phase_number: int = 1) -> None:
        """
        Initiate follow-up processing based on action execution results.
        
        This method implements the multi-phase workflow:
        1. Analyze action results to determine if follow-up is needed
        2. If needed, trigger thinking → planning → execution cycle
        3. Support multiple phases with incremental improvement
        """
        config = self.room_activity_config.get(room_id)
        if not config:
            logger.error(f"JsonCentricRLS: [{room_id}] No config found for follow-up processing")
            return

        turn_context = config.get('current_turn_context', {})
        if not turn_context:
            logger.error(f"JsonCentricRLS: [{room_id}] No turn context found for follow-up processing")
            return

        # Check if we've reached the maximum number of follow-up phases
        if phase_number > self.max_follow_up_phases:
            logger.info(f"JsonCentricRLS: [{room_id}] Reached maximum follow-up phases ({self.max_follow_up_phases}), stopping")
            return

        # Skip follow-up if disabled
        if not self.enable_action_feedback:
            logger.info(f"JsonCentricRLS: [{room_id}] Action feedback disabled, skipping follow-up processing")
            return

        logger.info(f"JsonCentricRLS: [{room_id}] Initiating follow-up processing phase {phase_number} for {len(action_results)} actions")

        try:
            # Step 1: Request AI analysis of action results to determine if follow-up is needed
            feedback_request_id = str(uuid.uuid4())
            
            feedback_request = ActionFeedbackRequestEvent(
                request_id=feedback_request_id,
                original_planning_request_id=original_request_id,
                executed_actions=action_results,
                original_context=turn_context['context_batch'],
                model_name=self.planner_model,  # Use planner model for feedback analysis
                phase_number=phase_number
            )

            # Store follow-up context for when feedback response arrives
            turn_context['follow_up_context'] = {
                'feedback_request_id': feedback_request_id,
                'action_results': action_results,
                'phase_number': phase_number,
                'original_request_id': original_request_id
            }

            await self.bus.publish(feedback_request)
            logger.info(f"JsonCentricRLS: [{room_id}] Sent action feedback request {feedback_request_id} for phase {phase_number}")

        except Exception as e:
            logger.error(f"JsonCentricRLS: [{room_id}] Error initiating follow-up processing: {e}")

    async def _handle_action_feedback_response(self, event: ActionFeedbackResponseEvent):
        """Handle response from action feedback analysis."""
        # Find the room that initiated this feedback request
        room_id = None
        config = None
        
        for rid, cfg in self.room_activity_config.items():
            turn_context = cfg.get('current_turn_context', {})
            follow_up_context = turn_context.get('follow_up_context', {})
            if follow_up_context.get('feedback_request_id') == event.request_id:
                room_id = rid
                config = cfg
                break

        if not room_id or not config:
            logger.error(f"JsonCentricRLS: Could not find room for feedback response {event.request_id}")
            return

        if not event.success:
            logger.error(f"JsonCentricRLS: [{room_id}] Action feedback analysis failed: {event.error_message}")
            return

        turn_context = config['current_turn_context']
        follow_up_context = turn_context['follow_up_context']
        phase_number = follow_up_context['phase_number']

        logger.info(f"JsonCentricRLS: [{room_id}] Received feedback response for phase {phase_number}: follow_up_needed={event.needs_follow_up}")

        if not event.needs_follow_up:
            logger.info(f"JsonCentricRLS: [{room_id}] No follow-up needed according to AI analysis. Reason: {event.follow_up_reasoning}")
            # Check if there are pending follow-up requests before clearing context
            follow_up_thinking_id = follow_up_context.get('follow_up_thinking_request_id')
            follow_up_planning_id = follow_up_context.get('follow_up_planning_request_id')
            
            if follow_up_thinking_id or follow_up_planning_id:
                pending_requests = []
                if follow_up_thinking_id:
                    pending_requests.append(f"thinking {follow_up_thinking_id}")
                if follow_up_planning_id:
                    pending_requests.append(f"planning {follow_up_planning_id}")
                logger.info(f"JsonCentricRLS: [{room_id}] Pending follow-up requests: {', '.join(pending_requests)}, keeping context until responses arrive")
                # Mark that no further follow-up is needed after current requests complete
                follow_up_context['no_further_follow_up'] = True
                return
            else:
                # Clear follow-up context as we're done and no pending requests
                turn_context.pop('follow_up_context', None)
                return

        # AI determined follow-up is needed - always use planning with original thoughts (no re-thinking)
        logger.info(f"JsonCentricRLS: [{room_id}] Follow-up needed, proceeding with planning using original thoughts. Reason: {event.follow_up_reasoning}")

        try:
            # Always go directly to planning with existing thoughts (no thinking phase)
            await self._initiate_follow_up_planning(room_id, config, phase_number + 1)

        except Exception as e:
            logger.error(f"JsonCentricRLS: [{room_id}] Error proceeding with follow-up: {e}")

    async def _initiate_follow_up_thinking(self, room_id: str, config: Dict[str, Any], phase_number: int):
        """DEPRECATED: Initiate follow-up thinking phase based on action results.
        
        This method is no longer used as we now reuse original thoughts for follow-up 
        planning to prevent overthinking.
        """
        logger.warning(f"JsonCentricRLS: [{room_id}] _initiate_follow_up_thinking called but this method is deprecated - should use _initiate_follow_up_planning directly")
        # Redirect to planning with existing thoughts
        await self._initiate_follow_up_planning(room_id, config, phase_number)

    async def _initiate_follow_up_planning(self, room_id: str, config: Dict[str, Any], phase_number: int):
        """Initiate follow-up planning phase with original thoughts (no re-thinking)."""
        turn_context = config['current_turn_context']
        follow_up_context = turn_context['follow_up_context']
        
        planning_request_id = str(uuid.uuid4())
        actions_schema = self.action_registry.generate_planner_schema()
        
        # Use original thoughts from the initial thinking phase
        original_thoughts = turn_context.get('thoughts', [])
        logger.info(f"JsonCentricRLS: [{room_id}] Follow-up planning will reuse {len(original_thoughts)} original thoughts")
        
        planning_request = FollowUpPlanningRequestEvent(
            request_id=planning_request_id,
            updated_thoughts=original_thoughts,  # Actually original thoughts, kept for API compatibility
            original_context=turn_context['context_batch'],
            previous_action_results=follow_up_context['action_results'],
            phase_number=phase_number,
            model_name=self.planner_model,
            actions_schema=actions_schema
        )

        # Update follow-up context
        follow_up_context['follow_up_planning_request_id'] = planning_request_id
        follow_up_context['phase_number'] = phase_number

        await self.bus.publish(planning_request)
        logger.info(f"JsonCentricRLS: [{room_id}] Sent follow-up planning request {planning_request_id} for phase {phase_number}")

    async def _handle_follow_up_thinking_response(self, event: ThinkingResponseEvent):
        """Handle response from follow-up thinking phase."""
        # Find the room that initiated this follow-up thinking
        room_id = None
        config = None
        
        for rid, cfg in self.room_activity_config.items():
            turn_context = cfg.get('current_turn_context', {})
            follow_up_context = turn_context.get('follow_up_context', {})
            if follow_up_context.get('follow_up_thinking_request_id') == event.request_id:
                room_id = rid
                config = cfg
                break

        if not room_id or not config:
            logger.error(f"JsonCentricRLS: Could not find room for follow-up thinking response {event.request_id}")
            return

        if not event.success:
            logger.error(f"JsonCentricRLS: [{room_id}] Follow-up thinking failed: {event.error_message}")
            return

        logger.info(f"JsonCentricRLS: [{room_id}] Received follow-up thinking response, proceeding to planning")

        try:
            turn_context = config['current_turn_context']
            follow_up_context = turn_context['follow_up_context']
            
            # Check if follow-up was already determined to be unnecessary
            if follow_up_context.get('no_further_follow_up'):
                logger.info(f"JsonCentricRLS: [{room_id}] Follow-up thinking completed but no further follow-up needed, clearing context")
                # Clear the follow-up context as we're done
                turn_context.pop('follow_up_context', None)
                return
            
            # Clear the thinking request ID as we've handled it
            follow_up_context.pop('follow_up_thinking_request_id', None)
            
            # DO NOT update thoughts - keep using original thoughts to prevent overthinking
            # turn_context['thoughts'] = event.thoughts  # REMOVED - we reuse original thoughts
            logger.info(f"JsonCentricRLS: [{room_id}] Keeping original thoughts instead of updating with follow-up thinking")
            
            # Proceed to follow-up planning with original thoughts
            await self._initiate_follow_up_planning(room_id, config, follow_up_context['phase_number'])

        except Exception as e:
            logger.error(f"JsonCentricRLS: [{room_id}] Error proceeding to follow-up planning: {e}")

    async def _handle_follow_up_planning_response(self, event: StructuredPlanningResponseEvent):
        """Handle response from follow-up planning phase and execute actions."""
        logger.debug(f"JsonCentricRLS: Processing follow-up planning response {event.request_id}")
        
        # Check if this is a follow-up planning response
        if not event.original_request_payload.get("is_follow_up"):
            logger.warning(f"JsonCentricRLS: _handle_follow_up_planning_response called for non-follow-up response {event.request_id}")
            # Not a follow-up response, let the regular handler deal with it
            return

        # Find the room that initiated this follow-up planning
        room_id = None
        config = None
        
        for rid, cfg in self.room_activity_config.items():
            turn_context = cfg.get('current_turn_context', {})
            follow_up_context = turn_context.get('follow_up_context', {})
            if follow_up_context.get('follow_up_planning_request_id') == event.request_id:
                room_id = rid
                config = cfg
                break

        if not room_id or not config:
            logger.error(f"JsonCentricRLS: Could not find room for follow-up planning response {event.request_id}")
            return

        if not event.success:
            logger.error(f"JsonCentricRLS: [{room_id}] Follow-up planning failed: {event.error_message}")
            return

        logger.info(f"JsonCentricRLS: [{room_id}] Received follow-up action plan, executing actions")

        try:
            turn_context = config['current_turn_context']
            follow_up_context = turn_context['follow_up_context']
            
            # Check if follow-up was already determined to be unnecessary
            if follow_up_context.get('no_further_follow_up'):
                logger.info(f"JsonCentricRLS: [{room_id}] Follow-up planning completed but no further follow-up needed, clearing context")
                # Clear the follow-up context as we're done
                turn_context.pop('follow_up_context', None)
                return
            
            # Clear the planning request ID as we've handled it
            follow_up_context.pop('follow_up_planning_request_id', None)
            
            phase_number = follow_up_context['phase_number']

            # Execute the follow-up action plan
            if event.action_plan and event.action_plan.channel_responses:
                for channel_response in event.action_plan.channel_responses:
                    if channel_response.channel_id == room_id:
                        # Execute the action plan for this channel
                        results = await self.action_executor.execute_action_plan(
                            event.action_plan,
                            request_id=event.request_id
                        )
                        
                        # Extract action results for this channel
                        follow_up_action_results = []
                        for channel_result in results.get("channel_results", []):
                            if channel_result["channel_id"] == room_id:
                                follow_up_action_results = channel_result.get("action_results", [])
                                
                                # Log results
                                for action_result in follow_up_action_results:
                                    if action_result.get("success"):
                                        logger.info(f"JsonCentricRLS: [{room_id}] Follow-up action {action_result['action_name']} succeeded")
                                    else:
                                        logger.error(f"JsonCentricRLS: [{room_id}] Follow-up action {action_result['action_name']} failed: {action_result.get('error', 'Unknown error')}")
                                break

                        # Check if further follow-up is requested
                        follow_up_requested = event.original_request_payload.get("follow_up_requested", False)
                        if follow_up_requested and phase_number < self.max_follow_up_phases:
                            logger.info(f"JsonCentricRLS: [{room_id}] AI requested another follow-up phase")
                            await self._initiate_follow_up_processing(
                                room_id, 
                                follow_up_action_results,
                                event.request_id,
                                phase_number
                            )
                        else:
                            # Follow-up processing complete
                            logger.info(f"JsonCentricRLS: [{room_id}] Follow-up processing complete after phase {phase_number}")
                            turn_context.pop('follow_up_context', None)
                        break

        except Exception as e:
            logger.error(f"JsonCentricRLS: [{room_id}] Error executing follow-up actions: {e}")

    async def _complete_turn_processing(self, room_id: str, config: Dict[str, Any]):
        """Complete the turn processing by updating memory and clearing context."""
        try:
            # Update memory with the turn
            await self._update_memory_after_turn(room_id, config)

            # Clear pending batch and turn context
            config['pending_batch'].clear()
            config.pop('current_turn_context', None)

            # Check if summary is needed
            if config.get('new_turns_since_last_summary', 0) >= self.short_term_memory_items:
                await self._generate_and_store_summary(room_id)

            logger.info(f"JsonCentricRLS: [{room_id}] Turn processing completed")

        except Exception as e:
            logger.error(f"JsonCentricRLS: [{room_id}] Error completing turn processing: {e}")