#!/usr/bin/env python3
"""
World State Management System

This module implements a sophisticated world state management system that maintains
comprehensive awareness of all platform activities, conversations, and bot interactions.
The world state serves as the central knowledge base for AI decision-making and provides
context-aware conversation management across multiple platforms.

Key Features:
- Multi-platform message and channel management (Matrix, Farcaster)
- Advanced message deduplication across channels and platforms
- Intelligent conversation thread tracking and context preservation
- Rich user profiling with social media metadata
- Comprehensive action history with deduplication
- Rate limiting integration and enforcement
- AI payload optimization for efficient token usage
- Real-time activity monitoring and analytics

Architecture:
- Message: Unified message model supporting platform-specific metadata
- Channel: Comprehensive channel/room representation with activity tracking
- ActionHistory: Complete audit trail of bot actions and results
- WorldState: Central state container with intelligent organization
- WorldStateManager: High-level interface for state manipulation and querying

The system is designed for high performance with automatic cleanup, memory management,
and optimized data structures for fast access and minimal resource usage.
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
    """
    Represents a unified message from any supported platform with comprehensive metadata.

    This class provides a standardized interface for messages across Matrix and Farcaster
    platforms while preserving platform-specific information in a structured way.

    Attributes:
        id: Unique message identifier (event_id for Matrix, cast hash for Farcaster)
        channel_id: Channel/room identifier where the message was posted
        channel_type: Platform type ('matrix' or 'farcaster')
        sender: Display name (Matrix) or username (Farcaster) of the message author
        content: The text content of the message
        timestamp: Unix timestamp when the message was created
        reply_to: Optional ID of the message this is replying to

    Enhanced Social Media Attributes:
        sender_username: Platform-specific username for tagging (@username)
        sender_display_name: Human-readable display name
        sender_fid: Farcaster ID number for user identification
        sender_pfp_url: Profile picture URL for rich display
        sender_bio: User biography/description text
        sender_follower_count: Number of followers (social influence metric)
        sender_following_count: Number of accounts the user follows

    Platform Metadata:
        metadata: Dictionary containing additional platform-specific data such as:
                 - power_badge: Whether user has verification/power badge
                 - is_bot: Whether the sender is identified as a bot
                 - cast_type: Type of Farcaster cast (cast, recast, etc.)
                 - encryption_info: Matrix encryption details
                 - edit_history: Message edit tracking

    Methods:
        to_ai_summary_dict(): Returns optimized version for AI consumption
        is_from_bot(): Checks if message originated from the bot itself
    """

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

    # Image URLs found in the message
    image_urls: Optional[List[str]] = field(default_factory=list)

    # v0.0.3: Media attachments and archival tracking
    s3_media_attachments: Optional[List[Dict[str, str]]] = field(
        default_factory=list
    )  # [{"type": "image", "s3_url": "..."}, ...]
    archived_media_tx_ids: Optional[List[str]] = field(
        default_factory=list
    )  # List of Arweave TXIDs if media archived

    def to_ai_summary_dict(self) -> Dict[str, Any]:
        """
        Return a summarized version of the message optimized for AI consumption.

        This method reduces token usage by truncating long content and focusing on
        the most relevant metadata for AI decision-making. It preserves essential
        context while removing verbose or unnecessary details.

        Returns:
            Dictionary with key message information optimized for AI prompts:
            - Truncated content (250 chars max)
            - Essential user identification
            - Key social signals (follower count, verification status)
            - Platform-specific flags (bot status, power badges)
        """
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
            "image_urls": self.image_urls if self.image_urls else [],
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
        """
        Check if this message is from the bot itself.

        This method supports multiple identification strategies to handle different
        platform identity mechanisms and edge cases in user identification.

        Args:
            bot_fid: Bot's Farcaster ID for precise identification
            bot_username: Bot's username for fallback identification

        Returns:
            True if the message originated from the bot, False otherwise

        Note:
            Uses multiple matching strategies to handle platform differences
            and ensure reliable bot message detection for conversation context.
        """
        if bot_fid and str(self.sender_fid) == str(bot_fid):
            return True
        if bot_username and (
            self.sender_username == bot_username or self.sender == bot_username
        ):
            return True
        return False


@dataclass
class Channel:
    """
    Represents a communication channel with comprehensive metadata and activity tracking.

    This class provides a unified interface for channels/rooms across different platforms
    while maintaining platform-specific details and providing intelligent activity analysis.

    Attributes:
        id: Unique channel identifier (room ID for Matrix, channel ID for Farcaster)
        type: Platform type ('matrix' or 'farcaster')
        name: Human-readable channel name or title
        recent_messages: List of recent Message objects with automatic size management
        last_checked: Unix timestamp of last observation cycle

    Matrix-Specific Attributes:
        canonical_alias: Primary room alias (#room:server.com)
        alt_aliases: List of alternative room aliases
        topic: Room topic/description text
        avatar_url: Room avatar image URL
        member_count: Current number of room members
        encrypted: Whether the room uses end-to-end encryption
        public: Whether the room is publicly joinable
        power_levels: Dictionary mapping user IDs to power levels
        creation_time: Unix timestamp when the room was created

    Methods:
        get_activity_summary(): Provides comprehensive activity analysis
        __post_init__(): Performs post-initialization validation and setup
    """

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

    # Channel status tracking
    status: str = (
        "active"  # Status: 'active', 'left_by_bot', 'kicked', 'banned', 'invited'
    )
    last_status_update: float = 0.0  # When status was last updated

    def __post_init__(self):
        """
        Perform post-initialization validation and setup.

        This method can be extended to add validation logic, default value
        assignment, or other initialization tasks that require the full object state.
        """
        # Initialize status timestamp if not set
        if self.last_status_update == 0.0:
            self.last_status_update = time.time()

    def get_activity_summary(self) -> Dict[str, Any]:
        """
        Generate a comprehensive summary of recent channel activity.

        This method provides detailed analytics about channel engagement, user activity,
        and temporal patterns that can inform AI decision-making about channel priority
        and engagement strategies.

        Returns:
            Dictionary containing:
            - message_count: Total number of recent messages
            - last_activity: Timestamp of most recent message
            - last_message: Preview of the most recent message content
            - last_sender: Username of the most recent message author
            - active_users: List of recently active usernames (top 5)
            - summary: Human-readable activity summary
            - timestamp_range: Detailed temporal analysis including:
                - start: Timestamp of oldest tracked message
                - end: Timestamp of newest tracked message
                - span_hours: Duration of activity period in hours
        """
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
    """
    Represents a completed or scheduled action with comprehensive tracking.

    This class maintains a complete audit trail of bot actions, enabling deduplication,
    performance monitoring, and intelligent decision-making about future actions.

    Attributes:
        action_type: Type of action performed (e.g., 'send_farcaster_reply', 'like_farcaster_post')
        parameters: Dictionary of parameters used for the action execution
        result: Result or status of the action ('success', 'failure', 'scheduled', etc.)
        timestamp: Unix timestamp when the action was completed or updated
        action_id: Unique identifier for tracking and updating scheduled actions

    Usage:
        - Deduplication: Prevents duplicate likes, follows, and replies
        - Performance Monitoring: Tracks success rates and execution times
        - State Consistency: Ensures actions are properly recorded and updated
        - AI Context: Provides historical context for future decision-making
    """

    action_type: str
    parameters: Dict[str, Any]
    result: str
    timestamp: float
    action_id: Optional[str] = None  # Unique ID for tracking/updating scheduled actions


class WorldState:
    """
    The complete observable state of the world with advanced management capabilities.

    This class serves as the central knowledge base for the AI system, maintaining
    comprehensive awareness of all platform activities, conversations, and bot interactions.
    It provides intelligent organization, deduplication, and optimization features for
    efficient AI decision-making.

    Core Components:
        - channels: Dictionary mapping channel IDs to Channel objects
        - action_history: Chronological list of completed actions
        - system_status: Current system health and connection status
        - threads: Conversation thread tracking for platforms supporting threading
        - seen_messages: Set for cross-platform message deduplication
        - rate_limits: API rate limiting information and enforcement data
        - pending_matrix_invites: Matrix room invitations awaiting response

    Key Features:
        - Automatic message deduplication across all platforms
        - Intelligent conversation thread management
        - AI payload optimization for efficient token usage
        - Comprehensive action tracking with deduplication
        - Real-time activity monitoring and analytics
        - Memory management with automatic cleanup

    Performance Optimizations:
        - Message rotation to prevent memory bloat (50 messages per channel)
        - Action history limits (100 actions maximum)
        - Smart filtering for AI payloads
        - Efficient data structures for fast access
    """

    def __init__(self):
        """
        Initialize empty world state with optimized data structures.

        Sets up all necessary containers and tracking mechanisms for efficient
        operation across multiple platforms and conversation contexts.
        """
        self.channels: Dict[str, Channel] = {}
        self.action_history: List[ActionHistory] = []
        self.system_status: Dict[str, Any] = {}
        self.threads: Dict[
            str, List[Message]
        ] = {}  # Map root cast id to thread messages
        self.thread_roots: Dict[str, Message] = {}  # Root message for each thread
        self.seen_messages: set[str] = set()  # Deduplication of message IDs

        # Rate limiting and API management
        self.rate_limits: Dict[str, Any] = {}  # API rate limiting information

        # Matrix room management
        self.pending_matrix_invites: List[
            Dict[str, Any]
        ] = []  # Pending Matrix invitations

        # v0.0.3: Bot media tracking for Farcaster engagement-based archival
        self.bot_media_on_farcaster: Dict[
            str, Dict[str, Any]
        ] = {}  # cast_hash -> media_info

        # Image library: Track AI-generated media for reuse and reference
        self.generated_media_library: List[Dict[str, Any]] = []

        # Initialize timestamp tracking
        self.last_update = time.time()

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
            # Include all messages including bot's own for AI context
            # The AI needs to see its own recent messages to maintain conversational flow
            # and understand the current state of conversations
            all_messages = ch_data.recent_messages

            # Decide if this channel gets detailed treatment
            is_primary = ch_id == primary_channel_id
            # Always include key Farcaster channels for minimum visibility
            is_key_farcaster = ch_data.type == "farcaster" and (
                "home" in ch_id or "notification" in ch_id or "reply" in ch_id
            )
            include_detailed = (
                is_primary or is_key_farcaster or detailed_count < max_other_channels
            )

            if include_detailed and all_messages:
                # Full detail for priority channels
                messages_for_payload = [
                    msg.to_ai_summary_dict()
                    if not include_detailed_user_info
                    else asdict(msg)
                    for msg in all_messages[-max_messages_per_channel:]
                ]

                # Calculate timestamp range for the included messages
                truncated_messages = all_messages[-max_messages_per_channel:]
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
                        "total_available_messages": len(all_messages),
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

        # Include all action history for AI context - the AI should see its own past actions
        # This provides better context for decision-making and prevents repetitive actions
        # If specific action types need filtering, it should be done more explicitly
        action_history_payload = [
            asdict(action) for action in self.action_history[-max_action_history:]
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
                    # Include all thread messages including bot's own for conversation context
                    all_thread_msgs = msgs[-max_thread_messages:]

                    if all_thread_msgs:
                        thread_msgs_for_payload = [
                            msg.to_ai_summary_dict()
                            if not include_detailed_user_info
                            else asdict(msg)
                            for msg in all_thread_msgs
                        ]
                        threads_payload[thread_id] = thread_msgs_for_payload

        return {
            "current_processing_channel_id": primary_channel_id,
            "channels": channels_payload,
            "action_history": action_history_payload,
            "system_status": {**self.system_status, "rate_limits": self.rate_limits},
            "threads": threads_payload,
            "pending_matrix_invites": self.pending_matrix_invites,
            "recent_media_actions": self.get_recent_media_actions(),
            "generated_media_library": self.generated_media_library[-20:],  # Last 20 generated media items
            "current_time": time.time(),
            "payload_stats": {
                "primary_channel": primary_channel_id,
                "detailed_channels": detailed_count
                + (1 if primary_channel_id in channels_payload else 0),
                "summary_channels": len(sorted_channels)
                - detailed_count
                - (1 if primary_channel_id in channels_payload else 0),
                "total_channels": len(sorted_channels),
                "included_messages": sum(
                    len(ch.get("recent_messages", []))
                    for ch in channels_payload.values()
                    if "recent_messages" in ch
                ),
                "bot_identity": {"fid": bot_fid, "username": bot_username},
                "pending_invites_count": len(self.pending_matrix_invites),
            },
        }

    def get_recent_media_actions(self, lookback_seconds: int = 300) -> Dict[str, Any]:
        """Get recent media-related actions to help avoid repetitive operations."""
        cutoff_time = time.time() - lookback_seconds

        recent_media_actions = []
        image_urls_recently_described = set()
        recent_generations = []

        for action in reversed(self.action_history):
            if action.timestamp < cutoff_time:
                break

            if action.action_type == "describe_image":
                if hasattr(action, "metadata") and action.metadata:
                    image_url = action.metadata.get("image_url")
                    if image_url:
                        image_urls_recently_described.add(image_url)
                elif hasattr(action, "parameters") and action.parameters:
                    image_url = action.parameters.get("image_url")
                    if image_url:
                        image_urls_recently_described.add(image_url)
                recent_media_actions.append(
                    {
                        "action": "describe_image",
                        "timestamp": action.timestamp,
                        "image_url": action.parameters.get("image_url")
                        if hasattr(action, "parameters")
                        else None,
                    }
                )

            elif action.action_type == "generate_image":
                recent_generations.append(
                    {
                        "action": "generate_image",
                        "timestamp": action.timestamp,
                        "prompt": action.parameters.get("prompt")
                        if hasattr(action, "parameters")
                        else None,
                        "result_url": action.result if hasattr(action, "result") else None,
                    }
                )
                recent_media_actions.append(recent_generations[-1])

        return {
            "recent_media_actions": recent_media_actions[-10:],  # Last 10 media actions
            "images_recently_described": list(image_urls_recently_described),
            "recent_generations": recent_generations[-5:],  # Last 5 generations
            "summary": {
                "total_recent_media_actions": len(recent_media_actions),
                "unique_images_described": len(image_urls_recently_described),
                "recent_generation_count": len(recent_generations),
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

    def get_state_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive metrics about the current world state.

        This method provides statistics that can be used for payload size estimation,
        monitoring, and optimization decisions.

        Returns:
            Dict containing various metrics about the world state
        """
        try:
            metrics = {
                # Channel metrics
                "total_channels": len(self.state.channels),
                "active_channels": len([
                    ch for ch in self.state.channels.values() 
                    if ch.recent_messages and time.time() - ch.last_activity < 3600
                ]),
                
                # Message metrics
                "total_messages": sum(len(ch.recent_messages) for ch in self.state.channels.values()),
                "recent_messages": sum(
                    len([msg for msg in ch.recent_messages if time.time() - msg.timestamp < 3600])
                    for ch in self.state.channels.values()
                ),
                
                # User metrics
                "total_users": len(self.state.users),
                "users_with_profiles": len([
                    user for user in self.state.users.values() 
                    if user.platform_data
                ]),
                
                # Action metrics
                "total_actions": len(self.state.action_history),
                "recent_actions": len([
                    action for action in self.state.action_history
                    if time.time() - action.timestamp < 3600
                ]),
                
                # Platform-specific metrics
                "matrix_channels": len([
                    ch for ch in self.state.channels.values()
                    if ch.platform == "matrix"
                ]),
                "farcaster_channels": len([
                    ch for ch in self.state.channels.values()
                    if ch.platform == "farcaster"
                ]),
                
                # Media metrics
                "bot_media_count": len(self.state.bot_media_on_farcaster),
                "archived_media_count": len([
                    media for media in self.state.bot_media_on_farcaster.values()
                    if media.get("arweave_tx_id")
                ]),
                
                # System metrics
                "rate_limit_data_size": len(self.state.rate_limits),
                "system_status_keys": len(self.state.system_status),
                
                # Timing metrics
                "last_update": time.time(),
                "oldest_message": min(
                    (msg.timestamp for ch in self.state.channels.values() for msg in ch.recent_messages),
                    default=time.time()
                ),
                "newest_message": max(
                    (msg.timestamp for ch in self.state.channels.values() for msg in ch.recent_messages),
                    default=0
                ),
            }
            
            # Add estimated data sizes (rough approximations)
            metrics["estimated_sizes"] = {
                "channels_kb": metrics["total_channels"] * 1.5,  # ~1.5KB per channel
                "messages_kb": metrics["total_messages"] * 0.8,  # ~0.8KB per message
                "users_kb": metrics["total_users"] * 0.3,       # ~0.3KB per user
                "actions_kb": metrics["total_actions"] * 0.5,   # ~0.5KB per action
                "total_estimated_kb": (
                    metrics["total_channels"] * 1.5 +
                    metrics["total_messages"] * 0.8 +
                    metrics["total_users"] * 0.3 +
                    metrics["total_actions"] * 0.5 + 5  # 5KB base overhead
                )
            }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error generating state metrics: {e}")
            return {
                "error": str(e),
                "total_channels": 0,
                "total_messages": 0,
                "total_users": 0,
                "total_actions": 0,
                "estimated_sizes": {"total_estimated_kb": 0}
            }
