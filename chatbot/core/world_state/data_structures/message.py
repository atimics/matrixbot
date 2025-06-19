#!/usr/bin/env python3
"""
Message Data Structure

Defines the core Message class for unified message representation across platforms.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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
