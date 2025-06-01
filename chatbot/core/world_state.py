#!/usr/bin/env python3
"""
World State Management

This module manages the current state of the world that the AI observes and acts upon.
The world state includes:
- Matrix channels and recent messages
- Farcaster feed and recent posts  
- System status and capabilities
- Recent action history
"""

import asyncio
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Represents a message in any channel"""

    id: str
    channel_id: str
    channel_type: str  # 'matrix' or 'farcaster'
    sender: str  # Display name for Matrix, username for Farcaster
    content: str
    timestamp: float
    reply_to: Optional[str] = None

    # Enhanced user information for social platforms like Farcaster
    sender_username: Optional[str] = None  # @username for tagging (Farcaster)
    sender_display_name: Optional[str] = None  # Human-readable display name
    sender_fid: Optional[int] = None  # Farcaster ID number
    sender_pfp_url: Optional[str] = None  # Profile picture URL
    sender_bio: Optional[str] = None  # User bio/description
    sender_follower_count: Optional[int] = None  # Number of followers
    sender_following_count: Optional[int] = None  # Number of following

    # Platform-specific metadata
    metadata: Dict[str, Any] = field(
        default_factory=dict
    )  # Additional platform-specific data

    def to_ai_summary_dict(self) -> Dict[str, Any]:
        """Return a summarized version for AI payload to reduce token usage."""
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "channel_type": self.channel_type,
            "sender_username": self.sender_username or self.sender,
            "content": self.content[:250] + "..."
            if len(self.content) > 250
            else self.content,
            "timestamp": self.timestamp,
            "reply_to": self.reply_to,
            "sender_fid": self.sender_fid,
            "sender_follower_count": self.sender_follower_count,
            "metadata": {
                "power_badge": self.metadata.get("power_badge", False)
                if self.metadata
                else False,
                "is_bot": self.metadata.get("is_bot", False)
                if self.metadata
                else False,
            },
        }

    def is_from_bot(
        self, bot_fid: Optional[str] = None, bot_username: Optional[str] = None
    ) -> bool:
        """Check if this message is from the bot itself."""
        if bot_fid and str(self.sender_fid) == str(bot_fid):
            return True
        if bot_username and (
            self.sender_username == bot_username or self.sender == bot_username
        ):
            return True
        return False


@dataclass
class Channel:
    """Represents a communication channel with full metadata"""

    id: str  # Room ID for Matrix, channel ID for Farcaster
    type: str  # 'matrix' or 'farcaster'
    name: str  # Display name
    recent_messages: List[Message]
    last_checked: float

    # Matrix-specific details
    canonical_alias: Optional[str] = None  # #room:server.com
    alt_aliases: List[str] = field(default_factory=list)  # Alternative aliases
    topic: Optional[str] = None  # Room topic/description
    avatar_url: Optional[str] = None  # Room avatar
    member_count: int = 0  # Number of members
    encrypted: bool = False  # Is room encrypted
    public: bool = True  # Is room publicly joinable
    power_levels: Dict[str, int] = field(default_factory=dict)  # User power levels
    creation_time: Optional[float] = None  # When room was created

    def __post_init__(self):
        pass

    def get_activity_summary(self) -> Dict[str, Any]:
        """Get a summary of recent channel activity with timestamp range."""
        if not self.recent_messages:
            return {
                "message_count": 0,
                "last_activity": None,
                "active_users": [],
                "summary": "No recent activity",
                "timestamp_range": None,
            }

        active_users = list(
            set(msg.sender_username or msg.sender for msg in self.recent_messages[-5:])
        )
        last_msg = self.recent_messages[-1]
        first_msg = self.recent_messages[0]

        return {
            "message_count": len(self.recent_messages),
            "last_activity": last_msg.timestamp,
            "last_message": last_msg.content[:100] + "..."
            if len(last_msg.content) > 100
            else last_msg.content,
            "last_sender": last_msg.sender_username or last_msg.sender,
            "active_users": active_users[:5],  # Top 5 active users
            "summary": f"Last: {last_msg.sender_username or last_msg.sender}: {last_msg.content[:50]}...",
            "timestamp_range": {
                "start": first_msg.timestamp,
                "end": last_msg.timestamp,
                "span_hours": round(
                    (last_msg.timestamp - first_msg.timestamp) / 3600, 2
                ),
            },
        }


@dataclass
class ActionHistory:
    """Represents a completed action"""

    action_type: str
    parameters: Dict[str, Any]
    result: str
    timestamp: float
    action_id: Optional[str] = None  # Unique ID for tracking/updating scheduled actions


class WorldState:
    """The complete observable state of the world"""

    def __init__(self):
        """Initialize empty world state"""
        self.channels: Dict[str, Channel] = {}
        self.action_history: List[ActionHistory] = []
        self.system_status: Dict[str, Any] = {}
        self.threads: Dict[
            str, List[Message]
        ] = {}  # Map root cast id to thread messages
        self.thread_roots: Dict[str, Message] = {}  # Root message for each thread
        self.seen_messages: set[str] = set()  # Deduplication of message IDs
        self.rate_limits: Dict[str, Dict[str, Any]] = {}  # API rate limit information
        self.last_update: float = time.time()

    def add_message(self, message: Message):
        """Add a message to the world state"""
        channel_id = message.channel_id

        # Deduplicate across channels
        if message.id in self.seen_messages:
            logger.debug(f"Deduplicated message {message.id}")
            return
        self.seen_messages.add(message.id)
        # Create channel if it doesn't exist
        if channel_id not in self.channels:
            self.channels[channel_id] = Channel(
                id=channel_id,
                type=message.channel_type,
                name=f"{message.channel_type}_{channel_id}",
                recent_messages=[],
                last_checked=time.time(),
            )

        # Add message to channel
        self.channels[channel_id].recent_messages.append(message)
        # Thread management: group Farcaster messages by root cast
        if message.channel_type == "farcaster":
            thread_id = message.reply_to or message.id
            self.threads.setdefault(thread_id, []).append(message)

        # Keep only last 50 messages per channel
        if len(self.channels[channel_id].recent_messages) > 50:
            self.channels[channel_id].recent_messages = self.channels[
                channel_id
            ].recent_messages[-50:]

        self.last_update = time.time()
        logger.info(f"Added message from {message.sender} to {channel_id}")

    def add_action_history(self, action_data: Dict[str, Any]):
        """Add completed action to history"""
        action = ActionHistory(
            action_type=action_data["action_type"],
            parameters=action_data["parameters"],
            result=action_data["result"],
            timestamp=action_data["timestamp"],
        )

        self.action_history.append(action)

        # Keep only last 100 actions
        if len(self.action_history) > 100:
            self.action_history = self.action_history[-100:]

        self.last_update = time.time()
        logger.info(f"Added action history: {action.action_type}")

    def update_system_status(self, updates: Dict[str, Any]):
        """Update system status information"""
        self.system_status.update(updates)
        self.last_update = time.time()
        logger.info(f"Updated system status: {list(updates.keys())}")

    def get_all_messages(self) -> List[Message]:
        """Get all messages from all channels"""
        all_messages = []
        for channel in self.channels.values():
            all_messages.extend(channel.recent_messages)
        return sorted(all_messages, key=lambda x: x.timestamp or 0)

    def to_json(self) -> str:
        """Convert world state to JSON for AI consumption"""
        import json

        return json.dumps(self.to_dict(), indent=2, default=str)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "channels": {
                id: {
                    "id": ch.id,
                    "type": ch.type,
                    "name": ch.name,
                    "recent_messages": [asdict(msg) for msg in ch.recent_messages],
                    "last_checked": ch.last_checked,
                }
                for id, ch in self.channels.items()
            },
            "action_history": [asdict(action) for action in self.action_history],
            "system_status": self.system_status,
            "last_update": self.last_update,
            "threads": {
                thread_id: [asdict(msg) for msg in msgs]
                for thread_id, msgs in self.threads.items()
            },
        }

    def get_recent_activity(self, lookback_seconds: int = 300) -> Dict[str, Any]:
        """Get recent activity summary for the AI"""
        cutoff_time = time.time() - lookback_seconds

        recent_messages = []
        for channel in self.channels.values():
            for msg in channel.recent_messages:
                if msg.timestamp > cutoff_time:
                    recent_messages.append(msg)

        recent_actions = [
            action for action in self.action_history if action.timestamp > cutoff_time
        ]

        # Sort by timestamp
        recent_messages.sort(key=lambda x: x.timestamp or 0)
        recent_actions.sort(key=lambda x: x.timestamp or 0)

        return {
            "recent_messages": [asdict(msg) for msg in recent_messages],
            "recent_actions": [asdict(action) for action in recent_actions],
            "channels": {
                id: {
                    "name": ch.name,
                    "type": ch.type,
                    "message_count": len(ch.recent_messages),
                }
                for id, ch in self.channels.items()
            },
            "system_status": self.system_status,
            "current_time": time.time(),
            "lookback_seconds": lookback_seconds,
        }

    def to_dict_for_ai(
        self,
        primary_channel_id: Optional[str] = None,
        max_messages_per_channel: int = 10,
        max_action_history: int = 5,
        max_thread_messages: int = 5,
        max_other_channels: int = 3,
        message_snippet_length: int = 75,
        include_detailed_user_info: bool = True,
        bot_fid: Optional[str] = None,
        bot_username: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Convert world state to optimized dictionary for AI consumption.
        Focuses on primary_channel_id with detailed info, summarizes others.
        """
        from ..config import settings

        # Sort channels by activity (most recent message first)
        # Give special priority to Farcaster channels to ensure minimum visibility
        sorted_channels = sorted(
            self.channels.items(),
            key=lambda x: (
                # Primary sort: Farcaster channels get priority boost
                0 if x[1].type == "farcaster" else 1,
                # Secondary sort: Most recent activity first
                -(x[1].recent_messages[-1].timestamp if x[1].recent_messages else 0),
            ),
        )

        channels_payload = {}
        detailed_count = 0

        for ch_id, ch_data in sorted_channels:
            # Filter out bot's own messages
            filtered_messages = [
                msg
                for msg in ch_data.recent_messages
                if not msg.is_from_bot(bot_fid, bot_username)
            ]

            # Decide if this channel gets detailed treatment
            is_primary = ch_id == primary_channel_id
            # Always include key Farcaster channels for minimum visibility
            is_key_farcaster = ch_data.type == "farcaster" and (
                "home" in ch_id or "notification" in ch_id or "reply" in ch_id
            )
            include_detailed = (
                is_primary or is_key_farcaster or detailed_count < max_other_channels
            )

            if include_detailed and filtered_messages:
                # Full detail for priority channels
                messages_for_payload = [
                    msg.to_ai_summary_dict()
                    if not include_detailed_user_info
                    else asdict(msg)
                    for msg in filtered_messages[-max_messages_per_channel:]
                ]

                # Calculate timestamp range for the included messages
                truncated_messages = filtered_messages[-max_messages_per_channel:]
                timestamp_range = None
                if truncated_messages:
                    timestamp_range = {
                        "start": truncated_messages[0].timestamp,
                        "end": truncated_messages[-1].timestamp,
                        "span_hours": round(
                            (
                                truncated_messages[-1].timestamp
                                - truncated_messages[0].timestamp
                            )
                            / 3600,
                            2,
                        ),
                        "total_available_messages": len(filtered_messages),
                        "included_messages": len(truncated_messages),
                    }

                channels_payload[ch_id] = {
                    "id": ch_data.id,
                    "type": ch_data.type,
                    "name": ch_data.name,
                    "recent_messages": messages_for_payload,
                    "last_checked": ch_data.last_checked,
                    "topic": ch_data.topic[:100] if ch_data.topic else None,
                    "member_count": ch_data.member_count,
                    "activity_summary": ch_data.get_activity_summary(),
                    "priority": "detailed" if is_primary else "secondary",
                    "message_timestamp_range": timestamp_range,
                }
                # Only count towards detailed limit if it's not primary or key Farcaster
                if not is_primary and not is_key_farcaster:
                    detailed_count += 1
            else:
                # Summary only for less active channels
                channels_payload[ch_id] = {
                    "id": ch_data.id,
                    "type": ch_data.type,
                    "name": ch_data.name,
                    "activity_summary": ch_data.get_activity_summary(),
                    "priority": "summary_only",
                }

        # Truncate action history, excluding bot's own actions
        filtered_actions = [
            action
            for action in self.action_history
            if not (
                hasattr(action, "parameters")
                and action.parameters.get("sender")
                in [bot_username, settings.MATRIX_USER_ID]
            )
        ]

        action_history_payload = [
            asdict(action) for action in filtered_actions[-max_action_history:]
        ]

        # Handle threads with bot filtering - only include threads relevant to primary channel
        threads_payload = {}
        if primary_channel_id:
            # Look for threads that might be related to the primary channel
            for thread_id, msgs in self.threads.items():
                # Include thread if any message belongs to primary channel or references it
                relevant_thread = any(
                    msg.channel_id == primary_channel_id
                    or msg.reply_to
                    in [
                        m.id
                        for m in self.channels.get(
                            primary_channel_id, Channel("", "", "", [], 0)
                        ).recent_messages
                    ]
                    for msg in msgs
                )

                if relevant_thread:
                    filtered_thread_msgs = [
                        msg
                        for msg in msgs[-max_thread_messages:]
                        if not msg.is_from_bot(bot_fid, bot_username)
                    ]

                    if filtered_thread_msgs:
                        thread_msgs_for_payload = [
                            msg.to_ai_summary_dict()
                            if not include_detailed_user_info
                            else asdict(msg)
                            for msg in filtered_thread_msgs
                        ]
                        threads_payload[thread_id] = thread_msgs_for_payload

        return {
            "current_processing_channel_id": primary_channel_id,
            "channels": channels_payload,
            "action_history": action_history_payload,
            "system_status": self.system_status,
            "threads": threads_payload,
            "current_time": time.time(),
            "payload_stats": {
                "primary_channel": primary_channel_id,
                "detailed_channels": detailed_count
                + (1 if primary_channel_id in channels_payload else 0),
                "summary_channels": len(sorted_channels)
                - detailed_count
                - (1 if primary_channel_id in channels_payload else 0),
                "total_channels": len(sorted_channels),
                "filtered_messages": sum(
                    len(ch.get("recent_messages", []))
                    for ch in channels_payload.values()
                    if "recent_messages" in ch
                ),
                "bot_identity": {"fid": bot_fid, "username": bot_username},
            },
        }


