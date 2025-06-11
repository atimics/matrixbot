"""
Farcaster Integration Service

Service wrapper for Farcaster platform integration.
Provides a clean service-oriented interface for Farcaster communication and feed management.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional
import logging

from ..base_service import BaseIntegrationService, ServiceStatus
from ...core.world_state import Message
from ..farcaster.farcaster_observer import FarcasterObserver

logger = logging.getLogger(__name__)


class FarcasterService(BaseIntegrationService):
    """
    Farcaster integration service providing clean abstraction over Farcaster observer.
    
    This service encapsulates Farcaster-specific logic and provides standardized
    interfaces for messaging, feed observation, and social interaction.
    """
    
    def __init__(self, service_id: str = "farcaster_service", config: Dict[str, Any] = None,
                 api_key: str = None, signer_uuid: str = None, bot_fid: str = None,
                 world_state_manager=None):
        super().__init__(service_id, "farcaster", config)
        self.api_key = api_key
        self.signer_uuid = signer_uuid
        self.bot_fid = bot_fid
        self.world_state_manager = world_state_manager
        self._farcaster_observer: Optional[FarcasterObserver] = None
        
    @property
    def enabled(self) -> bool:
        """Check if Farcaster service is enabled and properly configured."""
        return (self._farcaster_observer is not None and 
                self._farcaster_observer.enabled)
    
    async def connect(self) -> bool:
        """Connect to Farcaster API and initialize observer."""
        try:
            self._log_operation("Connecting to Farcaster")
            
            # Create Farcaster observer if not exists
            if not self._farcaster_observer:
                self._farcaster_observer = FarcasterObserver(
                    integration_id=f"{self.service_id}_observer",
                    display_name="Farcaster Observer",
                    config=self.config,
                    api_key=self.api_key,
                    signer_uuid=self.signer_uuid,
                    bot_fid=self.bot_fid,
                    world_state_manager=self.world_state_manager
                )
                self._set_observer(self._farcaster_observer)
            
            # Connect the observer
            await self._farcaster_observer.connect()
            
            self.is_connected = True
            self.connection_time = time.time()
            self.last_error = None
            
            self._log_operation("Connected successfully")
            return True
            
        except Exception as e:
            await self._handle_error(e, "Farcaster connection failed")
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from Farcaster API."""
        try:
            self._log_operation("Disconnecting from Farcaster")
            
            if self._farcaster_observer:
                await self._farcaster_observer.disconnect()
            
            self.is_connected = False
            self.connection_time = None
            
            self._log_operation("Disconnected successfully")
            
        except Exception as e:
            await self._handle_error(e, "Farcaster disconnection error")
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test Farcaster API connection without full initialization."""
        try:
            if not self._farcaster_observer:
                return {"success": False, "error": "Farcaster observer not initialized"}
                
            # Test connection through observer
            result = await self._farcaster_observer.test_connection()
            return {"success": result, "error": None if result else "Connection test failed"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # === MESSAGING INTERFACE ===
    
    async def send_message(self, content: str, channel_id: str = None, **kwargs) -> Dict[str, Any]:
        """
        Send a cast to Farcaster.
        
        Args:
            content: Cast content
            channel_id: Optional channel ID (e.g., 'base', 'farcaster-dev')
            **kwargs: Additional options (embed_urls, reply_to, etc.)
            
        Returns:
            Dict with success status and cast details
        """
        try:
            if not self.is_connected or not self._farcaster_observer:
                return {"success": False, "error": "Not connected to Farcaster"}
            
            self._log_operation(f"Sending cast to channel {channel_id or 'home'}")
            
            # Use observer's post_cast method
            result = await self._farcaster_observer.post_cast(
                content=content,
                channel=channel_id,
                embed_urls=kwargs.get('embed_urls'),
                reply_to=kwargs.get('reply_to'),
                action_id=kwargs.get('action_id')
            )
            
            return {
                "success": result.get("success", False),
                "cast_hash": result.get("cast", {}).get("hash"),
                "details": result
            }
            
        except Exception as e:
            await self._handle_error(e, "Failed to send Farcaster cast")
            return {"success": False, "error": str(e)}
    
    async def reply_to_message(self, content: str, message_id: str, **kwargs) -> Dict[str, Any]:
        """
        Reply to a specific Farcaster cast.
        
        Args:
            content: Reply content
            message_id: Cast hash to reply to
            **kwargs: Additional options
            
        Returns:
            Dict with success status and reply details
        """
        try:
            if not self.is_connected or not self._farcaster_observer:
                return {"success": False, "error": "Not connected to Farcaster"}
            
            self._log_operation(f"Replying to cast {message_id}")
            
            # Use observer's reply_to_cast method
            result = await self._farcaster_observer.reply_to_cast(
                content=content,
                reply_to_hash=message_id,
                action_id=kwargs.get('action_id')
            )
            
            return {
                "success": result.get("success", False),
                "reply_hash": result.get("cast", {}).get("hash"),
                "details": result
            }
            
        except Exception as e:
            await self._handle_error(e, "Failed to reply to Farcaster cast")
            return {"success": False, "error": str(e)}
    
    # === FEED OBSERVATION INTERFACE ===
    
    async def get_available_channels(self) -> List[Dict[str, Any]]:
        """
        Get list of Farcaster channels and feed types available.
        
        Returns:
            List of feed info dicts with keys: id, name, type, description
        """
        try:
            self._log_operation("Getting available Farcaster channels and feeds")
            
            # Return comprehensive list of Farcaster feed types
            feeds = [
                {
                    "id": "home",
                    "name": "Home Feed",
                    "type": "farcaster_home",
                    "description": "Personal home timeline"
                },
                {
                    "id": "for_you",
                    "name": "For You Feed",
                    "type": "farcaster_for_you",
                    "description": "Personalized algorithmic feed"
                },
                {
                    "id": "trending",
                    "name": "Trending",
                    "type": "farcaster_trending",
                    "description": "Trending casts across the network"
                },
                {
                    "id": "notifications",
                    "name": "Notifications",
                    "type": "farcaster_notifications",
                    "description": "Mentions, replies, and reactions"
                },
                {
                    "id": "mentions_and_replies",
                    "name": "Mentions & Replies",
                    "type": "farcaster_mentions",
                    "description": "Direct mentions and replies to bot"
                }
            ]
            
            # Add popular channels
            popular_channels = [
                "base", "farcaster-dev", "ethereum", "crypto", "builders", 
                "founders", "design", "programming", "ai", "tech"
            ]
            
            for channel in popular_channels:
                feeds.append({
                    "id": f"channel_{channel}",
                    "name": f"/{channel}",
                    "type": "farcaster_channel",
                    "description": f"Farcaster {channel} channel"
                })
            
            return feeds
        
        except Exception as e:
            await self._handle_error(e, "Failed to get Farcaster channels")
            return []
    
    async def observe_channel_messages(self, channel_id: str, limit: int = 50) -> List[Message]:
        """
        Observe recent messages from a specific Farcaster channel or feed.
        
        Args:
            channel_id: Channel identifier (e.g., 'home', 'base', 'trending')
            limit: Maximum number of messages to retrieve
            
        Returns:
            List of Message objects
        """
        try:
            if not self.is_connected or not self._farcaster_observer:
                return []
            
            self._log_operation(f"Observing Farcaster channel {channel_id}")
            
            # Route to appropriate observer method based on channel type
            if channel_id == "home":
                return await self._farcaster_observer._observe_home_feed()
            elif channel_id == "for_you":
                return await self._farcaster_observer._observe_for_you_feed(limit=limit)
            elif channel_id == "trending":
                return await self._farcaster_observer._observe_trending_casts(limit=limit)
            elif channel_id == "notifications":
                return await self._farcaster_observer._observe_notifications()
            elif channel_id == "mentions_and_replies":
                return await self._farcaster_observer._observe_mentions()
            elif channel_id.startswith("channel_"):
                # Extract actual channel name
                actual_channel = channel_id.replace("channel_", "")
                return await self._farcaster_observer._observe_channel_feed(actual_channel)
            else:
                # Try as direct channel name
                return await self._farcaster_observer._observe_channel_feed(channel_id)
                
        except Exception as e:
            await self._handle_error(e, f"Failed to observe Farcaster channel {channel_id}")
            return []
    
    async def observe_all_feeds(self, feed_types: List[str] = None) -> Dict[str, List[Message]]:
        """
        Observe messages from multiple Farcaster feed types.
        
        Args:
            feed_types: List of feed types to observe
            
        Returns:
            Dict mapping feed_type -> List[Message]
        """
        try:
            if not self.is_connected or not self._farcaster_observer:
                return {}
            
            # Default feed types for comprehensive coverage
            if feed_types is None:
                feed_types = [
                    'home', 'for_you', 'trending', 'notifications',
                    'mentions_and_replies'
                ]
            
            self._log_operation(f"Observing Farcaster feeds: {feed_types}")
            
            # Use observer's comprehensive world state collection
            world_state_data = await self._farcaster_observer.observe_world_state_data(
                include_trending='trending' in feed_types,
                include_home_feed='home' in feed_types,
                include_notifications='notifications' in feed_types,
                include_for_you_feed='for_you' in feed_types,
                trending_limit=10,
                for_you_limit=10
            )
            
            return world_state_data
            
        except Exception as e:
            await self._handle_error(e, "Failed to observe Farcaster feeds")
            return {}
    
    # === USER INTERACTION INTERFACE ===
    
    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """
        Get information about a Farcaster user.
        
        Args:
            user_id: Farcaster FID or username
            
        Returns:
            Dict with user information
        """
        try:
            if not self.is_connected or not self._farcaster_observer:
                return {}
            
            self._log_operation(f"Getting Farcaster user info for {user_id}")
            
            # Use observer's API client to get user info
            if self._farcaster_observer.api_client:
                try:
                    # Try as FID first, then username
                    if user_id.isdigit():
                        fid = int(user_id)
                        user_data = await self._farcaster_observer.api_client.get_user_info(fid)
                    else:
                        user_data = await self._farcaster_observer.api_client.get_user_by_username(user_id)
                        
                    if user_data and "user" in user_data:
                        user = user_data["user"]
                        return {
                            "user_id": str(user.get("fid")),
                            "username": user.get("username"),
                            "display_name": user.get("display_name"),
                            "bio": user.get("profile", {}).get("bio", {}).get("text"),
                            "follower_count": user.get("follower_count", 0),
                            "following_count": user.get("following_count", 0),
                            "power_badge": user.get("power_badge", False),
                            "platform": "farcaster",
                            "avatar_url": user.get("pfp_url"),
                            "verified_addresses": user.get("verified_addresses", [])
                        }
                except Exception as api_error:
                    logger.debug(f"API error getting user info: {api_error}")
            
            return {"user_id": user_id, "platform": "farcaster"}
                
        except Exception as e:
            await self._handle_error(e, f"Failed to get Farcaster user info for {user_id}")
            return {"user_id": user_id, "platform": "farcaster"}
    
    async def get_user_context(self, message: Message) -> Dict[str, Any]:
        """
        Get contextual information about a Farcaster user from a message.
        
        Args:
            message: Message object
            
        Returns:
            Dict with user context information
        """
        try:
            if self._farcaster_observer:
                return self._farcaster_observer.get_user_context(message)
            
            # Fallback context
            return {
                "username": getattr(message, 'sender_username', 'unknown'),
                "display_name": getattr(message, 'sender_display_name', 'Unknown'),
                "fid": getattr(message, 'sender_fid', None),
                "follower_count": getattr(message, 'sender_follower_count', 0),
                "following_count": getattr(message, 'sender_following_count', 0),
                "power_badge": False,
                "platform": "farcaster",
                "engagement_level": "medium"
            }
            
        except Exception as e:
            await self._handle_error(e, "Failed to get Farcaster user context")
            return {"username": "unknown", "platform": "farcaster"}
    
    # === STATUS AND METRICS ===
    
    def _get_service_metrics(self) -> Dict[str, Any]:
        """Get Farcaster service-specific metrics."""
        metrics = {
            "bot_fid": self.bot_fid,
            "api_connected": False,
            "rate_limit_remaining": None,
            "last_cast_time": None,
            "casts_sent": 0,
            "world_state_collection_enabled": False
        }
        
        if self._farcaster_observer:
            try:
                metrics.update({
                    "api_connected": bool(self._farcaster_observer.api_client),
                    "world_state_collection_enabled": getattr(
                        self._farcaster_observer, 'world_state_collection_enabled', False
                    ),
                    "ecosystem_token_service_active": bool(
                        getattr(self._farcaster_observer, 'ecosystem_token_service', None)
                    )
                })
                
                # Get rate limit info
                if hasattr(self._farcaster_observer, 'get_rate_limit_status'):
                    rate_status = self._farcaster_observer.get_rate_limit_status()
                    metrics["rate_limit_remaining"] = rate_status.get("remaining")
                    metrics["rate_limit_reset"] = rate_status.get("reset_time")
                
            except Exception as e:
                logger.debug(f"Error getting Farcaster metrics: {e}")
        
        return metrics
    
    # === FARCASTER-SPECIFIC METHODS ===
    
    async def like_cast(self, cast_hash: str) -> Dict[str, Any]:
        """Like a Farcaster cast."""
        try:
            if not self.is_connected or not self._farcaster_observer:
                return {"success": False, "error": "Not connected to Farcaster"}
            
            self._log_operation(f"Liking cast {cast_hash}")
            result = await self._farcaster_observer.like_cast(cast_hash)
            return result
            
        except Exception as e:
            await self._handle_error(e, f"Failed to like cast {cast_hash}")
            return {"success": False, "error": str(e)}
    
    async def recast(self, cast_hash: str) -> Dict[str, Any]:
        """Recast a Farcaster cast."""
        try:
            if not self.is_connected or not self._farcaster_observer:
                return {"success": False, "error": "Not connected to Farcaster"}
            
            self._log_operation(f"Recasting {cast_hash}")
            
            if hasattr(self._farcaster_observer, 'recast'):
                result = await self._farcaster_observer.recast(cast_hash)
                return result
            else:
                return {"success": False, "error": "Recast not supported"}
                
        except Exception as e:
            await self._handle_error(e, f"Failed to recast {cast_hash}")
            return {"success": False, "error": str(e)}
    
    async def follow_user(self, fid: int) -> Dict[str, Any]:
        """Follow a Farcaster user."""
        try:
            if not self.is_connected or not self._farcaster_observer:
                return {"success": False, "error": "Not connected to Farcaster"}
            
            self._log_operation(f"Following user FID {fid}")
            result = await self._farcaster_observer.follow_user(fid)
            return result
            
        except Exception as e:
            await self._handle_error(e, f"Failed to follow user {fid}")
            return {"success": False, "error": str(e)}
    
    async def unfollow_user(self, fid: int) -> Dict[str, Any]:
        """Unfollow a Farcaster user."""
        try:
            if not self.is_connected or not self._farcaster_observer:
                return {"success": False, "error": "Not connected to Farcaster"}
            
            self._log_operation(f"Unfollowing user FID {fid}")
            result = await self._farcaster_observer.unfollow_user(fid)
            return result
            
        except Exception as e:
            await self._handle_error(e, f"Failed to unfollow user {fid}")
            return {"success": False, "error": str(e)}
    
    async def get_cast_details(self, cast_hash: str) -> Dict[str, Any]:
        """Get detailed information about a specific cast."""
        try:
            if not self.is_connected or not self._farcaster_observer:
                return {"success": False, "error": "Not connected to Farcaster"}
            
            self._log_operation(f"Getting cast details for {cast_hash}")
            result = await self._farcaster_observer.get_cast_details(cast_hash)
            return result
            
        except Exception as e:
            await self._handle_error(e, f"Failed to get cast details for {cast_hash}")
            return {"success": False, "error": str(e)}
    
    async def search_casts(self, query: str, channel_id: str = None, limit: int = 10) -> Dict[str, Any]:
        """Search for casts by query."""
        try:
            if not self.is_connected or not self._farcaster_observer:
                return {"success": False, "error": "Not connected to Farcaster"}
            
            self._log_operation(f"Searching casts for '{query}'")
            result = await self._farcaster_observer.search_casts(query, channel_id, limit)
            return result
            
        except Exception as e:
            await self._handle_error(e, f"Failed to search casts for '{query}'")
            return {"success": False, "error": str(e)}
    
    async def get_trending_casts(self, channel_id: str = None, timeframe_hours: int = 24, 
                               limit: int = 10) -> Dict[str, Any]:
        """Get trending casts."""
        try:
            if not self.is_connected or not self._farcaster_observer:
                return {"success": False, "error": "Not connected to Farcaster"}
            
            self._log_operation(f"Getting trending casts for channel {channel_id or 'all'}")
            result = await self._farcaster_observer.get_trending_casts(
                channel_id, timeframe_hours, limit
            )
            return result
            
        except Exception as e:
            await self._handle_error(e, "Failed to get trending casts")
            return {"success": False, "error": str(e)}
    
    async def collect_world_state_now(self) -> Dict[str, Any]:
        """Manually trigger comprehensive world state collection."""
        try:
            if not self.is_connected or not self._farcaster_observer:
                return {"success": False, "error": "Not connected to Farcaster"}
            
            self._log_operation("Collecting comprehensive world state data")
            result = await self._farcaster_observer.collect_world_state_now()
            return result
            
        except Exception as e:
            await self._handle_error(e, "Failed to collect world state data")
            return {"success": False, "error": str(e)}
    
    def schedule_cast(self, content: str, channel: str = None, action_id: str = None, 
                     embeds: List[str] = None) -> Dict[str, Any]:
        """Schedule a cast for later posting."""
        try:
            if not self._farcaster_observer:
                return {"success": False, "error": "Observer not available"}
            
            self._log_operation(f"Scheduling cast for channel {channel or 'home'}")
            self._farcaster_observer.schedule_post(content, channel, action_id, embeds)
            return {"success": True, "message": "Cast scheduled successfully"}
            
        except Exception as e:
            logger.error(f"Failed to schedule cast: {e}")
            return {"success": False, "error": str(e)}
    
    def schedule_reply(self, content: str, reply_to_hash: str, action_id: str = None) -> Dict[str, Any]:
        """Schedule a reply for later posting."""
        try:
            if not self._farcaster_observer:
                return {"success": False, "error": "Observer not available"}
            
            self._log_operation(f"Scheduling reply to {reply_to_hash}")
            self._farcaster_observer.schedule_reply(content, reply_to_hash, action_id)
            return {"success": True, "message": "Reply scheduled successfully"}
            
        except Exception as e:
            logger.error(f"Failed to schedule reply: {e}")
            return {"success": False, "error": str(e)}
