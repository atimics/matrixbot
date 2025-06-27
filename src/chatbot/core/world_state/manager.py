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
import pickle
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ...config import settings

if TYPE_CHECKING:
    from ..node_system.node_manager import NodeManager

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

    def __init__(self, state_file_path: str = "data/world_state.pkl"):
        self.state = WorldStateData()
        self.state_file = Path(state_file_path)
        
        # Node system integration (set by main orchestrator after initialization)
        self.node_manager: Optional["NodeManager"] = None
        
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
        self, channel_or_id, channel_type: str = None, name: str = None, status: str = "active"
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
            self.state.channels[channel.id] = channel
            logger.info(
                f"WorldState: Added {channel.type} channel '{channel.name}' ({channel.id}) with status '{channel.status}'"
            )
        else:
            # Adding by parameters
            channel_id = channel_or_id
            if channel_type is None or name is None:
                raise ValueError("channel_type and name are required when adding by parameters")
            
            self.state.channels[channel_id] = Channel(
                id=channel_id,
                type=channel_type,
                name=name,
                status=status,
                last_status_update=time.time(),
            )
            # Set last_checked after creation
            self.state.channels[channel_id].update_last_checked()
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
        if channel_id not in self.state.channels:
            # Auto-create channel if it doesn't exist
            self.add_channel(channel_id, channel_type=message.channel_type, name=channel_id)
        self.state.channels[channel_id].recent_messages.append(message)
        # Limit to 50 messages per channel
        if len(self.state.channels[channel_id].recent_messages) > 50:
            self.state.channels[channel_id].recent_messages = self.state.channels[channel_id].recent_messages[-50:]
        self.state.channels[channel_id].update_last_checked()
        
        # CRITICAL: Update thread state for turn-based conversation management
        self._update_thread_on_new_message(message)
        
        # Notify AttentionEngine of new message (thread-centric architecture)
        if hasattr(self, 'attention_engine') and self.attention_engine:
            try:
                import asyncio
                # Schedule the attention processing without blocking
                asyncio.create_task(self.attention_engine.process_new_message(message))
            except Exception as e:
                logger.warning(f"Error notifying AttentionEngine: {e}")

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
            filtered_channels = {
                ch_id: ch_data for ch_id, ch_data in observation["channels"].items()
                if ch_id in channels_filter
            }
            observation["channels"] = filtered_channels
        
        # Include thread context for AI to follow conversation threads
        observation["threads"] = {}
        for thread_id, thread in self.state.threads.items():
            # Get bot ID safely for this platform
            if thread.platform == 'farcaster':
                bot_id = str(getattr(settings.farcaster, 'bot_fid', '')) if hasattr(settings, 'farcaster') else ''
            else:
                bot_id = str(getattr(settings.matrix, 'user_id', '')) if hasattr(settings, 'matrix') else ''
            
            observation["threads"][thread_id] = {
                "thread_id": thread.thread_id,
                "platform": thread.platform,
                "messages": [msg.__dict__ for msg in thread.messages],
                "participants": list(thread.participants),
                "last_activity_timestamp": thread.last_activity_timestamp,
                "message_count": thread.message_count,
                "last_speaker_id": thread.last_speaker_id,
                "is_bot_turn": thread.is_bot_turn(bot_id) if bot_id else False
            }

        # ENHANCEMENT: Include recently replied-to casts to prevent duplicate replies
        # This helps the AI avoid attempting replies to casts it has already responded to
        observation["recently_replied_to_casts"] = self._get_recently_replied_to_casts(lookback_seconds)

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
            if action.action_type == "send_farcaster_post":
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

    def _get_recently_replied_to_casts(self, lookback_seconds: int) -> Dict[str, Any]:
        """
        Get a list of recently replied-to casts to help AI avoid duplicate replies.
        
        This method extracts successful Farcaster replies from the action history
        to provide the AI with context about which casts it has already responded to.
        
        Args:
            lookback_seconds: Time window for recent replies
            
        Returns:
            Dictionary containing recent reply information
        """
        cutoff_time = time.time() - lookback_seconds
        recent_replies = []
        
        for action in reversed(self.state.action_history):
            # Stop if we've gone beyond the time window
            if action.timestamp < cutoff_time:
                break
                
            # Look for successful Farcaster replies
            if (action.action_type == "send_farcaster_post" and 
                action.parameters.get("reply_to_hash") and
                action.result in ["success", "scheduled"]):  # Include scheduled to prevent duplication
                
                reply_info = {
                    "reply_to_hash": action.parameters.get("reply_to_hash"),
                    "reply_content": action.parameters.get("content", ""),
                    "timestamp": action.timestamp,
                    "result": action.result,
                    "cast_hash": action.parameters.get("cast_hash")  # If available
                }
                recent_replies.append(reply_info)
        
        # Reverse to get chronological order (oldest first)
        recent_replies.reverse()
        
        return {
            "recent_replies": recent_replies,
            "reply_count": len(recent_replies),
            "lookback_seconds": lookback_seconds,
            "summary": f"Bot has replied to {len(recent_replies)} casts in the last {lookback_seconds//60} minutes"
        }

    def get_channel(self, channel_id: str) -> Optional[Channel]:
        """Get a channel by ID"""
        return self.state.channels.get(channel_id)

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
        if channel_id in self.state.channels:
            old_status = self.state.channels[channel_id].status
            self.state.channels[channel_id].status = new_status
            self.state.channels[channel_id].last_status_update = time.time()
            self.state.last_update = time.time()
            logger.info(
                f"WorldState: Updated channel {channel_id} ({self.state.channels[channel_id].name}) status from '{old_status}' to '{new_status}'"
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
        metadata: Optional[Dict[str, Any]] = None,
        raw_image_data: Optional[bytes] = None,  # NEW: Store raw bytes for Matrix optimization
        image_mime_type: Optional[str] = None    # NEW: MIME type for raw data
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
            raw_image_data: Raw image bytes for Matrix optimization (temporary storage)
            image_mime_type: MIME type for the raw image data
        """
        media_entry = {
            "url": media_url,
            "type": media_type,
            "prompt": prompt,
            "service_used": service_used,
            "timestamp": time.time(),
            "aspect_ratio": aspect_ratio,
            "metadata": metadata or {},
            "raw_image_data": raw_image_data,  # NEW: Include raw bytes for optimization
            "image_mime_type": image_mime_type  # NEW: Include MIME type
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

    def get_last_generated_media_with_raw_data(self) -> Optional[Dict[str, Any]]:
        """
        Returns the most recently generated media entry that has raw image data.
        This is used for Matrix upload optimization to avoid re-downloading.
        
        Returns:
            Dict with media entry containing raw_image_data, or None if not available
        """
        if not self.state.generated_media_library:
            return None
            
        # Check recent entries (last 3) for raw data within the last 5 minutes
        cutoff_time = time.time() - 300  # 5 minutes
        
        for media_entry in reversed(self.state.generated_media_library[-3:]):
            if (media_entry.get("raw_image_data") and 
                media_entry.get("image_mime_type") and
                media_entry.get("timestamp", 0) > cutoff_time):
                return media_entry
                
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

    def update_user_sentiment_from_action(self, platform: str, user_identifier: str, action_type: str):
        """
        Update user sentiment based on social actions (likes, reactions, mentions, etc.).
        
        Args:
            platform: The platform ('farcaster' or 'matrix')
            user_identifier: User's platform ID (FID for Farcaster, user_id for Matrix)
            action_type: Type of action performed
        """
        try:
            # Get or create user
            if platform == "farcaster":
                user = self.get_or_create_farcaster_user(user_identifier)
            elif platform == "matrix":
                user = self.get_or_create_matrix_user(user_identifier)
            else:
                logger.warning(f"Unknown platform for sentiment update: {platform}")
                return
            
            # Create default sentiment if none exists
            if not user.sentiment:
                user.sentiment = SentimentData(
                    score=0.0,
                    label="neutral",
                    last_updated=time.time(),
                    current_sentiment="neutral"
                )
            
            # Define sentiment weight adjustments based on action type
            sentiment_weights = {
                'mention': 0.3,            # Direct mentions/replies to bot
                'positive_reaction': 0.2,   # Likes, recasts, positive reactions
                'like': 0.1,               # Simple likes
                'recast': 0.2,             # Recasts/shares
                'quote_post': 0.2,         # Quote posts
                'no_feedback_on_reply': -0.05,  # No reaction to bot's reply
                'negative_text_sentiment': -0.4,  # Negative text analysis
            }
            
            # Apply sentiment adjustment
            weight = sentiment_weights.get(action_type, 0.0)
            old_score = user.sentiment.score
            user.sentiment.score = max(-1.0, min(1.0, old_score + weight))
            user.sentiment.last_updated = time.time()
            user.sentiment.last_interaction_time = time.time()
            
            # Update sentiment label
            if user.sentiment.score > 0.3:
                user.sentiment.label = "positive"
                user.sentiment.current_sentiment = "positive"
            elif user.sentiment.score < -0.2:
                user.sentiment.label = "negative"
                user.sentiment.current_sentiment = "negative"
            else:
                user.sentiment.label = "neutral"
                user.sentiment.current_sentiment = "neutral"
            
            # Add to interaction history
            interaction_event = {
                "timestamp": time.time(),
                "action_type": action_type,
                "weight": weight,
                "old_score": old_score,
                "new_score": user.sentiment.score
            }
            user.sentiment.interaction_history.append(interaction_event)
            
            # Keep only last 20 interaction events
            if len(user.sentiment.interaction_history) > 20:
                user.sentiment.interaction_history = user.sentiment.interaction_history[-20:]
            
            # Add to sentiment history
            history_entry = {
                "timestamp": time.time(),
                "sentiment": user.sentiment.label,
                "score": user.sentiment.score,
                "trigger": action_type
            }
            user.sentiment.history.append(history_entry)
            
            # Keep only last 10 history entries
            if len(user.sentiment.history) > 10:
                user.sentiment.history = user.sentiment.history[-10:]
            
            logger.info(f"Updated sentiment for {platform} user {user_identifier} from {action_type}: "
                       f"{old_score:.2f} -> {user.sentiment.score:.2f} ({user.sentiment.label})")
            
            self.state.last_update = time.time()
            
        except Exception as e:
            logger.error(f"Error updating user sentiment from action: {e}", exc_info=True)
    
    # === Memory Bank Management ===
    
    def add_user_memory(self, user_platform_id: str, memory_entry: MemoryEntry):
        """Add a memory entry for a specific user."""
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
            
        except Exception as e:
            logger.error(f"Error adding user memory: {e}", exc_info=True)
    
    def get_user_memories(self, user_platform_id: str, limit: int = 10) -> List[MemoryEntry]:
        """Get recent memories for a user."""
        memories = self.state.user_memory_bank.get(user_platform_id, [])
        # Sort by timestamp (most recent first)
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
        for channel in self.state.channels.values():
            if channel.type == "matrix":
                for msg in channel.recent_messages:
                    if (msg.sender == settings.matrix.user_id and 
                        msg.reply_to == original_event_id):
                        logger.debug(f"Bot reply found in messages for event {original_event_id}: message_id {msg.id}")
                        return True
        return False

    def set_attention_engine(self, attention_engine) -> None:
        """
        Set the AttentionEngine for this WorldStateManager.
        
        This allows the WorldStateManager to notify the AttentionEngine
        when new messages are added, enabling the attention-driven architecture.
        
        Args:
            attention_engine: The AttentionEngine instance to notify on new messages
        """
        self.attention_engine = attention_engine
        logger.info(f"AttentionEngine connected to WorldStateManager (type: {type(attention_engine).__name__})")
        
        # Verify the connection works
        if hasattr(attention_engine, 'neynar_api_client'):
            has_client = attention_engine.neynar_api_client is not None
            logger.info(f"  AttentionEngine context hydration capability: {'Enabled' if has_client else 'Disabled'}")
        else:
            logger.warning("  AttentionEngine does not have neynar_api_client attribute")

    def get_last_bot_activity_in_thread(self, thread_id: str, channel_id: Optional[str] = None) -> Optional[float]:
        """
        Get the timestamp of the last bot activity in a specific thread.
        
        Args:
            thread_id: Thread identifier
            channel_id: Optional channel identifier for more specific lookup
            
        Returns:
            Timestamp of last bot activity or None if no recent activity
        """
        try:
            # If channel_id is provided, search that specific channel
            if channel_id and channel_id in self.state.channels:
                channel = self.state.channels[channel_id]
                for message in reversed(channel.recent_messages):
                    if message.is_from_bot():
                        # Check if this message is in the same thread
                        if message.reply_to == thread_id or message.id == thread_id:
                            return message.timestamp
                        # For messages without explicit threading, use time proximity
                        elif not message.reply_to and abs(message.timestamp - time.time()) < 300:  # 5 minutes
                            return message.timestamp
            else:
                # Search all channels if no specific channel provided
                for channel in self.state.channels.values():
                    for message in reversed(channel.recent_messages):
                        if message.is_from_bot():
                            if message.reply_to == thread_id or message.id == thread_id:
                                return message.timestamp
            
            return None
            
        except Exception as e:
            logger.warning(f"Error getting last bot activity in thread {thread_id}: {e}")
            return None
    
    def get_conversation_history(self, message_id: str, channel_id: Optional[str] = None) -> List:
        """
        Get the conversation history for a message thread.
        
        Args:
            message_id: Message ID to get history for
            channel_id: Optional channel ID to limit search
            
        Returns:
            List of messages in the conversation thread
        """
        try:
            history = []
            
            # Search channels for the conversation thread
            channels_to_search = [self.state.channels[channel_id]] if channel_id and channel_id in self.state.channels else self.state.channels.values()
            
            for channel in channels_to_search:
                for message in channel.recent_messages:
                    if message.id == message_id or message.reply_to == message_id:
                        history.append(message)
            
            # Sort by timestamp
            history.sort(key=lambda x: x.timestamp)
            return history[-10:]  # Last 10 messages max
            
        except Exception as e:
            logger.warning(f"Error getting conversation history for {message_id}: {e}")
            return []
    
    def get_user_profile(self, platform: str, user_identifier: str):
        """
        Get user profile information for a given platform and identifier.
        
        Args:
            platform: Platform type ('farcaster' or 'matrix')
            user_identifier: User identifier (FID for Farcaster, user_id for Matrix)
            
        Returns:
            User profile object or None if not found
        """
        try:
            if platform == 'farcaster':
                return self.state.farcaster_users.get(user_identifier)
            elif platform == 'matrix':
                return self.state.matrix_users.get(user_identifier)
            return None
        except Exception as e:
            logger.warning(f"Error getting user profile for {platform}:{user_identifier}: {e}")
            return None
    
    def get_channel_by_id(self, channel_id: str):
        """
        Get channel information by ID.
        
        Args:
            channel_id: Channel identifier
            
        Returns:
            Channel object or None if not found
        """
        try:
            return self.state.channels.get(channel_id)
        except Exception as e:
            logger.warning(f"Error getting channel {channel_id}: {e}")
            return None

    def is_thread_active(self, thread_id: str) -> bool:
        """
        DEPRECATED: Use is_bot_turn_in_thread for proper turn-based validation.
        
        This method is kept for compatibility but should be replaced with
        the new turn-based conversation logic.
        """
        logger.warning("is_thread_active is deprecated. Use is_bot_turn_in_thread instead.")
        return self.is_bot_turn_in_thread(thread_id)
    
    def is_bot_turn_in_thread(self, thread_id: str) -> bool:
        """
        Check if it's the bot's turn to speak in a thread with socially-aware logic.
        
        This method implements sophisticated turn-taking logic that considers:
        1. Direct mentions of the bot (always allow response)
        2. Standard turn-taking (bot can speak if it wasn't the last speaker)
        3. Group conversation dynamics (new speakers reset turn state)
        
        Args:
            thread_id: The thread identifier to check
            
        Returns:
            True if the bot should participate in this thread
        """
        thread = self.state.threads.get(thread_id)
        if not thread:
            logger.warning(f"Turn validation failed: Thread '{thread_id}' does not exist. Context should have been hydrated by AttentionEngine.")
            return False

        # Must be a real conversation (allow bot to participate in any thread with activity)
        if thread.message_count < 1:
            logger.debug(f"Turn validation failed: Thread '{thread_id}' has no messages.")
            return False

        # Must have recent activity (within last 24 hours)
        if not thread.is_active():
            logger.debug(f"Turn validation failed: Thread '{thread_id}' is inactive.")
            return False
        
        # Import bot settings to get bot ID
        from ...config import settings
        
        # Get bot ID based on platform - use consistent identifiers
        if thread.platform == 'matrix':
            bot_id = settings.matrix.user_id
            bot_username = settings.matrix.user_id  # For Matrix, user_id is also the username
        elif thread.platform == 'farcaster':
            # For Farcaster, use username as the primary identifier
            bot_id = settings.farcaster.bot_username
            bot_username = settings.farcaster.bot_username
        else:
            logger.warning(f"Unknown platform for thread {thread_id}: {thread.platform}")
            return False
            
        if not bot_id or not bot_username:
            logger.warning(f"Bot ID/username not available for platform {thread.platform}")
            return False

        # Get the most recent message in the thread
        if not thread.messages:
            logger.debug(f"Turn validation failed: Thread '{thread_id}' has no messages in history.")
            return False
        
        latest_message = thread.messages[-1]  # Messages are sorted by timestamp
        
        # === RULE 1: Direct Mention Override ===
        # If the latest message mentions the bot, always allow response regardless of turn state
        mention_indicators = [f"@{bot_username}", bot_username.lower(), bot_id.lower()]
        if any(indicator in latest_message.content.lower() for indicator in mention_indicators):
            logger.info(f"Turn validation passed: Direct mention detected in thread '{thread_id}' - bot can always respond to mentions.")
            return True
        
        # === RULE 2: Standard Turn-Taking ===
        # Bot can speak if it wasn't the last speaker
        if thread.last_speaker_id != bot_id:
            logger.info(f"Turn validation passed: It is the bot's turn in thread '{thread_id}' (last speaker: {thread.last_speaker_id}).")
            return True
        
        # If we reach here, bot was the last speaker and there's no mention
        logger.info(f"Turn validation failed: Bot was the last speaker in thread '{thread_id}' and no direct mention detected. Waiting for user response.")
        
        # ENHANCEMENT: Check for recent failed actions to prevent immediate retries
        if thread.has_recent_failed_action('send_farcaster_post') or thread.has_recent_failed_action('send_matrix_message'):
            logger.info(f"Turn validation failed: Recent failed action in thread '{thread_id}'. Waiting for cooldown.")
            return False
            
        return False

    def _update_thread_on_new_message(self, message) -> None:
        """
        Update thread state when a new message arrives.
        
        This is critical for turn-based conversation management. It determines
        whose turn it is to speak next in each conversation thread.
        
        Args:
            message: The new message that was just added
        """
        if not message or message.channel_type not in ["farcaster", "matrix"]:
            return
            
        thread_id = message.reply_to or message.id
        
        # Create thread if it doesn't exist
        if thread_id not in self.state.threads:
            from .structures import Thread
            self.state.threads[thread_id] = Thread(
                thread_id=thread_id,
                platform=message.channel_type
            )
        
        thread = self.state.threads[thread_id]
        
        # Add message if not already present
        if not any(m.id == message.id for m in thread.messages):
            thread.messages.append(message)
            thread.message_count += 1
            thread.messages.sort(key=lambda m: m.timestamp)
            if len(thread.messages) > 50:
                thread.messages = thread.messages[-50:]
        
        # Update thread participants and activity
        thread.participants.add(message.sender)
        thread.last_activity_timestamp = max(thread.last_activity_timestamp, message.timestamp)
        
        # CRITICAL: Update turn state with multi-user conversation handling
        from ...config import settings
        
        # Determine bot ID for this platform - use consistent identifiers
        if message.channel_type == 'matrix':
            bot_id = settings.matrix.user_id
        elif message.channel_type == 'farcaster':
            # For Farcaster, use username as the primary identifier
            bot_id = settings.farcaster.bot_username
        else:
            bot_id = None
        
        # ENHANCEMENT: Handle "New Speaker" Turn Reset for multi-user conversations
        if bot_id and message.sender != bot_id:
            # A user spoke - check if this creates a new conversational turn
            
            # If bot was the last speaker and this is a different user than who spoke before bot's last message
            if thread.last_speaker_id == bot_id and len(thread.messages) >= 2:
                # Find the message before the bot's last message to see who was speaking then
                bot_messages = [m for m in thread.messages if m.sender == bot_id]
                if bot_messages:
                    last_bot_message = bot_messages[-1]
                    # Find messages before the last bot message
                    pre_bot_messages = [m for m in thread.messages if m.timestamp < last_bot_message.timestamp]
                    if pre_bot_messages:
                        last_pre_bot_speaker = pre_bot_messages[-1].sender
                        # If current speaker is different from who spoke before bot's last message
                        if message.sender != last_pre_bot_speaker:
                            logger.info(f"New speaker {message.sender} detected in thread {thread_id} - resetting bot's turn")
                            thread.last_speaker_id = message.sender
                            thread.bot_turn_timestamp = time.time()
                            return
            
            # Normal case: User spoke, now it's bot's turn
            thread.last_speaker_id = message.sender
            thread.bot_turn_timestamp = time.time()
            logger.debug(f"User {message.sender} spoke in thread {thread_id}, now bot's turn")
            
        # If the bot spoke, it's no longer the bot's turn
        elif bot_id and message.sender == bot_id:
            thread.last_speaker_id = bot_id
            thread.bot_turn_timestamp = None
            logger.debug(f"Bot spoke in thread {thread_id}, waiting for user response")
    
    def record_action_failure(self, thread_id: str, action_type: str, error: str) -> None:
        """
        Record a failed action in the specified thread to prevent immediate retries.
        
        Args:
            thread_id: The thread where the action failed
            action_type: Type of action that failed (e.g., 'send_farcaster_post')
            error: Error message or reason for failure
        """
        thread = self.state.threads.get(thread_id)
        if thread:
            thread.add_failed_action(action_type, error)
            logger.info(f"Recorded failed action {action_type} in thread {thread_id}: {error}")
        else:
            logger.warning(f"Cannot record failed action - thread {thread_id} not found")

    def record_and_check_daily_interaction(self, user_id: str) -> bool:
        """
        Records an interaction with a user for the current day and checks if the daily cap is exceeded.
        Returns True if the cap is exceeded, False otherwise.
        """
        from datetime import datetime
        from ...config import settings

        today_str = datetime.utcnow().strftime('%Y-%m-%d')
        daily_cap = getattr(settings.processing, 'daily_unsolicited_reply_cap', 5)

        if user_id not in self.state.daily_interaction_counts:
            self.state.daily_interaction_counts[user_id] = {}

        # Clean up old dates for this user
        self.state.daily_interaction_counts[user_id] = {
            date: count for date, count in self.state.daily_interaction_counts[user_id].items() if date == today_str
        }

        today_count = self.state.daily_interaction_counts[user_id].get(today_str, 0)

        if today_count >= daily_cap:
            logger.warning(f"Daily interaction cap of {daily_cap} reached for user {user_id}.")
            return True # Cap exceeded

        # Increment and record
        self.state.daily_interaction_counts[user_id][today_str] = today_count + 1
        return False # Still within cap
    
    def add_pending_feedback_action(self, reply_event_id: str, original_event_id: str, 
                                   user_id: str, platform: str, feedback_threshold_time: float = 3600):
        """
        Add a pending feedback action to track bot replies awaiting user feedback.
        
        Args:
            reply_event_id: ID of the bot's reply message/cast
            original_event_id: ID of the original message/cast being replied to
            user_id: Identifier of the user who received the reply
            platform: Platform where the interaction occurred ('farcaster' or 'matrix')
            feedback_threshold_time: Time in seconds after which lack of feedback is negative (default 1 hour)
        """
        try:
            from .structures import PendingFeedbackAction
            
            pending_action = PendingFeedbackAction(
                reply_event_id=reply_event_id,
                original_event_id=original_event_id,
                user_id=user_id,
                platform=platform,
                timestamp=time.time(),
                feedback_threshold_time=feedback_threshold_time
            )
            
            self.state.pending_feedback_actions[reply_event_id] = pending_action
            self.state.last_update = time.time()
            
            logger.debug(f"Added pending feedback action for {platform} reply {reply_event_id} to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error adding pending feedback action: {e}", exc_info=True)

    def remove_pending_feedback_action(self, reply_event_id: str) -> bool:
        """
        Remove a pending feedback action when feedback is received.
        
        Args:
            reply_event_id: ID of the reply event to remove
            
        Returns:
            True if action was found and removed, False otherwise
        """
        try:
            if reply_event_id in self.state.pending_feedback_actions:
                del self.state.pending_feedback_actions[reply_event_id]
                self.state.last_update = time.time()
                logger.debug(f"Removed pending feedback action for reply {reply_event_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error removing pending feedback action: {e}", exc_info=True)
            return False

    def get_expired_pending_feedback_actions(self) -> List:
        """
        Get all pending feedback actions that have expired (past their threshold time).
        
        Returns:
            List of PendingFeedbackAction objects that have exceeded their threshold time
        """
        try:
            expired_actions = []
            current_time = time.time()
            
            for reply_event_id, action in list(self.state.pending_feedback_actions.items()):
                if current_time - action.timestamp > action.feedback_threshold_time:
                    expired_actions.append(action)
            
            return expired_actions
            
        except Exception as e:
            logger.error(f"Error getting expired feedback actions: {e}", exc_info=True)
            return []

    def apply_time_decay_to_sentiment(self, decay_factor: float = 0.99):
        """
        Apply time decay to all user sentiment scores to gradually move them toward neutral.
        
        Args:
            decay_factor: Factor to multiply sentiment scores by (default 0.99 for gradual decay)
        """
        try:
            updated_count = 0
            
            # Apply decay to Farcaster users
            for user in self.state.farcaster_users.values():
                if user.sentiment and user.sentiment.score != 0.0:
                    old_score = user.sentiment.score
                    user.sentiment.score *= decay_factor
                    
                    # Update label if score changed significantly
                    if abs(old_score - user.sentiment.score) > 0.01:
                        if user.sentiment.score > 0.3:
                            user.sentiment.label = "positive"
                            user.sentiment.current_sentiment = "positive"
                        elif user.sentiment.score < -0.2:
                            user.sentiment.label = "negative"
                            user.sentiment.current_sentiment = "negative"
                        else:
                            user.sentiment.label = "neutral"
                            user.sentiment.current_sentiment = "neutral"
                        
                        user.sentiment.last_updated = time.time()
                        updated_count += 1
            
            # Apply decay to Matrix users
            for user in self.state.matrix_users.values():
                if user.sentiment and user.sentiment.score != 0.0:
                    old_score = user.sentiment.score
                    user.sentiment.score *= decay_factor
                    
                    # Update label if score changed significantly
                    if abs(old_score - user.sentiment.score) > 0.01:
                        if user.sentiment.score > 0.3:
                            user.sentiment.label = "positive"
                            user.sentiment.current_sentiment = "positive"
                        elif user.sentiment.score < -0.2:
                            user.sentiment.label = "negative"
                            user.sentiment.current_sentiment = "negative"
                        else:
                            user.sentiment.label = "neutral"
                            user.sentiment.current_sentiment = "neutral"
                        
                        user.sentiment.last_updated = time.time()
                        updated_count += 1
            
            if updated_count > 0:
                self.state.last_update = time.time()
                logger.debug(f"Applied sentiment decay to {updated_count} users")
                
        except Exception as e:
            logger.error(f"Error applying sentiment decay: {e}", exc_info=True)

    def save_state(self) -> None:
        """Serialize and save the current world state to a file."""
        try:
            # Ensure the data directory exists
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Create a backup of the current state file if it exists
            if self.state_file.exists():
                backup_path = self.state_file.with_suffix('.pkl.backup')
                self.state_file.rename(backup_path)
                logger.debug(f"Created backup of world state at {backup_path}")
            
            # Save the current state
            with open(self.state_file, 'wb') as f:
                pickle.dump(self.state, f)
            logger.info(f"World state successfully saved to {self.state_file}")
            
        except Exception as e:
            logger.error(f"Failed to save world state: {e}")
            # If backup exists, restore it
            backup_path = self.state_file.with_suffix('.pkl.backup')
            if backup_path.exists():
                backup_path.rename(self.state_file)
                logger.info("Restored backup after save failure")

    def load_state(self) -> None:
        """Load the world state from a file if it exists."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'rb') as f:
                    loaded_state = pickle.load(f)
                    # Validate the loaded state
                    if isinstance(loaded_state, WorldStateData):
                        self.state = loaded_state
                        logger.info(f"World state successfully loaded from {self.state_file}")
                        
                        # Ensure system_status exists (for backward compatibility)
                        if not hasattr(self.state, 'system_status') or self.state.system_status is None:
                            self.state.system_status = {
                                "matrix_connected": False,
                                "farcaster_connected": False,
                                "last_observation_cycle": 0,
                                "total_cycles": 0,
                            }
                            logger.info("Initialized system_status for backward compatibility")
                    else:
                        logger.error("Invalid state file format, starting with fresh state")
                        self.state = WorldStateData()
            except Exception as e:
                logger.error(f"Failed to load world state, starting fresh: {e}")
                self.state = WorldStateData()
        else:
            logger.info("No saved world state found, starting with a fresh state.")
