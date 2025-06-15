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

    Neynar-specific Attributes:
        neynar_user_score: Optional reputation score indicating user quality (0.0 to 1.0)

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

    # Neynar-specific user quality signals
    neynar_user_score: Optional[float] = None  # Neynar user reputation score (0.0 to 1.0)

    # Platform-specific metadata
    metadata: Dict[str, Any] = field(
        default_factory=dict
    )  # Additional platform-specific data

    # Image URLs found in the message
    image_urls: Optional[List[str]] = field(default_factory=list)

    # v0.0.3: Media attachments and archival tracking
    arweave_media_attachments: Optional[List[Dict[str, str]]] = field(
        default_factory=list
    )  # [{"type": "image", "arweave_url": "..."}, ...]
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
            - Truncated content (2000 chars max for Matrix, 250 chars for others)
            - Essential user identification
            - Key social signals (follower count, verification status)
            - Platform-specific flags (bot status, power badges)
        """
        # Use different content limits based on platform type
        # Matrix messages need full content for proper AI response
        # Other platforms can use shorter truncation for token efficiency
        if self.channel_type == 'matrix':
            max_content_length = 2000
        else:
            max_content_length = 250
            
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "channel_type": self.channel_type,
            "sender_username": self.sender_username or self.sender,
            "content": self.content[:max_content_length] + "..."
            if len(self.content) > max_content_length
            else self.content,
            "timestamp": self.timestamp,
            "reply_to": self.reply_to,
            "sender_fid": self.sender_fid,
            "sender_follower_count": self.sender_follower_count,
            "neynar_user_score": self.neynar_user_score,
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
        verified_addresses: Dictionary mapping blockchain networks to wallet addresses
        ecosystem_token_balance_sol: Current balance of ecosystem token on Solana
        ecosystem_nft_count_base: Number of NFTs held from the collection on Base
        is_eligible_for_airdrop: Whether user meets airdrop criteria
        last_eligibility_check: Timestamp of last eligibility verification
        nft_interaction_history: List of NFT mints/claims by this user
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
    
    # NFT & Cross-chain data (v0.0.4)
    verified_addresses: Dict[str, List[str]] = field(default_factory=dict)  # e.g., {"solana": [...], "evm": [...]}
    ecosystem_token_balance_sol: float = 0.0
    ecosystem_nft_count_base: int = 0
    is_eligible_for_airdrop: bool = False
    last_eligibility_check: Optional[float] = None
    nft_interaction_history: List[Dict[str, Any]] = field(default_factory=list)  # Mint/claim history


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


@dataclass
class ResearchEntry:
    """
    Represents a research entry in the persistent knowledge base.
    
    This stores information gathered through web searches and user interactions
    to build an evolving knowledge base that improves the AI's reliability over time.
    
    Attributes:
        topic: Key topic or subject (normalized to lowercase for deduplication)
        summary: Concise summary of current knowledge about the topic
        key_facts: List of important facts or data points
        sources: List of sources where information was gathered
        confidence_level: Confidence in the information accuracy (1-10 scale)
        last_updated: Timestamp when this entry was last updated
        last_verified: Timestamp when information was last verified
        tags: List of tags for categorization and cross-referencing
        related_topics: List of related topic keys for knowledge graph connections
        verification_notes: Notes about information verification or concerns
    """
    topic: str
    summary: str
    key_facts: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    confidence_level: int = 5  # 1-10 scale, 5 is neutral
    last_updated: float = field(default_factory=time.time)
    last_verified: Optional[float] = None
    tags: List[str] = field(default_factory=list)
    related_topics: List[str] = field(default_factory=list)
    verification_notes: Optional[str] = None


@dataclass
class TargetRepositoryContext:
    """
    Comprehensive context for a target repository in the ACE system.
    
    This structure maintains all necessary information for the AI to work on
    improving a specific codebase, whether external or its own.
    """
    url: str = ""  # Main repository URL (e.g., "https://github.com/owner/repo")
    fork_url: Optional[str] = None  # AI's fork URL
    local_clone_path: Optional[str] = None  # Local workspace path
    current_branch: Optional[str] = None  # Current working branch
    active_task_id: Optional[str] = None  # Currently active development task
    open_issues_summary: List[Dict[str, Any]] = field(default_factory=list)  # GitHub issues
    open_prs_summary: List[Dict[str, Any]] = field(default_factory=list)  # GitHub PRs
    codebase_structure: Optional[Dict[str, Any]] = None  # File tree and analysis
    last_synced_with_upstream: Optional[float] = None
    setup_complete: bool = False  # Whether workspace is ready for development


@dataclass
class DevelopmentTask:
    """
    Represents a development task in the ACE system lifecycle.
    
    Tracks the complete evolution from identification through implementation
    and feedback, enabling the AI to learn from outcomes.
    """
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""  # Detailed task description from AI or human
    target_repository: str = ""  # Repository URL this task applies to
    target_files: List[str] = field(default_factory=list)  # Files to modify
    status: str = "proposed"  # proposed, feedback_pending, approved, implementation_in_progress, pr_submitted, merged, closed
    priority: int = 5  # 1-10
    
    # ACE Lifecycle tracking
    initial_proposal: Optional[str] = None  # AI's initial proposal text
    feedback_summary: Optional[str] = None  # Human feedback from Matrix/PR
    implementation_plan: Optional[str] = None  # Detailed plan for code changes
    associated_pr_url: Optional[str] = None  # GitHub PR URL
    pr_status: Optional[str] = None  # open, merged, closed
    
    # Learning and evaluation
    validation_results: Optional[str] = None  # Test results, error logs, etc.
    key_learnings: Optional[str] = None  # What the AI learned from this task
    performance_impact: Optional[str] = None  # Measurable impact if available
    
    # Metadata
    source_reference: Optional[str] = None  # Matrix room, log entry, etc. that triggered this
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


@dataclass
class ProjectTask:
    """
    Represents a project task for legacy compatibility with UpdateProjectPlan tool.
    
    This is a simpler variant of DevelopmentTask focused on project planning
    rather than the full ACE lifecycle.
    """
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    status: str = "todo"  # todo, in_progress, completed, blocked
    priority: int = 5  # 1-10, higher number = higher priority
    estimated_complexity: Optional[int] = None  # 1-10 complexity estimate
    related_code_files: List[str] = field(default_factory=list)  # Files this task affects
    source_references: List[str] = field(default_factory=list)  # Source docs, issues, etc.
    
    # Metadata
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


@dataclass
class NFTMetadata:
    """
    NFT metadata structure following OpenSea/ERC-721 standards.
    
    Attributes:
        name: The name of the NFT
        description: Description of the NFT
        image: URL to the image (S3 or Arweave)
        image_data: Optional base64 encoded image data
        external_url: Optional external URL for more info
        animation_url: Optional URL to multimedia content
        background_color: Optional background color
        youtube_url: Optional YouTube URL
        attributes: List of traits/attributes
        created_by: Creator information
        created_at: Creation timestamp
        metadata_uri: URI where this metadata is stored (Arweave/IPFS)
    """
    name: str
    description: str
    image: str
    image_data: Optional[str] = None
    external_url: Optional[str] = None
    animation_url: Optional[str] = None
    background_color: Optional[str] = None
    youtube_url: Optional[str] = None
    attributes: List[Dict[str, Any]] = field(default_factory=list)
    created_by: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    metadata_uri: Optional[str] = None


@dataclass
class NFTMintRecord:
    """
    Record of an NFT mint/claim event.
    
    Attributes:
        nft_id: Unique identifier for the NFT
        token_id: On-chain token ID
        contract_address: NFT contract address
        recipient_fid: Farcaster ID of the recipient
        recipient_address: Wallet address of the recipient
        metadata: NFT metadata
        mint_type: Type of mint ('airdrop', 'claim', 'purchase')
        transaction_hash: Blockchain transaction hash
        block_number: Block number of the mint
        gas_used: Gas used for the transaction
        mint_timestamp: When the mint occurred
        frame_url: Frame URL used for the mint (if applicable)
        eligibility_criteria_met: Dict of criteria that were satisfied
    """
    nft_id: str
    token_id: Optional[int] = None
    contract_address: Optional[str] = None
    recipient_fid: str = ""
    recipient_address: str = ""
    metadata: Optional[NFTMetadata] = None
    mint_type: str = "claim"  # 'airdrop', 'claim', 'purchase'
    transaction_hash: Optional[str] = None
    block_number: Optional[int] = None
    gas_used: Optional[int] = None
    mint_timestamp: float = field(default_factory=time.time)
    frame_url: Optional[str] = None
    eligibility_criteria_met: Dict[str, bool] = field(default_factory=dict)


@dataclass
class Goal:
    """
    Represents a long-term goal or task for the AI system.
    
    Goals provide strategic direction beyond reactive behavior, allowing the AI
    to work towards specific objectives over time.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    status: str = "active"  # active, completed, paused, cancelled
    priority: int = 5  # 1-10, higher is more important
    created_timestamp: float = field(default_factory=time.time)
    target_completion: Optional[float] = None  # Optional deadline
    completion_criteria: List[str] = field(default_factory=list)
    sub_tasks: List[str] = field(default_factory=list)  # List of task descriptions
    progress_metrics: Dict[str, Any] = field(default_factory=dict)
    category: str = "general"  # e.g., "community_growth", "content_creation", "engagement"
    related_channels: List[str] = field(default_factory=list)  # Channels relevant to this goal
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_progress_update(self, update: str, metrics: Optional[Dict[str, Any]] = None):
        """Add a progress update to the goal."""
        if "progress_updates" not in self.metadata:
            self.metadata["progress_updates"] = []
        
        self.metadata["progress_updates"].append({
            "timestamp": time.time(),
            "update": update,
            "metrics": metrics or {}
        })
    
    def mark_completed(self, completion_note: str = ""):
        """Mark the goal as completed."""
        self.status = "completed"
        self.metadata["completed_timestamp"] = time.time()
        if completion_note:
            self.metadata["completion_note"] = completion_note
    
    def get_progress_summary(self) -> Dict[str, Any]:
        """Get a summary of goal progress."""
        updates = self.metadata.get("progress_updates", [])
        return {
            "goal_id": self.id,
            "title": self.title,
            "status": self.status,
            "priority": self.priority,
            "created_days_ago": (time.time() - self.created_timestamp) / 86400,
            "total_updates": len(updates),
            "latest_update": updates[-1] if updates else None,
            "completion_criteria_count": len(self.completion_criteria),
            "sub_tasks_count": len(self.sub_tasks)
        }
    

