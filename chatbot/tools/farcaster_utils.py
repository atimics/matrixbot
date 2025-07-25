"""
Farcaster utility functions and helper classes.
"""
import re
import time
import logging
from typing import Any, Dict, List, Optional, Union

from ..utils.markdown_utils import strip_markdown
from .farcaster_constants import (
    MAX_FARCASTER_CONTENT_LENGTH, 
    MENTION_PATTERN, 
    SUPPORTED_MEDIA_TYPES,
    ERROR_MESSAGES
)

logger = logging.getLogger(__name__)


class FarcasterCastUtils:
    """Utility class for Farcaster cast operations."""
    
    @staticmethod
    def validate_content(content: str) -> str:
        """
        Validate and clean content for Farcaster posting.
        
        Args:
            content: Raw content string
            
        Returns:
            Cleaned and validated content
            
        Raises:
            ValueError: If content is invalid
        """
        if not content:
            return ""
            
        # Strip markdown formatting
        cleaned_content = strip_markdown(content)
        
        # Truncate if too long
        if len(cleaned_content) > MAX_FARCASTER_CONTENT_LENGTH:
            cleaned_content = cleaned_content[:MAX_FARCASTER_CONTENT_LENGTH - 3] + "..."
            logger.warning(f"Content truncated to {MAX_FARCASTER_CONTENT_LENGTH} characters")
            
        return cleaned_content
    
    @staticmethod
    def prepare_media(media: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validate and prepare media objects for Farcaster.
        
        Args:
            media: List of media objects with url, type, and optional alt_text
            
        Returns:
            Validated media list
            
        Raises:
            ValueError: If media format is invalid
        """
        if not media:
            return []
            
        validated_media = []
        for item in media:
            if not isinstance(item, dict):
                logger.warning(f"Skipping invalid media item: {item}")
                continue
                
            if "url" not in item or "type" not in item:
                logger.warning(f"Skipping media item missing url/type: {item}")
                continue
                
            if item["type"] not in SUPPORTED_MEDIA_TYPES:
                logger.warning(f"Skipping unsupported media type: {item['type']}")
                continue
                
            validated_item = {
                "url": item["url"],
                "type": item["type"],
                "alt_text": item.get("alt_text", "")
            }
            validated_media.append(validated_item)
            
        return validated_media
    
    @staticmethod
    def extract_mentions(content: str) -> List[str]:
        """
        Extract @mentions from cast content.
        
        Args:
            content: Cast text content
            
        Returns:
            List of mentioned usernames (without @)
        """
        if not content:
            return []
            
        return re.findall(MENTION_PATTERN, content)
    
    @staticmethod
    def is_mention_to_bot(
        cast_content: str, 
        bot_fid: Optional[str] = None, 
        bot_username: Optional[str] = None
    ) -> bool:
        """
        Determine if a cast mentions the bot.
        
        Args:
            cast_content: The text content of the cast
            bot_fid: Bot's Farcaster ID  
            bot_username: Bot's username
            
        Returns:
            True if the cast mentions the bot, False otherwise
        """
        if not cast_content:
            return False
            
        content_lower = cast_content.lower()
        
        # Check for username mention
        if bot_username:
            username_lower = bot_username.lower()
            if f"@{username_lower}" in content_lower:
                return True
                
        # Could extend with FID-based mention detection if needed
        return False
    
    @staticmethod
    def summarize_cast_for_ai(cast_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create an AI-optimized summary of a cast, removing verbose metadata.

        Args:
            cast_data: Full cast data dictionary

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


class DuplicateGuard:
    """Helper class for preventing duplicate actions."""
    
    def __init__(self, world_state_manager=None):
        self.world_state_manager = world_state_manager
    
    def check_duplicate_cast(self, content: str) -> bool:
        """Check if we've already sent a cast with identical content."""
        if not self.world_state_manager:
            return False
        return self.world_state_manager.has_sent_farcaster_post(content)
    
    def check_duplicate_reply(self, cast_hash: str) -> bool:
        """Check if we've already replied to this cast."""
        if not self.world_state_manager:
            return False
        return self.world_state_manager.has_replied_to_cast(cast_hash)
    
    def check_duplicate_like(self, cast_hash: str) -> bool:
        """Check if we've already liked this cast."""
        if not self.world_state_manager:
            return False
        return self.world_state_manager.has_liked_cast(cast_hash)
    
    def check_duplicate_quote(self, cast_hash: str) -> bool:
        """Check if we've already quoted this cast."""
        if not self.world_state_manager:
            return False
        return self.world_state_manager.has_quoted_cast(cast_hash)
    
    def is_bot_cast(self, cast_hash: str) -> bool:
        """Check if a cast was sent by the bot."""
        if not self.world_state_manager:
            return False
        return self.world_state_manager.is_bot_cast(cast_hash)


class MediaUtils:
    """Utilities for handling media attachments."""
    
    @staticmethod
    def get_recent_media_url(world_state_manager, max_age_seconds: int = 300) -> Optional[str]:
        """
        Get URL of recently generated media.
        
        Args:
            world_state_manager: World state manager instance
            max_age_seconds: Maximum age in seconds (default 5 minutes)
            
        Returns:
            URL of recent media or None
        """
        if not world_state_manager:
            return None
            
        recent_media_url = world_state_manager.get_last_generated_media_url()
        if not recent_media_url:
            return None
            
        # Check if the media was generated recently
        if hasattr(world_state_manager.state, 'generated_media_library'):
            media_library = world_state_manager.state.generated_media_library
            if media_library:
                last_media = media_library[-1]
                media_age = time.time() - last_media.get('timestamp', 0)
                if media_age <= max_age_seconds:
                    return recent_media_url
                    
        return None


class EmbedUtils:
    """Utilities for handling embeds and URLs."""
    
    @staticmethod
    def prepare_embeds(embed_url: Optional[str] = None, media: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, str]]:
        """
        Prepare embeds list from various sources.
        
        Args:
            embed_url: Single URL to embed
            media: List of media objects
            
        Returns:
            List of embed objects
        """
        embeds = []
        
        if embed_url:
            embeds.append({"url": embed_url})
            
        if media:
            for item in media:
                if "url" in item:
                    embeds.append({"url": item["url"]})
                    
        return embeds
    
    @staticmethod
    def extract_embed_urls(embeds: List[Dict[str, str]]) -> List[str]:
        """Extract URLs from embed objects."""
        return [e['url'] for e in embeds if 'url' in e]