class WorldStateManager:
    """Manages the world state and provides updates"""

    def __init__(self):
        self.state = WorldState()
        # Deduplication and thread roots initialization
        self.state.seen_messages = set()
        # thread_roots is initialized in WorldState
        # Initialize thread storage for conversation threads
        self.state.threads = {}

        # Initialize system status
        self.state.system_status = {
            "matrix_connected": False,
            "farcaster_connected": False,
            "last_observation_cycle": 0,
            "total_cycles": 0,
        }
        logger.info("WorldStateManager: Initialized empty world state")

    def add_channel(self, channel_id: str, channel_type: str, name: str):
        """Add a new channel to monitor"""
        self.state.channels[channel_id] = Channel(
            id=channel_id,
            type=channel_type,
            name=name,
            recent_messages=[],
            last_checked=time.time(),
        )
        logger.info(f"WorldState: Added {channel_type} channel '{name}' ({channel_id})")

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

    def add_action_result(
        self, action_type: str, parameters: Dict[str, Any], result: str, action_id: Optional[str] = None
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

        logger.info(f"WorldState: Action completed - {action_type}: {result} (ID: {action_id})")
        return action_id

    def update_action_result(self, action_id: str, new_result: str, cast_hash: Optional[str] = None) -> bool:
        """Update the result of an existing action by ID. Returns True if found and updated."""
        for action in self.state.action_history:
            if action.action_id == action_id:
                old_result = action.result
                action.result = new_result
                action.timestamp = time.time()  # Update timestamp to reflect completion time
                
                # If this is a Farcaster action and we have a cast hash, add it to parameters
                if cast_hash and action.action_type.startswith("send_farcaster"):
                    action.parameters["cast_hash"] = cast_hash
                
                self.state.last_update = time.time()
                logger.info(f"WorldState: Action {action_id} updated - {action.action_type}: {old_result} -> {new_result}")
                return True
        
        logger.warning(f"WorldState: Could not find action with ID {action_id} to update")
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
            thread_id: [asdict(msg) for msg in msgs]
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

    def get_ai_optimized_payload(
        self, primary_channel_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get an optimized world state payload for AI decision making.
        Uses configuration from settings for all truncation parameters.
        """
        from ..config import settings

        return self.state.to_dict_for_ai(
            primary_channel_id=primary_channel_id,
            max_messages_per_channel=settings.AI_CONVERSATION_HISTORY_LENGTH,
            max_action_history=settings.AI_ACTION_HISTORY_LENGTH,
            max_thread_messages=settings.AI_THREAD_HISTORY_LENGTH,
            max_other_channels=settings.AI_OTHER_CHANNELS_SUMMARY_COUNT,
            message_snippet_length=settings.AI_OTHER_CHANNELS_MESSAGE_SNIPPET_LENGTH,
            include_detailed_user_info=settings.AI_INCLUDE_DETAILED_USER_INFO,
            bot_fid=settings.FARCASTER_BOT_FID,
            bot_username=settings.FARCASTER_BOT_USERNAME,
        )

    def get_channel(self, channel_id: str) -> Optional[Channel]:
        """Get a channel by ID"""
        return self.state.channels.get(channel_id)
