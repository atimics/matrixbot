#!/usr/bin/env python3
"""
World State Data Structures

This module defines the core data structures for the world state management system:
- Message: Unified message representation across platforms
- Channel: Communication channel/room with activity tracking
- ActionHistory: Audit trail of bot actions
- WorldStateData: Central data container (renamed from WorldState class)
- SentimentData: User sentiment tracking
- MemoryEntry: User memory bank entries
- FarcasterUserDetails: Enhanced user information with caching
- MatrixUserDetails: Enhanced Matrix user information
"""

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import logging

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
    channel_type: str  # 'matrix' or 'farcaster'
    sender: str  # Display name for Matrix, username for Farcaster
    content: str
    timestamp: float
    channel_id: Optional[str] = None  # Channel/room identifier where the message was posted
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

    # URL validation results
    validated_urls: Optional[List[Dict[str, Any]]] = field(
        default_factory=list
    )  # [{"url": "...", "status": "valid/invalid/error", "http_status_code": 200, "content_type": "text/html"}, ...]

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
        channel_type: Alias for type (backward compatibility)
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
        update_last_checked(): Updates the last_checked timestamp
        __post_init__(): Performs post-initialization validation and setup
    """

    id: str  # Room ID for Matrix, channel ID for Farcaster
    name: str  # Display name
    type: Optional[str] = None  # 'matrix' or 'farcaster'
    channel_type: Optional[str] = None  # Alias for type (backward compatibility)
    recent_messages: List[Message] = field(default_factory=list)
    last_checked: Optional[float] = None

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
    status: str = "active"  # Status: 'active', 'left_by_bot', 'kicked', 'banned', 'invited'
    last_status_update: float = 0.0  # When status was last updated

    def __post_init__(self):
        """
        Perform post-initialization validation and setup.

        This method handles backward compatibility and ensures consistency between
        type and channel_type attributes.
        """
        # Handle backward compatibility between type and channel_type
        if self.channel_type and not self.type:
            self.type = self.channel_type
        elif self.type and not self.channel_type:
            self.channel_type = self.type
        elif self.type and self.channel_type and self.type != self.channel_type:
            # If both are set but different, prefer type and update channel_type
            self.channel_type = self.type
            
        # Set default last_status_update if not provided
        if self.last_status_update == 0.0:
            self.last_status_update = time.time()
    
    def update_last_checked(self, timestamp: Optional[float] = None):
        """Update the last_checked timestamp"""
        self.last_checked = timestamp if timestamp is not None else time.time()
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
    metadata: Dict[str, Any] = field(default_factory=dict)
    action_id: Optional[str] = None  # Unique ID for tracking/updating scheduled actions


@dataclass
class SentimentData:
    """
    Tracks user sentiment based on their interactions.
    
    Attributes:
        score: Sentiment score from -1.0 (very negative) to 1.0 (very positive)
        label: Human-readable sentiment label (positive, negative, neutral)
        last_updated: Unix timestamp of last sentiment update
        confidence: Optional confidence score for the sentiment analysis
        history: List of recent sentiment scores for trending analysis
    """
    score: float  # -1.0 to 1.0
    label: str    # "positive", "negative", "neutral"
    last_updated: float
    confidence: Optional[float] = None
    history: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class MemoryEntry:
    """
    Represents a specific memory or observation about a user.
    
    Attributes:
        user_platform_id: Platform-specific user identifier (e.g., "matrix:@user:server.com", "farcaster:fid:123")
        timestamp: Unix timestamp when this memory was created
        content: The core text content of the memory
        memory_id: Unique identifier for this memory entry
        source_message_id: Optional ID of the message this memory relates to
        source_cast_hash: Optional Farcaster cast hash this memory relates to
        related_entities: List of related users, topics, or entities
        memory_type: Type of memory (observation, preference, fact, etc.)
        importance: Importance score from 0.0 to 1.0
        ai_summary: Optional AI-generated summary of this memory
    """
    user_platform_id: str
    timestamp: float
    content: str
    memory_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_message_id: Optional[str] = None
    source_cast_hash: Optional[str] = None
    related_entities: List[str] = field(default_factory=list)
    memory_type: str = "observation"  # observation, preference, fact, important_interaction
    importance: float = 0.5  # 0.0 to 1.0
    ai_summary: Optional[str] = None


@dataclass
class FarcasterUserDetails:
    """
    Enhanced Farcaster user information with caching capabilities.
    
    Attributes:
        fid: Farcaster ID number
        username: Farcaster username
        display_name: Display name
        bio: User biography
        follower_count: Number of followers
        following_count: Number of following
        pfp_url: Profile picture URL
        power_badge: Whether user has power badge
        timeline_cache: Cached recent casts from user's timeline
        last_timeline_fetch: Timestamp of last timeline fetch
        sentiment: Current sentiment analysis for this user
        memory_entries: List of memory entries for this user
    """
    fid: str
    username: Optional[str] = None
    display_name: Optional[str] = None
    bio: Optional[str] = None
    follower_count: Optional[int] = None
    following_count: Optional[int] = None
    pfp_url: Optional[str] = None
    power_badge: bool = False
    timeline_cache: Optional[Dict[str, Any]] = None  # Contains casts and metadata
    last_timeline_fetch: Optional[float] = None
    sentiment: Optional[SentimentData] = None
    memory_entries: List[MemoryEntry] = field(default_factory=list)


@dataclass
class MatrixUserDetails:
    """
    Enhanced Matrix user information.
    
    Attributes:
        user_id: Matrix user ID (@user:server.com)
        display_name: Display name
        avatar_url: Avatar URL
        sentiment: Current sentiment analysis for this user
        memory_entries: List of memory entries for this user
    """
    user_id: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    sentiment: Optional[SentimentData] = None
    memory_entries: List[MemoryEntry] = field(default_factory=list)


@dataclass
class TokenMetadata:
    """
    Comprehensive token metadata including market data and activity metrics.
    
    Attributes:
        contract_address: The token's contract address
        ticker: Token ticker symbol (e.g., 'ETH', 'USDC')
        name: Full token name
        description: Token description
        market_cap: Current market capitalization in USD
        price_usd: Current price in USD
        price_change_24h: 24-hour price change percentage
        volume_24h: 24-hour trading volume in USD
        total_supply: Total token supply
        circulating_supply: Circulating token supply
        holder_count: Total number of token holders
        top_holder_percentage: Percentage of supply held by top holder
        last_updated: Timestamp of last metadata update
        dex_info: DEX trading information (pools, liquidity, etc.)
        social_metrics: Social media activity metrics
    """
    contract_address: str
    ticker: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    market_cap: Optional[float] = None
    price_usd: Optional[float] = None
    price_change_24h: Optional[float] = None
    volume_24h: Optional[float] = None
    total_supply: Optional[float] = None
    circulating_supply: Optional[float] = None
    holder_count: Optional[int] = None
    top_holder_percentage: Optional[float] = None
    last_updated: Optional[float] = None
    dex_info: Dict[str, Any] = field(default_factory=dict)
    social_metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenHolderData:
    """
    Enhanced token holder information with balance and ranking data.
    
    Attributes:
        address: Wallet address of the holder
        balance: Token balance
        percentage_of_supply: Percentage of total supply held
        rank: Ranking among all holders (1 = largest holder)
        fid: Associated Farcaster ID (if available)
        last_transaction_timestamp: Timestamp of last token transaction
        is_whale: Whether this holder qualifies as a "whale"
        transaction_count: Number of token transactions
    """
    address: str
    balance: float
    percentage_of_supply: float
    rank: int
    fid: Optional[str] = None
    last_transaction_timestamp: Optional[float] = None
    is_whale: bool = False
    transaction_count: Optional[int] = None


@dataclass
class MonitoredTokenHolder:
    """
    Represents a monitored token holder with their Farcaster activity and token data.
    
    Attributes:
        fid: Farcaster ID of the holder
        username: Farcaster username
        display_name: Display name
        last_cast_seen_timestamp: Timestamp of the last cast seen from this holder
        recent_casts: List of recent messages from this holder
        token_holder_data: Enhanced token holding information
        social_influence_score: Calculated influence score based on followers/activity
        last_activity_timestamp: Timestamp of last Farcaster activity
    """
    fid: str
    username: Optional[str] = None
    display_name: Optional[str] = None
    last_cast_seen_timestamp: Optional[float] = None
    recent_casts: List[Message] = field(default_factory=list)
    token_holder_data: Optional[TokenHolderData] = None
    social_influence_score: Optional[float] = None
    last_activity_timestamp: Optional[float] = None


class WorldStateData:
    def add_action_history(self, action_data: dict):
        """Compatibility method for tests that call add_action_history on WorldStateData."""
        from .manager import ActionHistory
        action = ActionHistory(
            action_type=action_data.get("action_type", "unknown"),
            parameters=action_data.get("parameters", {}),
            result=action_data.get("result", ""),
            timestamp=action_data.get("timestamp", time.time()),
        )
        self.action_history.append(action)
        if len(self.action_history) > 100:
            self.action_history = self.action_history[-100:]
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
        # Aliases
        self.pending_invites = self.pending_matrix_invites
        # action_history already exists
        # Pending invites alias
        # pending_matrix_invites: List[Dict] already defined

        # Image library: Track AI-generated media for reuse and reference
        self.generated_media_library: List[Dict[str, Any]] = []

        # Ecosystem token tracking
        self.ecosystem_token_contract: Optional[str] = None
        # Enhanced token metadata tracking
        self.token_metadata: Optional[TokenMetadata] = None
        # Stores FIDs of top holders and their details + recent activity
        self.monitored_token_holders: Dict[str, MonitoredTokenHolder] = {}

        # Initialize timestamp tracking
        self.last_update = time.time()
        
        # Enhanced user tracking with sentiment and memory
        self.farcaster_users: Dict[str, FarcasterUserDetails] = {}  # fid -> user details
        self.matrix_users: Dict[str, MatrixUserDetails] = {}  # user_id -> user details
        self.user_memory_bank: Dict[str, List[MemoryEntry]] = {}  # user_platform_id -> memories
        
        # Tool result caching
        self.tool_cache: Dict[str, Dict[str, Any]] = {}  # cache_key -> cached result
        self.search_cache: Dict[str, Dict[str, Any]] = {}  # query_hash -> search results
        
        # Backward compatibility placeholders
        self.user_details: Dict[str, Any] = {}
        self.bot_media: Dict[str, Any] = {}  # alias for bot_media_on_farcaster

    def get_state_metrics(self) -> Dict[str, Any]:
        """
        Get metrics about the current state for payload size estimation.
        
        Returns:
            Dictionary with metrics about channels, messages, actions, etc.
        """
        total_messages = sum(len(ch.recent_messages) for ch in self.channels.values())
        
        return {
            "channel_count": len(self.channels),
            "total_messages": total_messages,
            "action_history_count": len(self.action_history),
            "thread_count": len(self.threads),
            "pending_invites": len(self.pending_matrix_invites),
            "media_library_size": len(self.generated_media_library),
            "last_update": self.last_update
        }
    # Backward-compatible methods for direct WorldState usage
    def add_channel(self, channel_id: str, channel_type: str, name: str, status: str = "active"):
        """Add a new channel to the world state."""
        ch = Channel(
            id=channel_id,
            type=channel_type,
            name=name,
            recent_messages=[],
            last_checked=time.time(),
            status=status,
            last_status_update=time.time(),
        )
        self.channels[channel_id] = ch
        self.last_update = time.time()

    def add_message(self, message):
        """Add a message to the world state, deduplicating and managing channel history. Accepts Message or dict."""
        from .structures import Message
        # Convert dict to Message if needed
        if isinstance(message, dict):
            message = Message(**message)
        # Deduplicate
        if message.id in self.seen_messages:
            return
        self.seen_messages.add(message.id)
        # Determine channel_id
        chan_id = message.channel_id or f"{message.channel_type}:unknown"
        # Auto-create channel if missing
        if chan_id not in self.channels:
            self.add_channel(chan_id, message.channel_type, chan_id)
        ch = self.channels[chan_id]
        ch.recent_messages.append(message)
        # Keep only last 50
        if len(ch.recent_messages) > 50:
            ch.recent_messages = ch.recent_messages[-50:]
        self.last_update = time.time()
        # Thread management
        if message.channel_type == "farcaster":
            thread_id = message.reply_to or message.id
            self.threads.setdefault(thread_id, []).append(message)

    def get_recent_messages(self, channel_id: str, limit: int = 10) -> List[Message]:
        """Get up to `limit` most recent messages for a channel."""
        ch = self.channels.get(channel_id)
        if not ch:
            return []
        return ch.recent_messages[-limit:]

    def has_replied_to_cast(self, cast_hash: str) -> bool:
        """Check if a Farcaster reply action exists for the given cast_hash."""
        for action in self.action_history:
            if action.action_type == "send_farcaster_reply" and action.result not in ["scheduled", "failure"]:
                # support multiple parameter keys
                params = action.parameters or {}
                if cast_hash in params.values():
                    return True
        return False

    def set_rate_limits(self, key: str, limits: Dict[str, Any]):
        """Set rate limit info for a service."""
        self.rate_limits[key] = limits

    def get_rate_limits(self, key: str) -> Optional[Dict[str, Any]]:
        """Get rate limit info for a service."""
        return self.rate_limits.get(key)

    def add_pending_invite(self, invite_info: Dict[str, Any]):
        """Add a pending Matrix invite."""
        # Use pending_matrix_invites list
        room = invite_info.get("room_id")
        if room:
            self.pending_matrix_invites.append(invite_info)
            self.last_update = time.time()

    def remove_pending_invite(self, room_id: str) -> bool:
        """Remove a pending Matrix invite by room_id."""
        original = len(self.pending_matrix_invites)
        self.pending_matrix_invites = [inv for inv in self.pending_matrix_invites if inv.get("room_id") != room_id]
        removed = len(self.pending_matrix_invites) < original
        if removed:
            self.last_update = time.time()
        return removed

    def track_bot_media(self, cast_hash: str, media_info: Dict[str, Any]):
        """Record tracking info for bot media engagement."""
        self.bot_media_on_farcaster[cast_hash] = media_info
        # Maintain alias
        self.bot_media = self.bot_media_on_farcaster
        self.last_update = time.time()

    def add_action(self, action: ActionHistory):
        """Add an action to history with a default limit of 10 entries."""
        self.action_history.append(action)
        # Keep only last 10
        if len(self.action_history) > 10:
            self.action_history = self.action_history[-10:]
        self.last_update = time.time()

    def to_dict_for_ai(self, include_channels: List[str] = None, max_messages_per_channel: int = None, message_limit_per_channel: int = None, max_actions: int = None) -> Dict[str, Any]:
        """Convert world state to AI-friendly dict with optional limits."""
        data: Dict[str, Any] = {}
        # Channels
        data["channels"] = {}
        # Determine message limit
        limit = message_limit_per_channel or max_messages_per_channel
        for cid, ch in self.channels.items():
            if include_channels and cid not in include_channels:
                continue
            msgs = ch.recent_messages
            if limit is not None:
                msgs = msgs[-limit:]
            data["channels"][cid] = {
                "recent_messages": [asdict(msg) for msg in msgs]
            }
        # Action history
        actions = self.action_history
        if max_actions is not None:
            actions = actions[-max_actions:]
        data["action_history"] = [asdict(act) for act in actions]
        # Recent media actions
        data["recent_media_actions"] = self.get_recent_media_actions()
        return data

    def get_observation_data(self) -> Dict[str, Any]:
        """Alias for to_dict, for backward compatibility with direct world state use."""
        return self.to_dict()

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
            "rate_limits": self.rate_limits,
            "pending_invites": self.pending_matrix_invites,
            "recent_activity": self.get_recent_activity(),
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
                    "recent_messages": [asdict(msg) for msg in ch.recent_messages],
                }
                for id, ch in self.channels.items()
            },
            "system_status": self.system_status,
            "current_time": time.time(),
            "lookback_seconds": lookback_seconds,
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
