"""
Utility functions for Farcaster tools.
"""
import time
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _summarize_cast_for_ai(cast_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create an AI-optimized summary of a cast, removing verbose metadata.

    Args:
        cast_data: Full cast data dictionary from asdict() conversion

    Returns:
        Compact cast summary suitable for AI context
    """
    # Extract essential information only
    summary = {
        "id": cast_data.get("id"),
        "sender": cast_data.get("sender_username") or cast_data.get("sender"),
        "content": cast_data.get("content", "")[:200] + "..." if len(cast_data.get("content", "")) > 200 else cast_data.get("content", ""),
        "timestamp": cast_data.get("timestamp"),
        "engagement": {
            "likes": cast_data.get("metadata", {}).get("reactions", {}).get("likes_count", 0),
            "recasts": cast_data.get("metadata", {}).get("reactions", {}).get("recasts_count", 0),
            "replies": cast_data.get("metadata", {}).get("replies_count", 0)
        },
        "user_info": {
            "username": cast_data.get("sender_username"),
            "display_name": cast_data.get("sender_display_name"),
            "followers": cast_data.get("sender_follower_count"),
            "power_badge": cast_data.get("metadata", {}).get("power_badge", False)
        }
    }

    # Add reply context if it's a reply
    if cast_data.get("reply_to"):
        summary["reply_to"] = cast_data.get("reply_to")

    # Add channel if it's in a specific channel
    channel_id = cast_data.get("channel_id", "")
    if ":" in channel_id and not channel_id.endswith("_all"):
        # Extract meaningful channel name (e.g., "farcaster:trending_all:chatbfg" -> "chatbfg")
        parts = channel_id.split(":")
        if len(parts) > 2:
            summary["channel"] = parts[-1]

    return summary


def get_farcaster_observer(context):
    """
    Get the Farcaster observer from the ServiceRegistry.
    
    Args:
        context: ActionContext instance
        
    Returns:
        FarcasterObserver instance or None if not available
    """
    if not context.service_registry:
        logger.error("ServiceRegistry not available in ActionContext")
        return None
        
    observer = context.service_registry.get_service("farcaster_observer")
    if not observer:
        logger.error("Farcaster observer not available in ServiceRegistry")
        
    return observer


def create_error_response(message: str, **kwargs) -> Dict[str, Any]:
    """Create a standardized error response."""
    response = {
        "status": "failure",
        "error": message,
        "timestamp": time.time()
    }
    response.update(kwargs)
    return response


def create_success_response(message: str, **kwargs) -> Dict[str, Any]:
    """Create a standardized success response."""
    response = {
        "status": "success",
        "message": message,
        "timestamp": time.time()
    }
    response.update(kwargs)
    return response
