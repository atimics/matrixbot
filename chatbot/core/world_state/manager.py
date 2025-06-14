#!/usr/bin/env python3
"""
World State Manager

This module provides the primary interface for managing WorldStateData. It handles
all CRUD operations on the world state, including adding messages, managing channels,
tracking actions, and maintaining system status.

Responsibilities:
- Add/update messages and channels
- Track action results and history  
- Manage Matrix invites and channel status
- Record bot media and generated content
- Provide access to world state metrics

Note: This module focuses on data management only. AI payload generation has been
moved to PayloadBuilder for better separation of concerns.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from .structures import (
    WorldStateData, 
    Message, 
    Channel, 
    ActionHistory,
    SentimentData,
    MemoryEntry,
    FarcasterUserDetails,
    MatrixUserDetails
)

logger = logging.getLogger(__name__)


class WorldStateManager:
    """
    Manages the world state and provides updates.
    
    This class provides a high-level interface for interacting with WorldStateData,
    handling all the common operations needed by the orchestration system.
    """

    def __init__(self):
        self.state = WorldStateData()
        
        # Initialize system status
        self.state.system_status = {
            "matrix_connected": False,
            "farcaster_connected": False,
            "last_observation_cycle": 0,
            "total_cycles": 0,
        }
        logger.info("WorldStateManager: Initialized empty world state")

    @property
    def world_state(self):
        """Compatibility property for tests expecting 'world_state' instead of 'state'."""
        return self.state

    def add_channel(
        self, channel_or_id, channel_type: Optional[str] = None, name: Optional[str] = None, status: str = "active"
    ):
        """Add a new channel to monitor
        
        Args:
            channel_or_id: Either a Channel object or a channel_id string
            channel_type: Channel type (required if channel_or_id is string)
            name: Channel name (required if channel_or_id is string)
            status: Channel status (default: "active")
        """
        if isinstance(channel_or_id, Channel):
            # Adding a Channel object directly
            channel = channel_or_id
            # Initialize platform dict if it doesn't exist
            if channel.type not in self.state.channels:
                self.state.channels[channel.type] = {}
            self.state.channels[channel.type][channel.id] = channel
            logger.info(
                f"WorldState: Added {channel.type} channel '{channel.name}' ({channel.id}) with status '{channel.status}'"
            )
        else:
            # Adding by parameters
            channel_id = channel_or_id
            if channel_type is None or name is None:
                raise ValueError("channel_type and name are required when adding by parameters")
            
            # Initialize platform dict if it doesn't exist
            if channel_type not in self.state.channels:
                self.state.channels[channel_type] = {}
                
            channel = Channel(
                id=channel_id,
                name=name,
                type=channel_type,
                status=status,
                last_status_update=time.time(),
            )
            # Set last_checked after creation
            channel.update_last_checked()
            self.state.channels[channel_type][channel_id] = channel
            logger.info(
                f"WorldState: Added {channel_type} channel '{name}' ({channel_id}) with status '{status}'"
            )

    def add_message(self, *args, **kwargs):
        """Add a new message to a channel. Accepts (channel_id, message), (message_data, message), or (dict) for test compatibility."""
        from .structures import Message
        # Accept (channel_id, message), (message_data, message), or (dict with keys 'channel_id' and 'message'
        if len(args) == 2:
            channel_id, message = args
            if isinstance(channel_id, dict):
                channel_id = channel_id.get("channel_id") or channel_id.get("id")
        elif len(args) == 1 and isinstance(args[0], dict):
            d = args[0]
            channel_id = d.get("channel_id") or d.get("id")
            message = d.get("message") or d.get("msg")
            if message is None and "message" in kwargs:
                message = kwargs["message"]
            if message is None and "msg" in kwargs:
                message = kwargs["msg"]
            # If the dict itself is a message dict, treat it as the message
            if message is None and all(k in d for k in ("id", "sender", "content", "timestamp", "channel_type")):
                message = d
        else:
            raise TypeError("add_message expects (channel_id, message), (message_data, message), or (dict with channel_id and message)")

        # Validate message exists
        if message is None:
            logger.error("WorldStateManager: Cannot add message - message is None")
            return

        # Convert dict to Message if needed
        if isinstance(message, dict):
            message = Message(**message)
        # Deduplicate across channels
        if message.id in self.state.seen_messages:
            logger.debug(f"WorldStateManager: Deduplicated message {message.id}")
            return
        self.state.seen_messages.add(message.id)
        # Handle None channel_id gracefully
        if not channel_id:
            channel_id = message.channel_id or f"{message.channel_type}:unknown"
            logger.warning(f"None channel_id provided, using fallback: {channel_id}")
        
        # Check if channel exists using the new nested structure
        channel = self.get_channel(channel_id, message.channel_type)
        if channel is None:
            # Auto-create channel if it doesn't exist
            self.add_channel(channel_id, channel_type=message.channel_type, name=channel_id)
            channel = self.get_channel(channel_id, message.channel_type)
        
        if channel is None:
            logger.error(f"Failed to create or retrieve channel {channel_id}")
            return
            
        channel.recent_messages.append(message)
        # Limit to 50 messages per channel
        if len(channel.recent_messages) > 50:
            channel.recent_messages = channel.recent_messages[-50:]
        channel.update_last_checked()
        
        # Thread management: group Farcaster messages by root cast
        if message.channel_type == "farcaster":
            thread_id = message.reply_to or message.id
            self.state.threads.setdefault(thread_id, []).append(message)
            logger.info(f"WorldStateManager: Added message to thread '{thread_id}'")

        # Log the message addition
        logger.info(
            f"WorldState: New message in {channel.name}: {message.sender}: {message.content[:100]}..."
        )

    def add_message_compat(self, channel_id_or_dict, message=None):
        """Compatibility wrapper for tests that call add_message with (dict, message) or (message_data, message)."""
        # If called with (message_data, message), extract channel_id
        if isinstance(channel_id_or_dict, dict) and message is not None:
            channel_id = channel_id_or_dict.get("channel_id") or channel_id_or_dict.get("id")
            return self.add_message(channel_id, message)
        # If called with (channel_id, message)
        return self.add_message(channel_id_or_dict, message)
    
    def add_messages(self, messages: List[Message]) -> None:
        """Batch add multiple messages to the world state."""
        for msg in messages:
            # Use each message's channel_id when adding
            try:
                self.add_message(msg.channel_id, msg)
            except Exception as e:
                logger.error(f"WorldStateManager: Failed to add message {getattr(msg, 'id', None)}: {e}")

    def add_action_result(
        self,
        action_type: str,
        parameters: Dict[str, Any],
        result: str,
        action_id: Optional[str] = None,
    ) -> str:
        """Record the result of an executed action. Returns the action_id for tracking."""
        if not action_id:
            # Generate a unique ID for new actions
            action_id = f"{action_type}_{int(time.time() * 1000)}_{id(parameters)}"

        action = ActionHistory(
            action_type=action_type,
            parameters=parameters,
            result=result,
            timestamp=time.time(),
            action_id=action_id,
        )

        self.state.action_history.append(action)

        # Keep only last 100 actions
        if len(self.state.action_history) > 100:
            self.state.action_history = self.state.action_history[-100:]

        self.state.last_update = time.time()

        logger.info(
            f"WorldState: Action completed - {action_type}: {result} (ID: {action_id})"
        )
        return action_id

    def update_action_result(
        self, action_id: str, new_result: str, cast_hash: Optional[str] = None
    ) -> bool:
        """Update the result of an existing action by ID. Returns True if found and updated."""
        for action in self.state.action_history:
            if action.action_id == action_id:
                old_result = action.result
                action.result = new_result
                action.timestamp = (
                    time.time()
                )  # Update timestamp to reflect completion time

                # If this is a Farcaster action and we have a cast hash, add it to parameters
                if cast_hash and action.action_type.startswith("send_farcaster"):
                    action.parameters["cast_hash"] = cast_hash

                self.state.last_update = time.time()
                logger.info(
                    f"WorldState: Action {action_id} updated - {action.action_type}: {old_result} -> {new_result}"
                )
                return True

        logger.warning(
            f"WorldState: Could not find action with ID {action_id} to update"
        )
        return False

    def update_system_status(self, updates: Dict[str, Any]):
        """Update system status information"""
        self.state.system_status.update(updates)
        self.state.last_update = time.time()

        for key, value in updates.items():
            logger.info(f"WorldState: System status update - {key}: {value}")

    def get_observation_data(self, channels_or_lookback=None, lookback_seconds: int = 300) -> Dict[str, Any]:
        """Get current world state data for AI observation
        
        Args:
            channels_or_lookback: Either a list of channel IDs to filter, or lookback_seconds for backward compatibility
            lookback_seconds: Time window for recent activity (default 300 seconds)
        """
        # Handle backward compatibility: if first arg is int, treat as lookback_seconds
        if isinstance(channels_or_lookback, int):
            lookback_seconds = channels_or_lookback
            channels_filter = None
        elif isinstance(channels_or_lookback, list):
            channels_filter = channels_or_lookback
        else:
            channels_filter = None
            
        observation = self.state.get_recent_activity(lookback_seconds)
        
        # Filter channels if specified
        if channels_filter and "channels" in observation:
            filtered_channels = {}
            for platform, platform_channels in observation["channels"].items():
                filtered_platform_channels = {
                    ch_id: ch_data for ch_id, ch_data in platform_channels.items()
                    if ch_id in channels_filter
                }
                if filtered_platform_channels:
                    filtered_channels[platform] = filtered_platform_channels
            observation["channels"] = filtered_channels
        
        # Include thread context for AI to follow conversation threads
        observation["threads"] = {
            thread_id: [msg.__dict__ for msg in msgs]
            for thread_id, msgs in self.state.threads.items()
        }

        # Increment observation cycle counter
        self.state.system_status["total_cycles"] += 1
        self.state.system_status["last_observation_cycle"] = time.time()

        logger.info(
            f"WorldState: Generated observation #{self.state.system_status['total_cycles']} "
            f"with {len(observation['recent_messages'])} recent messages and "
            f"{len(observation['recent_actions'])} recent actions"
        )

        return observation

    def to_json(self) -> str:
        """Convert world state to JSON for serialization"""
        return self.state.to_json()

    def to_dict(self) -> Dict[str, Any]:
        """Convert world state to dictionary for AI processing"""
        return self.state.to_dict()

    async def get_state(self) -> WorldStateData:
        """Get the current world state (async version for compatibility)"""
        return self.state

    def get_state_data(self) -> WorldStateData:
        """Get the raw WorldStateData object"""
        return self.state

    def get_state_metrics(self) -> Dict[str, Any]:
        """Get metrics about the current world state for monitoring"""
        return self.state.get_state_metrics()

    def get_all_messages(self) -> List[Message]:
        """Get all messages from all channels"""
        return self.state.get_all_messages()

    def add_action_history(self, action_data: Dict[str, Any]):
        """Add a new action to the history"""
        action = ActionHistory(
            action_type=action_data.get("action_type", "unknown"),
            parameters=action_data.get("parameters", {}),
            result=action_data.get("result", ""),
            timestamp=time.time(),
        )

        self.state.action_history.append(action)

        # Limit action history size
        if len(self.state.action_history) > 100:
            self.state.action_history = self.state.action_history[-100:]

    def has_replied_to_cast(self, cast_hash: str) -> bool:
        """
        Check if the AI has already replied to a specific cast.
        This now checks for successful or scheduled actions.
        """
        for action in self.state.action_history:
            if action.action_type == "send_farcaster_reply":
                reply_to_hash = action.parameters.get("reply_to_hash")
                if reply_to_hash == cast_hash:
                    # Consider it replied if the action was successful OR is still scheduled.
                    # This prevents re-queueing a reply while one is already pending.
                    if action.result != "failure":
                        return True
        return False

    def has_quoted_cast(self, cast_hash: str) -> bool:
        """
        Check if the AI has already quoted a specific cast.

        Args:
            cast_hash: The hash of the cast to check

        Returns:
            True if the AI has already quoted this cast
        """
        for action in self.state.action_history:
            if action.action_type == "quote_farcaster_post":
                quoted_cast_hash = action.parameters.get("quoted_cast_hash")
                if quoted_cast_hash == cast_hash:
                    return True
        return False

    def has_liked_cast(self, cast_hash: str) -> bool:
        """
        Check if the AI has already liked a specific cast.

        Args:
            cast_hash: The hash of the cast to check

        Returns:
            True if the AI has already liked this cast
        """
        for action in self.state.action_history:
            if action.action_type == "like_farcaster_post":
                liked_cast_hash = action.parameters.get("cast_hash")
                if liked_cast_hash == cast_hash:
                    return True
        return False

    def has_sent_farcaster_post(self, content: str) -> bool:
        """
        Check if the AI has already sent a Farcaster post with identical content.
        """
        for action in self.state.action_history:
            if action.action_type == "send_farcaster_post":
                sent_content = action.parameters.get("content")
                if sent_content == content:
                    return True
        return False

    def get_last_farcaster_post(self) -> Optional[Dict[str, Any]]:
        """
        Get the bot's most recent successful Farcaster post for activity context.
        
        Returns:
            Dictionary with content, timestamp, and other details of last post, or None
        """
        for action in reversed(self.state.action_history):
            if action.action_type == "send_farcaster_post" and "success" in action.result:
                return {
                    "content": action.parameters.get("content", ""),
                    "channel": action.parameters.get("channel"),
                    "timestamp": action.timestamp,
                    "cast_hash": action.parameters.get("cast_hash"),
                    "embed_url": action.parameters.get("embed_url")
                }
        return None

    def get_last_matrix_message(self) -> Optional[Dict[str, Any]]:
        """
        Get the bot's most recent Matrix message for activity context.
        
        Returns:
            Dictionary with content, timestamp, and channel details of last message, or None
        """
        for action in reversed(self.state.action_history):
            if action.action_type == "send_matrix_message" and "success" in action.result:
                return {
                    "content": action.parameters.get("content", ""),
                    "room_id": action.parameters.get("room_id"),
                    "timestamp": action.timestamp,
                    "event_id": action.parameters.get("event_id")
                }
        return None

    def get_channel(self, channel_id: str, channel_type: Optional[str] = None) -> Optional[Channel]:
        """Get a channel by ID and optional type.
        
        Args:
            channel_id: The channel ID to look up
            channel_type: Optional platform type to narrow search
            
        Returns:
            Channel object if found, None otherwise
        """
        # If channel_type is provided, look in specific platform
        if channel_type and channel_type in self.state.channels:
            return self.state.channels[channel_type].get(channel_id)
        
        # Search all platforms for the channel_id
        for platform_channels in self.state.channels.values():
            if channel_id in platform_channels:
                return platform_channels[channel_id]
        
        return None

    def add_pending_matrix_invite(self, invite_info: Dict[str, Any]) -> None:
        """
        Add a pending Matrix room invite to the world state.

        Args:
            invite_info: Dictionary with 'room_id', 'inviter', and optionally 'room_name', 'timestamp'
        """
        room_id = invite_info.get("room_id")
        if not room_id:
            logger.warning("Cannot add Matrix invite without room_id")
            return

        # Check for duplicates and update if existing
        for existing_invite in self.state.pending_matrix_invites:
            if existing_invite.get("room_id") == room_id:
                # Update existing invite with new information
                existing_invite.update(invite_info)
                logger.info(
                    f"WorldState: Updated existing pending invite for room {room_id} from {invite_info.get('inviter')}"
                )
                self.state.last_update = time.time()
                return

        # Add timestamp if not provided
        if "timestamp" not in invite_info:
            invite_info["timestamp"] = time.time()

        self.state.pending_matrix_invites.append(invite_info)
        self.state.last_update = time.time()
        logger.info(
            f"WorldState: Added new pending Matrix invite for room {room_id} from {invite_info.get('inviter')}"
        )

    def remove_pending_matrix_invite(self, room_id: str) -> bool:
        """
        Remove a pending Matrix invite from the world state.

        Args:
            room_id: The room ID to remove from pending invites

        Returns:
            True if invite was found and removed, False otherwise
        """
        original_count = len(self.state.pending_matrix_invites)
        self.state.pending_matrix_invites = [
            invite
            for invite in self.state.pending_matrix_invites
            if invite.get("room_id") != room_id
        ]

        removed = len(self.state.pending_matrix_invites) < original_count
        if removed:
            self.state.last_update = time.time()
            logger.info(f"WorldState: Removed pending Matrix invite for room {room_id}")
        else:
            logger.debug(f"No pending Matrix invite found for room {room_id}")
        return removed

    def update_channel_status(
        self, channel_id: str, new_status: str, room_name: Optional[str] = None
    ):
        """
        Update the status of a channel (e.g., 'left_by_bot', 'kicked', 'banned', 'active').

        Args:
            channel_id: The channel ID to update
            new_status: New status for the channel
            room_name: Optional room name for creating unknown channels
        """
        # Find channel in nested structure (assuming Matrix for backward compatibility)
        channel = self.get_channel(channel_id, "matrix")
        if channel:
            old_status = channel.status
            channel.status = new_status
            channel.last_status_update = time.time()
            self.state.last_update = time.time()
            logger.info(
                f"WorldState: Updated channel {channel_id} ({channel.name}) status from '{old_status}' to '{new_status}'"
            )
        elif room_name:
            # If channel not known, add it with the new status (e.g. for kicks from unknown rooms)
            self.add_channel(channel_id, "matrix", room_name, status=new_status)
        else:
            logger.warning(
                f"Cannot update status for unknown channel {channel_id} without providing a room name."
            )

    def get_pending_matrix_invites(self) -> List[Dict[str, Any]]:
        """
        Get all pending Matrix invites.

        Returns:
            List of invite dictionaries
        """
        return self.state.pending_matrix_invites.copy()

    # v0.0.3: Bot Media Tracking Methods for Permaweb Archival

    def record_bot_media_post(
        self, cast_hash: str, arweave_url: str, media_type: str, channel_id: str
    ):
        """
        Record that the bot posted media to Farcaster for engagement tracking.

        Args:
            cast_hash: Farcaster cast hash
            arweave_url: Arweave URL of the media
            media_type: 'image' or 'video'
            channel_id: Farcaster channel where posted
        """
        self.state.bot_media_on_farcaster[cast_hash] = {
            "arweave_url": arweave_url,
            "media_type": media_type,
            "likes": 0,
            "arweave_tx_id": None,
            "posted_timestamp": time.time(),
            "channel_id": channel_id,
        }
        logger.info(f"WorldState: Recorded bot media post {cast_hash} ({media_type})")

    def update_bot_media_likes(self, cast_hash: str, current_likes: int):
        """
        Update the like count for bot media on Farcaster.

        Args:
            cast_hash: Farcaster cast hash
            current_likes: Current number of likes
        """
        if cast_hash in self.state.bot_media_on_farcaster:
            old_likes = self.state.bot_media_on_farcaster[cast_hash]["likes"]
            self.state.bot_media_on_farcaster[cast_hash]["likes"] = current_likes
            if current_likes > old_likes:
                logger.debug(
                    f"WorldState: Updated likes for {cast_hash}: {old_likes} -> {current_likes}"
                )

    def get_top_bot_media_for_archival(
        self, media_type: str, like_threshold: int
    ) -> Optional[tuple]:
        """
        Find the top liked bot media of a specific type that hasn't been archived yet.

        Args:
            media_type: 'image' or 'video'
            like_threshold: Minimum likes required for archival

        Returns:
            Tuple of (cast_hash, media_info_dict) or None
        """
        candidates = []
        for cast_hash, media_info in self.state.bot_media_on_farcaster.items():
            if (
                media_info["media_type"] == media_type
                and media_info["likes"] >= like_threshold
                and media_info["arweave_tx_id"] is None
            ):
                candidates.append((cast_hash, media_info))

        if candidates:
            # Return the one with the most likes
            return max(candidates, key=lambda x: x[1]["likes"])
        return None

    def mark_bot_media_archived(self, cast_hash: str, arweave_tx_id: str):
        """
        Mark bot media as archived to Arweave.

        Args:
            cast_hash: Farcaster cast hash
            arweave_tx_id: Arweave transaction ID
        """
        if cast_hash in self.state.bot_media_on_farcaster:
            self.state.bot_media_on_farcaster[cast_hash][
                "arweave_tx_id"
            ] = arweave_tx_id
            logger.info(
                f"WorldState: Marked {cast_hash} as archived to Arweave: {arweave_tx_id}"
            )

    def record_generated_media(
        self, 
        media_url: str, 
        media_type: str, 
        prompt: str,
        service_used: str,
        aspect_ratio: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Record AI-generated media in the image library for future reference.

        Args:
            media_url: Arweave URL or other URL of the generated media
            media_type: 'image' or 'video'
            prompt: The text prompt used to generate the media
            service_used: The AI service used (e.g., 'google_gemini', 'replicate')
            aspect_ratio: Aspect ratio of the media (e.g., '1:1', '16:9')
            metadata: Additional metadata about the generation
        """
        media_entry = {
            "url": media_url,
            "type": media_type,
            "prompt": prompt,
            "service_used": service_used,
            "timestamp": time.time(),
            "aspect_ratio": aspect_ratio,
            "metadata": metadata or {}
        }
        
        self.state.generated_media_library.append(media_entry)
        self.state.last_update = time.time()
        
        logger.info(
            f"WorldState: Added {media_type} to generated media library: {prompt[:50]}..."
        )

    def get_last_generated_media_url(self) -> Optional[str]:
        """
        Returns the URL of the most recently generated image or video, or None if none exist.
        """
        if self.state.generated_media_library:
            last = self.state.generated_media_library[-1]
            return last.get("url")
        return None

    def get_world_state_data(self) -> WorldStateData:
        """
        Get direct access to the underlying WorldStateData object.
        
        Returns:
            The WorldStateData instance managed by this manager
        """
        return self.state

    # === Enhanced User Management ===
    
    def get_or_create_farcaster_user(self, fid: str) -> FarcasterUserDetails:
        """Get or create a FarcasterUserDetails object for the given FID."""
        fid_str = str(fid)
        if fid_str not in self.state.farcaster_users:
            self.state.farcaster_users[fid_str] = FarcasterUserDetails(fid=fid_str)
            self.state.last_update = time.time()
        return self.state.farcaster_users[fid_str]
    
    def get_or_create_matrix_user(self, user_id: str) -> MatrixUserDetails:
        """Get or create a MatrixUserDetails object for the given user ID."""
        if user_id not in self.state.matrix_users:
            self.state.matrix_users[user_id] = MatrixUserDetails(user_id=user_id)
            self.state.last_update = time.time()
        return self.state.matrix_users[user_id]
    
    def update_user_sentiment(self, platform: str, user_identifier: str, sentiment_data: SentimentData):
        """Update sentiment data for a user."""
        try:
            if platform == "farcaster":
                user = self.get_or_create_farcaster_user(user_identifier)
                user.sentiment = sentiment_data
                logger.info(f"Updated sentiment for Farcaster user {user_identifier}: {sentiment_data.label} ({sentiment_data.score})")
            elif platform == "matrix":
                user = self.get_or_create_matrix_user(user_identifier)
                user.sentiment = sentiment_data
                logger.info(f"Updated sentiment for Matrix user {user_identifier}: {sentiment_data.label} ({sentiment_data.score})")
            else:
                logger.warning(f"Unknown platform for sentiment update: {platform}")
                return
                
            self.state.last_update = time.time()
        except Exception as e:
            logger.error(f"Error updating user sentiment: {e}", exc_info=True)
    
    # === Memory Bank Management ===
    
    def set_history_recorder(self, history_recorder):
        """Set the history recorder for memory persistence."""
        self.history_recorder = history_recorder
        logger.info("WorldStateManager: Connected to HistoryRecorder for memory persistence")

    async def persist_user_memory(self, memory_entry: MemoryEntry) -> bool:
        """
        Persist a user memory entry using the HistoryRecorder.
        
        Args:
            memory_entry: MemoryEntry to persist
            
        Returns:
            bool: True if successfully persisted
        """
        if hasattr(self, 'history_recorder') and self.history_recorder:
            return await self.history_recorder.store_user_memory(memory_entry)
        else:
            logger.warning("WorldStateManager: No HistoryRecorder available for memory persistence")
            return False

    async def load_persisted_memories(self, user_platform_id: str) -> List[MemoryEntry]:
        """
        Load persisted memories for a user from the HistoryRecorder.
        
        Args:
            user_platform_id: Platform-specific user identifier
            
        Returns:
            List of MemoryEntry objects
        """
        if hasattr(self, 'history_recorder') and self.history_recorder:
            return await self.history_recorder.load_user_memories(user_platform_id)
        else:
            logger.warning("WorldStateManager: No HistoryRecorder available for loading memories")
            return []

    async def persist_research_entry(self, topic: str, research_data: dict) -> bool:
        """
        Persist a research entry using the HistoryRecorder.
        
        Args:
            topic: Research topic key
            research_data: Research information dictionary
            
        Returns:
            bool: True if successfully persisted
        """
        if hasattr(self, 'history_recorder') and self.history_recorder:
            return await self.history_recorder.store_research_entry(topic, research_data)
        else:
            logger.warning("WorldStateManager: No HistoryRecorder available for research persistence")
            return False

    async def load_persisted_research(self) -> dict:
        """
        Load persisted research entries from the HistoryRecorder.
        
        Returns:
            Dictionary of topic -> research_data
        """
        if hasattr(self, 'history_recorder') and self.history_recorder:
            return await self.history_recorder.load_research_entries()
        else:
            logger.warning("WorldStateManager: No HistoryRecorder available for loading research")
            return {}

    async def restore_persistent_state(self):
        """
        Restore user memories and research data from persistent storage.
        This should be called during startup to recover state across restarts.
        """
        try:
            if not hasattr(self, 'history_recorder') or not self.history_recorder:
                logger.warning("WorldStateManager: No HistoryRecorder available for state restoration")
                return
            
            # Load research database
            research_data = await self.load_persisted_research()
            self.state.research_database.update(research_data)
            logger.info(f"WorldStateManager: Restored {len(research_data)} research entries")
            
            # Load user memories for existing users
            # Note: We'll load memories on-demand when users are accessed
            # to avoid loading all user data at startup
            
            logger.info("WorldStateManager: Persistent state restoration completed")
            
        except Exception as e:
            logger.error(f"WorldStateManager: Error restoring persistent state: {e}")

    def add_user_memory(self, user_platform_id: str, memory_entry: MemoryEntry):
        """Add a memory entry for a specific user and persist it."""
        try:
            if user_platform_id not in self.state.user_memory_bank:
                self.state.user_memory_bank[user_platform_id] = []
            
            self.state.user_memory_bank[user_platform_id].append(memory_entry)
            
            # Keep only the most recent 100 memories per user to prevent bloat
            if len(self.state.user_memory_bank[user_platform_id]) > 100:
                # Sort by importance and recency, keep top 100
                memories = self.state.user_memory_bank[user_platform_id]
                memories.sort(key=lambda m: (m.importance, m.timestamp), reverse=True)
                self.state.user_memory_bank[user_platform_id] = memories[:100]
            
            self.state.last_update = time.time()
            logger.info(f"Added memory for user {user_platform_id}: {memory_entry.memory_type}")
            
            # Persist memory asynchronously if HistoryRecorder is available
            if hasattr(self, 'history_recorder') and self.history_recorder:
                # Schedule persistence without blocking
                import asyncio
                try:
                    asyncio.create_task(self.persist_user_memory(memory_entry))
                    logger.debug(f"Scheduled memory persistence for user {user_platform_id}")
                except RuntimeError:
                    # No event loop running, persistence will happen later
                    logger.debug(f"No event loop available, memory persistence deferred for user {user_platform_id}")
            
        except Exception as e:
            logger.error(f"Error adding user memory: {e}", exc_info=True)
    
    def get_user_memories(self, user_platform_id: str, limit: int = 10) -> List[MemoryEntry]:
        """Get recent memories for a user, loading from persistent storage if needed."""
        memories = self.state.user_memory_bank.get(user_platform_id, [])
        
        # If no memories in memory and we have a history recorder, try loading from persistence
        if not memories and hasattr(self, 'history_recorder') and self.history_recorder:
            try:
                import asyncio
                # Try to load persisted memories
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule for later if we're in an async context
                    logger.debug(f"Memories not in cache for {user_platform_id}, will load from persistence later")
                else:
                    # Load synchronously if no event loop is running
                    persisted_memories = loop.run_until_complete(self.load_persisted_memories(user_platform_id))
                    self.state.user_memory_bank[user_platform_id] = persisted_memories
                    memories = persisted_memories
                    logger.info(f"Loaded {len(memories)} persisted memories for user {user_platform_id}")
            except Exception as e:
                logger.debug(f"Could not load persisted memories for {user_platform_id}: {e}")
        
        # Sort by timestamp (most recent first) and return limited results
        sorted_memories = sorted(memories, key=lambda m: m.timestamp, reverse=True)
        return sorted_memories[:limit]
    
    def search_user_memories(self, user_platform_id: str, query: str, top_k: int = 3) -> List[MemoryEntry]:
        """Search memories for a user using simple keyword matching."""
        memories = self.state.user_memory_bank.get(user_platform_id, [])
        if not memories:
            return []
        
        query_lower = query.lower()
        scored_memories = []
        
        for memory in memories:
            score = 0.0
            content_lower = memory.content.lower()
            
            # Simple keyword matching - count keyword occurrences
            for word in query_lower.split():
                if word in content_lower:
                    score += 1
                # Boost for exact phrase match
                if query_lower in content_lower:
                    score += 2
            
            # Factor in memory importance
            score *= memory.importance
            
            if score > 0:
                scored_memories.append((score, memory))
        
        # Sort by score and return top_k
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        return [memory for _, memory in scored_memories[:top_k]]
    
    # === Tool Result Caching ===
    
    def cache_tool_result(self, tool_name: str, params_key: str, result: Dict[str, Any]):
        """Cache a tool result for later retrieval."""
        cache_key = f"{tool_name}:{params_key}"
        self.state.tool_cache[cache_key] = {
            "result": result,
            "timestamp": time.time(),
            "tool_name": tool_name,
            "params_key": params_key
        }
        
        # Clean up old cache entries (keep only last 24 hours)
        cutoff_time = time.time() - (24 * 3600)
        keys_to_remove = [
            key for key, value in self.state.tool_cache.items()
            if value.get("timestamp", 0) < cutoff_time
        ]
        for key in keys_to_remove:
            del self.state.tool_cache[key]
        
        self.state.last_update = time.time()
        logger.debug(f"Cached tool result: {cache_key}")
    
    def get_cached_tool_result(self, tool_name: str, params_key: str, max_age_seconds: int = 3600) -> Optional[Dict[str, Any]]:
        """Retrieve a cached tool result if it's still fresh."""
        cache_key = f"{tool_name}:{params_key}"
        cached = self.state.tool_cache.get(cache_key)
        
        if cached and (time.time() - cached["timestamp"]) < max_age_seconds:
            return cached["result"]
        return None
    
    def update_farcaster_user_timeline_cache(self, fid: str, timeline_data: Dict[str, Any]):
        """Update the timeline cache for a Farcaster user."""
        try:
            user = self.get_or_create_farcaster_user(fid)
            user.timeline_cache = timeline_data
            user.last_timeline_fetch = time.time()
            self.state.last_update = time.time()
            logger.info(f"Updated timeline cache for Farcaster user {fid}")
        except Exception as e:
            logger.error(f"Error updating Farcaster user timeline cache: {e}", exc_info=True)

    def has_bot_replied_to_matrix_event(self, original_event_id: str) -> bool:
        """
        Check if the bot has already sent a reply to a specific Matrix event.
        
        Args:
            original_event_id: The Matrix event ID that was replied to
            
        Returns:
            True if the bot has successfully replied to this event
        """
        from ...config import settings
        
        # First check in action_history for successful send_matrix_reply actions
        for action in self.state.action_history:
            if action.action_type == "send_matrix_reply":
                params = action.parameters or {}
                # Check both parameter names since input params use 'reply_to_id'
                reply_to_event_id = params.get("reply_to_id") or params.get("reply_to_event_id")
                if reply_to_event_id == original_event_id:
                    if action.result not in ["scheduled", "failure"]:
                        logger.debug(f"Bot reply found in action_history for event {original_event_id}: {action.result}")
                        return True
        
        # Also check in messages for bot replies (as a secondary verification)
        for platform_channels in self.state.channels.values():
            for channel in platform_channels.values():
                if channel.type == "matrix":
                    for msg in channel.recent_messages:
                        if (msg.sender == settings.MATRIX_USER_ID and 
                            msg.reply_to == original_event_id):
                            logger.debug(f"Bot reply found in messages for event {original_event_id}: message_id {msg.id}")
                            return True
        return False

    def get_daily_video_generation_count(self) -> int:
        """
        Get the number of videos generated today (since 00:00 UTC).
        
        Returns:
            Number of videos generated today
        """
        import datetime
        
        # Get start of today in UTC
        today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_timestamp = today_start.timestamp()
        
        # Count videos generated since today_start
        video_count = 0
        for media_entry in self.state.generated_media_library:
            if (media_entry.get("type") == "video" and 
                media_entry.get("timestamp", 0) >= today_start_timestamp):
                video_count += 1
        
        logger.debug(f"WorldState: Found {video_count} videos generated today")
        return video_count

    def record_matrix_reaction(self, room_id: str, event_id: str, reaction: str, reaction_event_id: str) -> None:
        """
        Record a Matrix reaction in the world state for deduplication tracking.
        
        Args:
            room_id: Matrix room ID where the reaction was made
            event_id: Event ID of the message that was reacted to
            reaction: The reaction emoji/text
            reaction_event_id: Event ID of the reaction itself
        """
        try:
            # Add to action history for tracking
            self.add_action_result(
                action_type="react_to_matrix_message",
                parameters={
                    "room_id": room_id,
                    "event_id": event_id,
                    "reaction": reaction
                },
                result=f"success: {reaction_event_id}",
            )
            
            logger.info(f"WorldState: Recorded Matrix reaction {reaction} to {event_id} in {room_id}")
            
        except Exception as e:
            logger.error(f"Error recording Matrix reaction: {e}", exc_info=True)

    def record_farcaster_like(self, cast_hash: str, like_hash: str) -> None:
        """
        Record a Farcaster like in the world state for deduplication tracking.
        
        Args:
            cast_hash: Hash of the cast that was liked
            like_hash: Hash of the like action
        """
        try:
            # Add to action history for tracking
            self.add_action_result(
                action_type="like_farcaster_post",
                parameters={"cast_hash": cast_hash},
                result=f"success: {like_hash}",
            )
            
            logger.info(f"WorldState: Recorded Farcaster like for cast {cast_hash}")
            
        except Exception as e:
            logger.error(f"Error recording Farcaster like: {e}", exc_info=True)

    def track_bot_reply_to_matrix_event(self, original_event_id: str, reply_event_id: str) -> None:
        """
        Track that the bot has replied to a specific Matrix event to prevent duplicate replies.
        
        Args:
            original_event_id: The Matrix event ID that was replied to
            reply_event_id: The Matrix event ID of the bot's reply
        """
        try:
            # This is already handled by the add_action_result in the service,
            # but we can add additional tracking if needed
            logger.debug(f"WorldState: Tracked bot reply {reply_event_id} to event {original_event_id}")
            
        except Exception as e:
            logger.error(f"Error tracking bot reply: {e}", exc_info=True)
