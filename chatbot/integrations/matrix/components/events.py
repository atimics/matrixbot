"""
Matrix Event Handlers

Handles Matrix events including messages, invites, membership changes, and encryption errors.
Enhanced with improved collapsed channel context generation.
"""

import logging
import time
from typing import Any, Dict, Optional, List

import httpx
from nio import MatrixRoom, RoomMessageImage, RoomMessageText

from ....core.world_state import Message, WorldStateManager
from .rooms import MatrixRoomManager

logger = logging.getLogger(__name__)


class MatrixEventHandler:
    """Handles Matrix events and updates world state with enhanced context awareness."""
    
    def __init__(
        self, 
        world_state: WorldStateManager, 
        room_manager: MatrixRoomManager,
        user_id: str,
        arweave_client=None,
        processing_hub=None,
        channels_to_monitor: list = None
    ):
        self.world_state = world_state
        self.room_manager = room_manager
        self.user_id = user_id
        self.arweave_client = arweave_client
        self.processing_hub = processing_hub
        self.channels_to_monitor = channels_to_monitor or []
        
        # Message batching for high-traffic channels
        self.message_batches = {}  # room_id -> list of recent messages
        self.batch_timers = {}     # room_id -> timestamp of last batch
        self.batch_timeout = 5.0   # seconds to wait before processing batch
        
        # Context enhancement for collapsed channels
        self.recent_activity = {}  # room_id -> activity summary
        self.activity_keywords = {} # room_id -> important keywords
    
    async def handle_message(self, room: MatrixRoom, event, client=None):
        """Handle incoming Matrix messages with enhanced batching and context tracking."""
        # Skip our own messages
        logger.info(f"MatrixEventHandler: Comparing event.sender='{event.sender}' with user_id='{self.user_id}'")
        if event.sender == self.user_id:
            logger.info(f"MatrixEventHandler: Skipping own message from {event.sender}")
            return

        # Extract comprehensive room details
        room_details = self.room_manager.extract_room_details(room)

        # Auto-register room if not known
        existing_channel = self.world_state.get_channel(room.room_id, "matrix")
        if not existing_channel:
            logger.info(f"MatrixEventHandler: Auto-registering room {room.room_id}")
            self.room_manager.register_room(room.room_id, room_details, room)
        else:
            # Update existing room details
            self.room_manager.update_room_details(room.room_id, room_details)

        logger.debug(
            f"MatrixEventHandler: Processing message from {room.room_id} ({room.display_name})"
        )

        # Process message content
        content, image_urls_list = await self._process_message_content(event, client)
        
        # Create message object
        metadata = {
            "matrix_event_type": getattr(event, "msgtype", type(event).__name__)
        }
        
        # Add original filename to metadata for image messages if available
        if isinstance(event, RoomMessageImage) and hasattr(event, 'body') and event.body:
            metadata["original_filename"] = event.body
        
        message = Message(
            id=event.event_id,
            channel_id=room.room_id,
            channel_type="matrix",
            sender=event.sender,
            content=content,
            timestamp=time.time(),
            reply_to=None,  # TODO: Extract reply information if present
            image_urls=image_urls_list if image_urls_list else None,
            metadata=metadata,
        )

        # Check for message batching (rapid consecutive messages from same user)
        should_batch = await self._handle_message_batching(room, message)
        
        if not should_batch:
            # Add to world state immediately
            self.world_state.add_message(room.room_id, message)
            
            # Update activity tracking for collapsed channel summaries
            await self._update_activity_tracking(room, message)

            log_content = content[:100] + "..." if len(content) > 100 else content
            if image_urls_list:
                log_content += f" [Image: {image_urls_list[0]}]"

            logger.info(
                f"MatrixEventHandler: New message in {room.display_name or room.room_id}: "
                f"{event.sender}: {log_content}"
            )

            # Generate triggers for processing hub if connected
            await self._generate_triggers(room, event, message)
    
    async def _handle_message_batching(self, room: MatrixRoom, message: Message) -> bool:
        """Handle message batching for rapid-fire messages from same user."""
        room_id = room.room_id
        current_time = time.time()
        
        # Initialize batching structures if needed
        if room_id not in self.message_batches:
            self.message_batches[room_id] = []
            self.batch_timers[room_id] = current_time
        
        # Check if this message should be batched
        recent_messages = self.message_batches[room_id]
        if recent_messages:
            last_message = recent_messages[-1]
            time_diff = current_time - last_message.timestamp
            
            # Batch if: same sender, within timeout, and recent activity
            if (last_message.sender == message.sender and 
                time_diff < self.batch_timeout and 
                len(recent_messages) < 5):  # Max batch size
                
                logger.debug(f"MatrixEventHandler: Batching message from {message.sender} in {room_id}")
                recent_messages.append(message)
                return True  # Message was batched
        
        # Process any existing batch if timeout exceeded
        if recent_messages and current_time - self.batch_timers[room_id] > self.batch_timeout:
            await self._process_message_batch(room, recent_messages)
            self.message_batches[room_id] = []
        
        # Add current message to new batch
        self.message_batches[room_id] = [message]
        self.batch_timers[room_id] = current_time
        
        return False  # Message not batched, process normally
    
    async def _process_message_batch(self, room: MatrixRoom, messages: List[Message]) -> None:
        """Process a batch of messages as a single coherent unit."""
        if not messages:
            return
            
        # Combine messages into a single coherent message
        combined_content = []
        combined_images = []
        
        for msg in messages:
            combined_content.append(msg.content)
            if msg.image_urls:
                combined_images.extend(msg.image_urls)
        
        # Create a single combined message
        combined_message = Message(
            id=f"batch_{messages[0].id}_{messages[-1].id}",
            channel_id=room.room_id,
            channel_type="matrix",
            sender=messages[0].sender,
            content=" ".join(combined_content),
            timestamp=messages[-1].timestamp,  # Use timestamp of last message
            reply_to=None,
            image_urls=combined_images if combined_images else None,
            metadata={
                "matrix_event_type": "batched_messages",
                "batch_size": len(messages),
                "original_message_ids": [msg.id for msg in messages]
            }
        )
        
        # Add combined message to world state
        self.world_state.add_message(room.room_id, combined_message)
        
        # Update activity tracking
        await self._update_activity_tracking(room, combined_message)
        
        logger.info(
            f"MatrixEventHandler: Processed message batch of {len(messages)} messages "
            f"from {messages[0].sender} in {room.display_name or room.room_id}"
        )
        
        # Generate trigger for the batch
        if self.processing_hub:
            from ....core.orchestration.processing_hub import Trigger
            
            # Check for bot mention in any of the batched messages
            bot_mentioned = any(self.user_id.lower() in msg.content.lower() for msg in messages)
            
            if bot_mentioned:
                trigger = Trigger(
                    trigger_type="mention",
                    channel_id=room.room_id,
                    channel_type="matrix",
                    triggering_message_id=combined_message.id,
                    priority=1,
                    metadata={"mentioned_user": self.user_id, "batch_size": len(messages)}
                )
            else:
                trigger = Trigger(
                    trigger_type="new_message",
                    channel_id=room.room_id,
                    channel_type="matrix",
                    triggering_message_id=combined_message.id,
                    priority=3,
                    metadata={"batch_size": len(messages)}
                )
            
            await self.processing_hub.add_trigger(trigger)
    
    async def _update_activity_tracking(self, room: MatrixRoom, message: Message) -> None:
        """Update activity tracking for enhanced collapsed channel summaries."""
        room_id = room.room_id
        current_time = time.time()
        
        # Initialize activity tracking if needed
        if room_id not in self.recent_activity:
            self.recent_activity[room_id] = {
                "last_activity": current_time,
                "recent_senders": set(),
                "recent_keywords": set(),
                "message_count_1h": 0,
                "message_count_24h": 0,
                "last_summary_update": current_time
            }
        
        activity = self.recent_activity[room_id]
        
        # Update basic activity metrics
        activity["last_activity"] = current_time
        activity["recent_senders"].add(message.sender)
        
        # Extract keywords from message content
        keywords = self._extract_keywords(message.content)
        activity["recent_keywords"].update(keywords)
        
        # Update message counts (simplified - would need proper time-based counting)
        activity["message_count_1h"] += 1
        activity["message_count_24h"] += 1
        
        # Limit keyword set size
        if len(activity["recent_keywords"]) > 20:
            # Keep only the most recent keywords
            activity["recent_keywords"] = set(list(activity["recent_keywords"])[-20:])
        
        # Limit sender set size
        if len(activity["recent_senders"]) > 10:
            # Keep only the most recent senders
            activity["recent_senders"] = set(list(activity["recent_senders"])[-10:])
        
        # Update the channel's activity_metrics in the world state
        channel = self.world_state.get_channel(room_id, "matrix")
        if channel:
            channel.activity_metrics = {
                "last_activity": activity["last_activity"],
                "recent_senders": list(activity["recent_senders"]),
                "recent_keywords": list(activity["recent_keywords"]),
                "message_count_1h": activity["message_count_1h"],
                "message_count_24h": activity["message_count_24h"],
                "last_update": current_time
            }
            logger.debug(f"MatrixEventHandler: Updated channel activity metrics for {room_id}")
        
        logger.debug(f"MatrixEventHandler: Updated activity tracking for {room_id}")
    
    def _extract_keywords(self, content: str) -> set:
        """Extract important keywords from message content."""
        if not content:
            return set()
        
        # Simple keyword extraction (could be enhanced with NLP)
        words = content.lower().split()
        
        # Filter out common words and extract meaningful terms
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
            'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 
            'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should',
            'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them'
        }
        
        keywords = set()
        for word in words:
            # Clean word and check criteria
            clean_word = ''.join(c for c in word if c.isalnum())
            if (len(clean_word) > 3 and 
                clean_word.lower() not in stop_words and
                not clean_word.isdigit()):
                keywords.add(clean_word.lower())
        
        return keywords
    
    def get_enhanced_channel_summary(self, room_id: str) -> Dict[str, Any]:
        """Get enhanced summary for collapsed channel display."""
        activity = self.recent_activity.get(room_id, {})
        
        if not activity:
            return {
                "summary": "No recent activity",
                "message_count": 0,
                "active_users": 0,
                "keywords": [],
                "last_activity": None
            }
        
        # Generate meaningful summary
        message_count = activity.get("message_count_1h", 0)
        active_users = len(activity.get("recent_senders", set()))
        keywords = list(activity.get("recent_keywords", set()))[:5]  # Top 5 keywords
        last_activity = activity.get("last_activity")
        
        # Create human-readable summary
        if message_count == 0:
            summary = "No recent messages"
        elif message_count == 1:
            summary = f"1 message from {active_users} user"
        else:
            summary = f"{message_count} messages from {active_users} users"
        
        if keywords:
            summary += f" discussing: {', '.join(keywords[:3])}"
        
        return {
            "summary": summary,
            "message_count": message_count,
            "active_users": active_users,
            "keywords": keywords,
            "last_activity": last_activity,
            "time_since_activity": time.time() - last_activity if last_activity else None
        }

    async def handle_invite(self, room, event):
        """Handle room invitations."""
        try:
            room_id = room.room_id
            inviter = event.sender
            
            logger.info(f"MatrixEventHandler: Received invite to {room_id} from {inviter}")
            
            # Register the invite in world state as a pending invite
            if hasattr(self.world_state, 'add_pending_matrix_invite'):
                invite_details = {
                    "room_id": room_id,
                    "inviter": inviter,
                    "room_name": getattr(room, 'name', None) or getattr(room, 'display_name', 'Unknown Room'),
                    "invited_at": time.time(),
                    "room_topic": getattr(room, 'topic', None),
                    "member_count": getattr(room, 'member_count', 0),
                }
                self.world_state.add_pending_matrix_invite(room_id, invite_details)
                
            logger.info(f"MatrixEventHandler: Added pending invite for room {room_id}")
            
        except Exception as e:
            logger.error(f"MatrixEventHandler: Error processing invite: {e}", exc_info=True)
    
    async def handle_membership_change(self, room, event):
        """Handle membership change events (join, leave, kick, ban)."""
        try:
            sender = event.sender
            membership = event.membership
            target = getattr(event, 'state_key', sender)  # Who the membership change affects
            room_id = room.room_id
            
            logger.info(
                f"MatrixEventHandler: Membership change in {room_id}: "
                f"{sender} -> {target} ({membership})"
            )
            
            # Handle bot's own membership changes
            if target == self.user_id:
                if membership == "leave":
                    # Bot left or was removed from room
                    reason = event.content.get("reason", "")
                    
                    # Check if it was voluntary (bot left) or involuntary (kicked/banned)
                    if sender == self.user_id:
                        status = "left"
                        logger.info(f"MatrixEventHandler: Bot left room {room_id}")
                    else:
                        # Check if it was a ban by looking at the event content
                        reason = event.content.get("reason", "")
                        if (
                            "ban" in reason.lower()
                            or event.content.get("membership") == "ban"
                        ):
                            status = "banned"
                            logger.warning(
                                f"MatrixEventHandler: Bot was banned from room {room_id} by {sender}. Reason: {reason}"
                            )
                        else:
                            status = "kicked"
                            logger.warning(
                                f"MatrixEventHandler: Bot was kicked from room {room_id} by {sender}. Reason: {reason}"
                            )

                    # Update world state
                    if hasattr(self.world_state, "update_channel_status"):
                        self.world_state.update_channel_status(room_id, status)

                    # Remove from monitoring if kicked/banned (but not if we left voluntarily)
                    if (
                        status in ["kicked", "banned"]
                        and room_id in self.channels_to_monitor
                    ):
                        self.channels_to_monitor.remove(room_id)
                        logger.info(
                            f"MatrixEventHandler: Removed {room_id} from monitoring due to {status}"
                        )

                elif membership == "join":
                    # Bot joined a room (usually handled by join/accept methods, but this catches edge cases)
                    logger.info(f"MatrixEventHandler: Bot joined room {room_id}")

                    # Ensure the channel is registered in the world state
                    existing_channel = self.world_state.get_channel(room_id, "matrix")
                    if not existing_channel:
                        room_details = self.room_manager.extract_room_details(room)
                        self.room_manager.register_room(room_id, room_details)

                    # Ensure room is in monitoring if not already
                    if room_id not in self.channels_to_monitor:
                        self.channels_to_monitor.append(room_id)

                    # Remove any pending invite for this room
                    if hasattr(self.world_state, "remove_pending_matrix_invite"):
                        self.world_state.remove_pending_matrix_invite(room_id)
                    if hasattr(self.world_state, "update_channel_status"):
                        self.world_state.update_channel_status(room_id, "joined")

                elif membership == "ban":
                    # Explicit ban event
                    status = "banned"
                    reason = event.content.get("reason", "")
                    logger.warning(
                        f"MatrixEventHandler: Bot was banned from room {room_id} by {sender}. Reason: {reason}"
                    )

                    # Update world state and remove from monitoring
                    if hasattr(self.world_state, "update_channel_status"):
                        self.world_state.update_channel_status(room_id, status)

                    if room_id in self.channels_to_monitor:
                        self.channels_to_monitor.remove(room_id)

        except Exception as e:
            logger.error(
                f"MatrixEventHandler: Error processing membership change: {e}",
                exc_info=True,
            )
    
    async def handle_encryption_error(self, room: MatrixRoom, event):
        """Handle Megolm decryption errors and other encryption issues."""
        try:
            room_id = room.room_id
            event_id = getattr(event, 'event_id', 'unknown')
            sender = getattr(event, 'sender', 'unknown')
            
            logger.warning(
                f"MatrixEventHandler: Encryption error in {room_id} "
                f"(event {event_id} from {sender}): Undecryptable Megolm event"
            )
            
            # Create a placeholder message indicating encryption failure
            error_message = Message(
                id=event_id,
                channel_id=room_id,
                channel_type="matrix",
                sender=sender,
                content="[Encrypted message - decryption failed]",
                timestamp=time.time(),
                reply_to=None,
                image_urls=None,
                metadata={
                    "matrix_event_type": "m.room.encrypted",
                    "encryption_error": True,
                    "error_type": "megolm_decryption_failed"
                },
            )
            
            # Add the error message to world state so AI is aware of missing content
            self.world_state.add_message(room_id, error_message)
            
            # TODO: Implement key recovery strategies:
            # 1. Request keys from other devices
            # 2. Check if keys become available later
            # 3. Mark room for key refresh
            
            logger.info(
                f"MatrixEventHandler: Added placeholder for undecryptable message in {room.display_name or room_id}"
            )
            
        except Exception as e:
            logger.error(f"MatrixEventHandler: Error handling encryption error: {e}", exc_info=True)
