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

from .structures import WorldStateData, Message, Channel, ActionHistory

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

    def add_channel(
        self, channel_id: str, channel_type: str, name: str, status: str = "active"
    ):
        """Add a new channel to monitor"""
        self.state.channels[channel_id] = Channel(
            id=channel_id,
            type=channel_type,
            name=name,
            recent_messages=[],
            last_checked=time.time(),
            status=status,
            last_status_update=time.time(),
        )
        logger.info(
            f"WorldState: Added {channel_type} channel '{name}' ({channel_id}) with status '{status}'"
        )

    def add_message(self, channel_id: str, message: Message):
        """Add a new message to a channel"""
        # Deduplicate across channels
        if message.id in self.state.seen_messages:
            logger.debug(f"WorldStateManager: Deduplicated message {message.id}")
            return
        self.state.seen_messages.add(message.id)
        
        # Handle None channel_id gracefully
        if not channel_id:
            channel_id = f"{message.channel_type}:unknown"
            logger.warning(f"None channel_id provided, using fallback: {channel_id}")

        if channel_id not in self.state.channels:
            # Auto-create channel if it doesn't exist
            logger.info(f"WorldState: Auto-creating unknown channel {channel_id}")
            self.add_channel(channel_id, message.channel_type, f"Channel {channel_id}")

        channel = self.state.channels[channel_id]
        channel.recent_messages.append(message)

        # Keep only last 50 messages per channel
        if len(channel.recent_messages) > 50:
            channel.recent_messages = channel.recent_messages[-50:]

        channel.last_checked = time.time()
        self.state.last_update = time.time()
        
        # Thread management: group Farcaster messages by root cast
        if message.channel_type == "farcaster":
            thread_id = message.reply_to or message.id
            self.state.threads.setdefault(thread_id, []).append(message)
            logger.info(f"WorldStateManager: Added message to thread '{thread_id}'")

        logger.info(
            f"WorldState: New message in {channel.name}: {message.sender}: {message.content[:100]}..."
        )
    
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

    def get_observation_data(self, lookback_seconds: int = 300) -> Dict[str, Any]:
        """Get current world state data for AI observation"""
        observation = self.state.get_recent_activity(lookback_seconds)
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

        Args:
            cast_hash: The hash of the cast to check

        Returns:
            True if the AI has successfully replied to this cast (not just scheduled)
        """
        for action in self.state.action_history:
            if action.action_type == "send_farcaster_reply":
                reply_to_hash = action.parameters.get("reply_to_hash")
                if reply_to_hash == cast_hash:
                    # Only count as replied if it was actually successful, not just scheduled
                    if action.result not in ["scheduled", "failure"]:
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
        self, cast_hash: str, s3_url: str, media_type: str, channel_id: str
    ):
        """
        Record that the bot posted media to Farcaster for engagement tracking.

        Args:
            cast_hash: Farcaster cast hash
            s3_url: S3 URL of the media
            media_type: 'image' or 'video'
            channel_id: Farcaster channel where posted
        """
        self.state.bot_media_on_farcaster[cast_hash] = {
            "s3_url": s3_url,
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
            media_url: S3 URL or other URL of the generated media
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

    def get_world_state_data(self) -> WorldStateData:
        """
        Get direct access to the underlying WorldStateData object.
        
        Returns:
            The WorldStateData instance managed by this manager
        """
        return self.state
