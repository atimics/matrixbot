"""
Farcaster Service Wrapper

Service-oriented wrapper for Farcaster observer that implements clean service interfaces.
"""

import logging
import time
from typing import Any, Dict, Optional

from .service_registry import SocialServiceInterface
from ...config import settings

logger = logging.getLogger(__name__)


class FarcasterService(SocialServiceInterface):
    """
    Service wrapper for Farcaster integration that provides clean APIs for social operations.
    """
    
    def __init__(self, farcaster_observer, world_state_manager=None, context_manager=None):
        self._observer = farcaster_observer
        self._world_state_manager = world_state_manager
        self._context_manager = context_manager
        self._service_id = "farcaster"
        self._service_type = "farcaster"
    
    @property
    def service_id(self) -> str:
        return self._service_id
    
    @property
    def service_type(self) -> str:
        return self._service_type
    
    async def is_available(self) -> bool:
        """Check if the Farcaster service is available"""
        return (self._observer is not None and 
                hasattr(self._observer, 'api_client') and 
                self._observer.api_client is not None and
                self._observer.enabled)
    
    async def create_post(self, content: str, **kwargs) -> Dict[str, Any]:
        """
        Create a new Farcaster cast.
        
        Args:
            content: Cast content
            **kwargs: Additional options (embed_urls, parent_url, etc.)
            
        Returns:
            Dict with success status and cast details
        """
        if not await self.is_available():
            return {
                "status": "failure",
                "error": "Farcaster service not available",
                "timestamp": time.time()
            }
        
        embed_urls = kwargs.get('embed_urls', [])
        parent_url = kwargs.get('parent_url')
        
        try:
            result = await self._observer.post_cast(
                content, 
                embed_urls=embed_urls,
                reply_to=parent_url
            )
            
            if result.get("success"):
                cast_hash = result.get("cast_hash", "unknown")
                
                # Record the sent cast in world state
                if self._world_state_manager:
                    from ...core.world_state.structures import Message
                    bot_message = Message(
                        id=cast_hash,
                        channel_id="farcaster_feed",  # Generic channel for Farcaster posts
                        channel_type="farcaster",
                        sender=settings.FARCASTER_FID,
                        content=content,
                        timestamp=time.time(),
                        reply_to=parent_url
                    )
                    self._world_state_manager.add_message("farcaster_feed", bot_message)
                
                # Record in context manager
                if self._context_manager:
                    assistant_message = {
                        "cast_hash": cast_hash,
                        "sender": settings.FARCASTER_FID,
                        "content": content,
                        "timestamp": time.time(),
                        "type": "assistant"
                    }
                    await self._context_manager.add_assistant_message("farcaster_feed", assistant_message)
                
                return {
                    "status": "success",
                    "message": f"Created Farcaster cast",
                    "cast_hash": cast_hash,
                    "content": content,
                    "embed_urls": embed_urls,
                    "parent_url": parent_url,
                    "timestamp": time.time()
                }
            else:
                return {
                    "status": "failure",
                    "error": result.get("error", "Unknown error creating cast"),
                    "timestamp": time.time()
                }
                
        except Exception as e:
            logger.error(f"Error creating Farcaster cast: {e}")
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time()
            }
    
    async def like_post(self, post_id: str) -> Dict[str, Any]:
        """
        Like a Farcaster cast.
        
        Args:
            post_id: Hash of the cast to like
            
        Returns:
            Dict with success status and like details
        """
        if not await self.is_available():
            return {
                "status": "failure",
                "error": "Farcaster service not available",
                "timestamp": time.time()
            }
        
        try:
            result = await self._observer.like_cast(post_id)
            
            if result.get("success"):
                like_hash = result.get("like_hash", "unknown")
                
                # Record the like action in world state
                if self._world_state_manager:
                    self._world_state_manager.record_farcaster_like(post_id, like_hash)
                
                return {
                    "status": "success",
                    "message": f"Liked Farcaster cast {post_id}",
                    "like_hash": like_hash,
                    "cast_hash": post_id,
                    "timestamp": time.time()
                }
            else:
                return {
                    "status": "failure",
                    "error": result.get("error", "Unknown error liking cast"),
                    "timestamp": time.time()
                }
                
        except Exception as e:
            logger.error(f"Error liking Farcaster cast: {e}")
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time()
            }
    
    async def reply_to_post(self, content: str, parent_cast_hash: str, **kwargs) -> Dict[str, Any]:
        """
        Reply to a Farcaster cast.
        
        Args:
            content: Reply content
            parent_cast_hash: Hash of the cast to reply to
            **kwargs: Additional options
            
        Returns:
            Dict with success status and reply details
        """
        if not await self.is_available():
            return {
                "status": "failure",
                "error": "Farcaster service not available",
                "timestamp": time.time()
            }
        
        try:
            result = await self._observer.reply_to_cast(content, parent_cast_hash)
            
            if result.get("success"):
                reply_hash = result.get("cast_hash", "unknown")
                
                # Record the reply in world state
                if self._world_state_manager:
                    from ...core.world_state.structures import Message
                    bot_message = Message(
                        id=reply_hash,
                        channel_id="farcaster_feed",
                        channel_type="farcaster",
                        sender=settings.FARCASTER_FID,
                        content=content,
                        timestamp=time.time(),
                        reply_to=parent_cast_hash
                    )
                    self._world_state_manager.add_message("farcaster_feed", bot_message)
                
                return {
                    "status": "success",
                    "message": f"Replied to Farcaster cast {parent_cast_hash}",
                    "reply_hash": reply_hash,
                    "parent_hash": parent_cast_hash,
                    "content": content,
                    "timestamp": time.time()
                }
            else:
                return {
                    "status": "failure",
                    "error": result.get("error", "Unknown error replying to cast"),
                    "timestamp": time.time()
                }
                
        except Exception as e:
            logger.error(f"Error replying to Farcaster cast: {e}")
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time()
            }
