"""
Matrix Service Wrapper

Service-oriented wrapper for Matrix observer that implements clean service interfaces.
"""

import logging
import time
from typing import Any, Dict, Optional

from .service_registry import MessagingServiceInterface, MediaServiceInterface
from ...utils.markdown_utils import format_for_matrix
from ...config import settings

logger = logging.getLogger(__name__)


class MatrixService(MessagingServiceInterface, MediaServiceInterface):
    """
    Service wrapper for Matrix integration that provides clean APIs for messaging operations.
    """
    
    def __init__(self, matrix_observer, world_state_manager=None, context_manager=None):
        self._observer = matrix_observer
        self._world_state_manager = world_state_manager
        self._context_manager = context_manager
        self._service_id = "matrix"
        self._service_type = "matrix"
    
    @property
    def service_id(self) -> str:
        return self._service_id
    
    @property
    def service_type(self) -> str:
        return self._service_type
    
    async def is_available(self) -> bool:
        """Check if the Matrix service is available"""
        return self._observer is not None and hasattr(self._observer, 'client') and self._observer.client is not None
    
    async def send_message(self, channel_id: str, content: str, **kwargs) -> Dict[str, Any]:
        """
        Send a message to a Matrix room.
        
        Args:
            channel_id: Matrix room ID
            content: Message content
            **kwargs: Additional options (format_as_markdown, etc.)
            
        Returns:
            Dict with success status and message details
        """
        if not await self.is_available():
            return {
                "status": "failure",
                "error": "Matrix service not available",
                "timestamp": time.time()
            }
        
        format_as_markdown = kwargs.get('format_as_markdown', True)
        
        try:
            # Format content if markdown is enabled
            if format_as_markdown:
                formatted = format_for_matrix(content)
                result = await self._observer.send_formatted_message(
                    channel_id, formatted["plain"], formatted["html"]
                )
            else:
                result = await self._observer.send_message(channel_id, content)
            
            if result.get("success"):
                event_id = result.get("event_id", "unknown")
                
                # Record the sent message in world state
                if self._world_state_manager:
                    from ...core.world_state.structures import Message
                    bot_message = Message(
                        id=event_id,
                        channel_id=channel_id,
                        channel_type="matrix",
                        sender=settings.MATRIX_USER_ID,
                        content=content,
                        timestamp=time.time(),
                        reply_to=None
                    )
                    self._world_state_manager.add_message(channel_id, bot_message)
                
                # Record in context manager
                if self._context_manager:
                    assistant_message = {
                        "event_id": event_id,
                        "sender": settings.MATRIX_USER_ID,
                        "content": content,
                        "timestamp": time.time(),
                        "type": "assistant"
                    }
                    await self._context_manager.add_assistant_message(channel_id, assistant_message)
                
                return {
                    "status": "success",
                    "message": f"Sent Matrix message to {channel_id}",
                    "event_id": event_id,
                    "room_id": channel_id,
                    "timestamp": time.time()
                }
            else:
                return {
                    "status": "failure",
                    "error": result.get("error", "Unknown error sending message"),
                    "timestamp": time.time()
                }
                
        except Exception as e:
            logger.error(f"Error sending Matrix message: {e}")
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time()
            }
    
    async def send_reply(self, channel_id: str, content: str, reply_to_id: str, **kwargs) -> Dict[str, Any]:
        """
        Send a reply to a specific message in a Matrix room.
        
        Args:
            channel_id: Matrix room ID
            content: Reply content
            reply_to_id: Event ID of the message to reply to
            **kwargs: Additional options
            
        Returns:
            Dict with success status and reply details
        """
        if not await self.is_available():
            return {
                "status": "failure",
                "error": "Matrix service not available",
                "timestamp": time.time()
            }
        
        # Deduplication check
        if self._world_state_manager and self._world_state_manager.has_bot_replied_to_matrix_event(reply_to_id):
            return {
                "status": "skipped",
                "message": f"Bot has already replied to Matrix event {reply_to_id}",
                "event_id": reply_to_id,
                "room_id": channel_id,
                "reason": "already_replied",
                "timestamp": time.time()
            }
        
        format_as_markdown = kwargs.get('format_as_markdown', True)
        
        try:
            # Format content if markdown is enabled
            if format_as_markdown:
                formatted = format_for_matrix(content)
                result = await self._observer.send_formatted_reply(
                    channel_id, reply_to_id, formatted["plain"], formatted["html"]
                )
            else:
                result = await self._observer.send_reply(channel_id, reply_to_id, content)
            
            if result.get("success"):
                event_id = result.get("event_id", "unknown")
                
                # Record the sent reply in world state
                if self._world_state_manager:
                    from ...core.world_state.structures import Message
                    bot_message = Message(
                        id=event_id,
                        channel_id=channel_id,
                        channel_type="matrix",
                        sender=settings.MATRIX_USER_ID,
                        content=content,
                        timestamp=time.time(),
                        reply_to=reply_to_id
                    )
                    self._world_state_manager.add_message(channel_id, bot_message)
                    
                    # Track that we've replied to this event
                    self._world_state_manager.track_bot_reply_to_matrix_event(reply_to_id, event_id)
                
                # Record in context manager
                if self._context_manager:
                    assistant_message = {
                        "event_id": event_id,
                        "sender": settings.MATRIX_USER_ID,
                        "content": content,
                        "timestamp": time.time(),
                        "type": "assistant",
                        "reply_to": reply_to_id
                    }
                    await self._context_manager.add_assistant_message(channel_id, assistant_message)
                
                return {
                    "status": "success",
                    "message": f"Sent Matrix reply to {channel_id}",
                    "event_id": event_id,
                    "room_id": channel_id,
                    "reply_to": reply_to_id,
                    "timestamp": time.time()
                }
            else:
                return {
                    "status": "failure",
                    "error": result.get("error", "Unknown error sending reply"),
                    "timestamp": time.time()
                }
                
        except Exception as e:
            logger.error(f"Error sending Matrix reply: {e}")
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time()
            }
    
    async def react_to_message(self, channel_id: str, event_id: str, reaction: str) -> Dict[str, Any]:
        """
        React to a message in a Matrix room.
        
        Args:
            channel_id: Matrix room ID
            event_id: Event ID of the message to react to
            reaction: Reaction emoji/text
            
        Returns:
            Dict with success status and reaction details
        """
        if not await self.is_available():
            return {
                "status": "failure",
                "error": "Matrix service not available",
                "timestamp": time.time()
            }
        
        try:
            result = await self._observer.react_to_message(channel_id, event_id, reaction)
            
            if result.get("success"):
                reaction_event_id = result.get("event_id", "unknown")
                
                # Record the reaction in world state
                if self._world_state_manager:
                    self._world_state_manager.record_matrix_reaction(
                        channel_id, event_id, reaction, reaction_event_id
                    )
                
                return {
                    "status": "success",
                    "message": f"Reacted to Matrix message {event_id} with {reaction}",
                    "reaction_event_id": reaction_event_id,
                    "room_id": channel_id,
                    "original_event_id": event_id,
                    "reaction": reaction,
                    "timestamp": time.time()
                }
            else:
                return {
                    "status": "failure",
                    "error": result.get("error", "Unknown error reacting to message"),
                    "timestamp": time.time()
                }
                
        except Exception as e:
            logger.error(f"Error reacting to Matrix message: {e}")
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time()
            }
    
    async def send_image(self, channel_id: str, image_url: str, caption: str = None, **kwargs) -> Dict[str, Any]:
        """
        Send an image to a Matrix room.
        
        Args:
            channel_id: Matrix room ID
            image_url: URL of the image to send
            caption: Optional caption for the image
            **kwargs: Additional options
            
        Returns:
            Dict with success status and image details
        """
        if not await self.is_available():
            return {
                "status": "failure",
                "error": "Matrix service not available",
                "timestamp": time.time()
            }
        
        try:
            result = await self._observer.send_image(channel_id, image_url, caption or "")
            
            if result.get("success"):
                event_id = result.get("event_id", "unknown")
                
                # Record the sent image in world state
                if self._world_state_manager:
                    from ...core.world_state.structures import Message
                    bot_message = Message(
                        id=event_id,
                        channel_id=channel_id,
                        channel_type="matrix",
                        sender=settings.MATRIX_USER_ID,
                        content=f"[Image] {caption or image_url}",
                        timestamp=time.time(),
                        reply_to=None,
                        attachments=[{"type": "image", "url": image_url}]
                    )
                    self._world_state_manager.add_message(channel_id, bot_message)
                
                return {
                    "status": "success",
                    "message": f"Sent image to Matrix room {channel_id}",
                    "event_id": event_id,
                    "room_id": channel_id,
                    "image_url": image_url,
                    "timestamp": time.time()
                }
            else:
                return {
                    "status": "failure",
                    "error": result.get("error", "Unknown error sending image"),
                    "timestamp": time.time()
                }
                
        except Exception as e:
            logger.error(f"Error sending Matrix image: {e}")
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time()
            }
    
    async def send_video(self, channel_id: str, video_url: str, caption: str = None, **kwargs) -> Dict[str, Any]:
        """
        Send a video to a Matrix room.
        
        Args:
            channel_id: Matrix room ID
            video_url: URL of the video to send
            caption: Optional caption for the video
            **kwargs: Additional options
            
        Returns:
            Dict with success status and video details
        """
        if not await self.is_available():
            return {
                "status": "failure",
                "error": "Matrix service not available",
                "timestamp": time.time()
            }
        
        try:
            result = await self._observer.send_video(channel_id, video_url, caption or "")
            
            if result.get("success"):
                event_id = result.get("event_id", "unknown")
                
                # Record the sent video in world state
                if self._world_state_manager:
                    from ...core.world_state.structures import Message
                    bot_message = Message(
                        id=event_id,
                        channel_id=channel_id,
                        channel_type="matrix",
                        sender=settings.MATRIX_USER_ID,
                        content=f"[Video] {caption or video_url}",
                        timestamp=time.time(),
                        reply_to=None,
                        attachments=[{"type": "video", "url": video_url}]
                    )
                    self._world_state_manager.add_message(channel_id, bot_message)
                
                return {
                    "status": "success",
                    "message": f"Sent video to Matrix room {channel_id}",
                    "event_id": event_id,
                    "room_id": channel_id,
                    "video_url": video_url,
                    "timestamp": time.time()
                }
            else:
                return {
                    "status": "failure",
                    "error": result.get("error", "Unknown error sending video"),
                    "timestamp": time.time()
                }
                
        except Exception as e:
            logger.error(f"Error sending Matrix video: {e}")
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time()
            }