class WorldStateData:
    def add_message(self, channel_id: str, message):
        """Compatibility method for tests that call add_message on WorldStateData."""
        from .manager import WorldStateManager
        logger.warning("WorldStateData.add_message is deprecated - use WorldStateManager instead")
        if isinstance(message, dict):
            message = Message(**message)
        # Fallback for None channel_id
        if not channel_id:
            channel_id = getattr(message, 'channel_id', None)
        if not channel_id:
            raise ValueError("channel_id must be provided or present in message")
        channel_type = message.channel_type or "matrix"
        if channel_type not in self.channels:
            self.channels[channel_type] = {}
        if channel_id not in self.channels[channel_type]:
            from .structures import Channel
            self.channels[channel_type][channel_id] = Channel(
                id=channel_id,
                name=channel_id,
                type=channel_type
            )
        channel = self.channels[channel_type][channel_id]
        channel.recent_messages.append(message)
        if len(channel.recent_messages) > 50:
            channel.recent_messages = channel.recent_messages[-50:]
        channel.update_last_checked()
        self.seen_messages.add(message.id)
        self.last_update = time.time()

    def to_dict_for_ai(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """Compatibility method for tests that call to_dict_for_ai on WorldStateData."""
        logger.warning("WorldStateData.to_dict_for_ai is deprecated - use PayloadBuilder instead")
        # Provide a basic implementation for backward compatibility
        result = self.to_dict()
        if limit:
            # Apply basic limiting to recent_messages
            for platform_channels in result["channels"].values():
                if isinstance(platform_channels, dict):
                    for channel_data in platform_channels.values():
                        if "recent_messages" in channel_data and len(channel_data["recent_messages"]) > limit:
                            channel_data["recent_messages"] = channel_data["recent_messages"][-limit:]
        # Add recent_media_actions if available
        try:
            media_actions = self.get_recent_media_actions()
            if media_actions:
                result["recent_media_actions"] = media_actions
        except Exception:
            pass
        return result

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
        self.channels: Dict[str, Dict[str, Channel]] = {}  # Nested: {platform: {channel_id: Channel}}
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
        
        # Research knowledge base - persistent AI learning and knowledge accumulation
        self.research_database: Dict[str, Dict[str, Any]] = {}  # topic -> research_entry
        
        # Autonomous Code Evolution (ACE) capabilities
        self.target_repositories: Dict[str, TargetRepositoryContext] = {}  # repo_url -> context
        self.development_tasks: Dict[str, DevelopmentTask] = {}  # task_id -> task
        self.evolutionary_knowledge_base: Dict[str, Dict[str, Any]] = {}  # patterns and learnings
        
        # Legacy compatibility (Phase 1 backward compatibility)
        self.codebase_structure: Optional[Dict[str, Any]] = None
        self.project_plan: Dict[str, DevelopmentTask] = {}  # task_id -> DevelopmentTask  
        self.github_repository_state: Optional[TargetRepositoryContext] = None
        
        # Goal Management System - Long-term strategic objectives
        self.active_goals: List[Goal] = []
        
        # Backward compatibility placeholders
        self.user_details: Dict[str, Any] = {}
        self.bot_media: Dict[str, Any] = {}  # alias for bot_media_on_farcaster

    def get_state_metrics(self) -> Dict[str, Any]:
        """
        Get metrics about the current state for payload size estimation.
        
        Returns:
            Dictionary with metrics about channels, messages, actions, etc.
        """
        # Handle nested channel structure: channels[platform][channel_id]
        total_messages = sum(
            len(ch.recent_messages) 
            for platform_channels in self.channels.values() 
            for ch in platform_channels.values()
        )
        
        # Count total channels across all platforms
        total_channels = sum(len(platform_channels) for platform_channels in self.channels.values())
        
        return {
            "channel_count": total_channels,
            "total_messages": total_messages,
            "action_history_count": len(self.action_history),
            "thread_count": len(self.threads),
            "pending_invites": len(self.pending_matrix_invites),
            "media_library_size": len(self.generated_media_library),
            "development_task_count": len(self.development_tasks),
            "target_repository_count": len(self.target_repositories),
            "active_tasks": len([t for t in self.development_tasks.values() if t.status in ["approved", "implementation_in_progress"]]),
            "codebase_structure_available": self.codebase_structure is not None,
            "active_goals_count": len(self.active_goals),
            "last_update": self.last_update
        }

    # Goal Management System Methods
    def add_goal(self, goal: Goal):
        """Add a new goal to active goals."""
        self.active_goals.append(goal)
        logger.info(f"Added new goal: {goal.title} (ID: {goal.id})")
        
    def update_goal_progress(self, goal_id: str, update: str, metrics: Optional[Dict[str, Any]] = None):
        """Update progress on a specific goal."""
        for goal in self.active_goals:
            if goal.id == goal_id:
                goal.add_progress_update(update, metrics)
                logger.info(f"Updated goal {goal.title}: {update}")
                return True
        return False
        
    def get_active_goals_summary(self) -> List[Dict[str, Any]]:
        """Get summary of all active goals for AI context."""
        return [goal.get_progress_summary() for goal in self.active_goals if goal.status == "active"]
        
    def complete_goal(self, goal_id: str, completion_note: str = ""):
        """Mark a goal as completed."""
        for goal in self.active_goals:
            if goal.id == goal_id:
                goal.mark_completed(completion_note)
                logger.info(f"Completed goal: {goal.title}")
                return True
        return False
        
    def get_goal_by_id(self, goal_id: str) -> Optional[Goal]:
        """Get a specific goal by ID."""
        for goal in self.active_goals:
            if goal.id == goal_id:
                return goal
        return None
    
    def remove_goal(self, goal_id: str) -> bool:
        """Remove a goal from active goals."""
        for i, goal in enumerate(self.active_goals):
            if goal.id == goal_id:
                removed_goal = self.active_goals.pop(i)
                logger.info(f"Removed goal: {removed_goal.title} (ID: {goal_id})")
                return True
        return False
    # Backward-compatible methods for direct WorldState usage - REMOVED
    # These methods caused conflicts with the new nested structure

    def has_replied_to_cast(self, cast_hash: str) -> bool:
        """
        Check if the AI has already replied to a specific cast.
        This now checks for successful or scheduled actions.
        """
        for action in self.action_history:
            if action.action_type == "send_farcaster_reply":
                reply_to_hash = action.parameters.get("reply_to_hash")
                if reply_to_hash == cast_hash:
                    # Consider it replied if the action was successful OR is still scheduled.
                    # This prevents re-queueing a reply while one is already pending.
                    if action.result != "failure":
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

    # Removed to_dict_for_ai method - use WorldStateManager and PayloadBuilder instead

    def get_all_messages(self) -> List[Message]:
        """Get all messages from all channels"""
        all_messages = []
        for platform_channels in self.channels.values():
            for channel in platform_channels.values():
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
                platform: {
                    channel_id: {
                        "id": ch.id,
                        "type": ch.type,
                        "name": ch.name,
                        "recent_messages": [asdict(msg) for msg in ch.recent_messages],
                        "last_checked": ch.last_checked,
                    }
                    for channel_id, ch in platform_channels.items()
                } if isinstance(platform_channels, dict) else {
                    platform_channels.id: {
                        "id": platform_channels.id,
                        "type": platform_channels.type,
                        "name": platform_channels.name,
                        "recent_messages": [asdict(msg) for msg in platform_channels.recent_messages],
                        "last_checked": platform_channels.last_checked,
                    }
                }
                for platform, platform_channels in self.channels.items()
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
            # Autonomous Code Evolution (ACE) fields
            "target_repositories": {url: asdict(ctx) for url, ctx in self.target_repositories.items()},
            "development_tasks": {task_id: asdict(task) for task_id, task in self.development_tasks.items()},
            "evolutionary_knowledge_base": self.evolutionary_knowledge_base,
            # Legacy compatibility
            "codebase_structure": self.codebase_structure,
            "project_plan": {task_id: asdict(task) for task_id, task in self.project_plan.items()},
            "github_repository_state": asdict(self.github_repository_state) if self.github_repository_state else None,
        }

    def get_recent_activity(self, lookback_seconds: int = 300) -> Dict[str, Any]:
        """Get recent activity summary for the AI"""
        cutoff_time = time.time() - lookback_seconds

        recent_messages = []
        for platform_channels in self.channels.values():
            for channel in platform_channels.values():
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
                platform: {
                    channel_id: {
                        "name": ch.name,
                        "type": ch.type,
                        "message_count": len(ch.recent_messages),
                        "recent_messages": [asdict(msg) for msg in ch.recent_messages],
                    }
                    for channel_id, ch in platform_channels.items()
                }
                for platform, platform_channels in self.channels.items()
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
                # Only consider successful image descriptions to avoid retry loops
                is_successful = hasattr(action, "result") and not (
                    "failure" in str(action.result).lower() or
                    "not accessible" in str(action.result).lower() or
                    "error" in str(action.result).lower()
                )
                
                if is_successful:
                    if hasattr(action, "metadata") and action.metadata:
                        image_url = action.metadata.get("image_url")
                        if image_url:
                            image_urls_recently_described.add(image_url)
                    elif hasattr(action, "parameters") and action.parameters:
                        image_url = action.parameters.get("image_url")
                        if image_url:
                            image_urls_recently_described.add(image_url)
                
                # Include all describe_image actions in recent_media_actions for context
                recent_media_actions.append(
                    {
                        "action": "describe_image",
                        "timestamp": action.timestamp,
                        "image_url": action.parameters.get("image_url")
                        if hasattr(action, "parameters")
                        else None,
                        "status": "success" if is_successful else "failed",
                        "result": str(action.result) if hasattr(action, "result") else None,
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

    def update_codebase_structure(self, structure: Dict[str, Any]):
        """Update the codebase structure from GitHub or local analysis."""
        self.codebase_structure = structure
        self.last_update = time.time()

    def add_project_task(self, task: DevelopmentTask):
        """Add a new development task to the plan (legacy compatibility)."""
        self.project_plan[task.task_id] = task
        self.development_tasks[task.task_id] = task  # Also add to new structure
        self.last_update = time.time()

    def update_project_task(self, task_id: str, **kwargs):
        """Update an existing development task."""
        if task_id in self.development_tasks:
            task = self.development_tasks[task_id]
            for key, value in kwargs.items():
                if hasattr(task, key):
                    setattr(task, key, value)
            task.updated_at = time.time()
            self.last_update = time.time()
            # Keep legacy structure in sync
            if task_id in self.project_plan:
                self.project_plan[task_id] = task

    def get_project_tasks_by_status(self, status: str) -> List[DevelopmentTask]:
        """Get all development tasks with a specific status."""
        return [task for task in self.development_tasks.values() if task.status == status]

    def add_target_repository(self, repo_url: str, context: TargetRepositoryContext):
        """Add or update target repository context for ACE operations."""
        self.target_repositories[repo_url] = context
        self.last_update = time.time()

    def get_target_repository(self, repo_url: str) -> Optional[TargetRepositoryContext]:
        """Get target repository context by URL."""
        return self.target_repositories.get(repo_url)

    def update_github_repo_state(self, **kwargs):
        """Update GitHub repository state fields (legacy compatibility)."""
        if self.github_repository_state is None:
            self.github_repository_state = TargetRepositoryContext()
        for key, value in kwargs.items():
            if hasattr(self.github_repository_state, key):
                setattr(self.github_repository_state, key, value)
        self.last_update = time.time()
