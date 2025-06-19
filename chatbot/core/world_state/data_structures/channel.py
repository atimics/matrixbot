#!/usr/bin/env python3
"""
Channel Data Structure

Defines the Channel class for unified channel/room representation across platforms.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .message import Message


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
