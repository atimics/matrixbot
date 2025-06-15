"""
Farcaster tools module - Service-oriented architecture.

This module contains all Farcaster-related tools organized by functionality:
- posting_tools: Creating posts, replies, quotes, DMs
- engagement_tools: Likes, follows, unfollows, delete reactions
- management_tools: Delete posts and other management functions
- discovery_tools: Search, trending, timelines, world state collection
"""

# Import all tools from submodules
from .posting_tools import (
    SendFarcasterPostTool,
    SendFarcasterReplyTool,
    QuoteFarcasterPostTool,
    SendFarcasterDMTool,
)

from .engagement_tools import (
    LikeFarcasterPostTool,
    FollowFarcasterUserTool,
    UnfollowFarcasterUserTool,
    DeleteFarcasterReactionTool,
)

from .management_tools import (
    DeleteFarcasterPostTool,
)

from .discovery_tools import (
    GetUserTimelineTool,
    CollectWorldStateTool,
    GetTrendingCastsTool,
    SearchCastsTool,
    GetCastByUrlTool,
)

from .feed_management_tools import (
    AddFarcasterFeedTool,
    ListFarcasterFeedsTool,
    RemoveFarcasterFeedTool,
)

# Export all tools for easy import
__all__ = [
    # Posting tools
    "SendFarcasterPostTool",
    "SendFarcasterReplyTool", 
    "QuoteFarcasterPostTool",
    "SendFarcasterDMTool",
    
    # Engagement tools
    "LikeFarcasterPostTool",
    "FollowFarcasterUserTool",
    "UnfollowFarcasterUserTool",
    "DeleteFarcasterReactionTool",
    
    # Management tools
    "DeleteFarcasterPostTool",
    
    # Discovery tools
    "GetUserTimelineTool",
    "CollectWorldStateTool",
    "GetTrendingCastsTool",
    "SearchCastsTool",
    "GetCastByUrlTool",
    
    # Feed management tools
    "AddFarcasterFeedTool",
    "ListFarcasterFeedsTool",
    "RemoveFarcasterFeedTool",
]

# Convenience groupings
POSTING_TOOLS = [
    SendFarcasterPostTool,
    SendFarcasterReplyTool,
    QuoteFarcasterPostTool,
    SendFarcasterDMTool,
]

ENGAGEMENT_TOOLS = [
    LikeFarcasterPostTool,
    FollowFarcasterUserTool,
    UnfollowFarcasterUserTool,
    DeleteFarcasterReactionTool,
]

MANAGEMENT_TOOLS = [
    DeleteFarcasterPostTool,
]

DISCOVERY_TOOLS = [
    GetUserTimelineTool,
    CollectWorldStateTool,
    GetTrendingCastsTool,
    SearchCastsTool,
    GetCastByUrlTool,
]

FEED_MANAGEMENT_TOOLS = [
    AddFarcasterFeedTool,
    ListFarcasterFeedsTool,
    RemoveFarcasterFeedTool,
]

# All tools in one list
ALL_FARCASTER_TOOLS = (
    POSTING_TOOLS + 
    ENGAGEMENT_TOOLS + 
    MANAGEMENT_TOOLS + 
    DISCOVERY_TOOLS +
    FEED_MANAGEMENT_TOOLS
)
