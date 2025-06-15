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
    Service wrapper for Matrix integration that provides clean APIs for messaging and media operations.
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
        return (self._observer is not None and 
                hasattr(self._observer, 'client') and 
                self._observer.client is not None and
                hasattr(self._observer.client, 'access_token') and
                self._observer.client.access_token is not None)
    
    # === MessagingServiceInterface Implementation ===
    
    async def send_message(self, channel_id: str, content: str, **kwargs) -> Dict[str, Any]:
        """Send a message to a Matrix room"""
        try:
            if not await self.is_available():
                return {
                    "status": "failure",
                    "error": "Matrix service not available",
                    "timestamp": time.time()
                }
            
            # Format content for Matrix
            formatted_content = format_for_matrix(content)
            
            result = await self._observer.send_message(channel_id, formatted_content)
            
            if result.get("success"):
                return {
                    "status": "success",
                    "message": f"Successfully sent message to Matrix room {channel_id}",
                    "event_id": result.get("event_id"),
                    "content": formatted_content,
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
        """Send a reply to a specific message"""
        try:
            if not await self.is_available():
                return {
                    "status": "failure",
                    "error": "Matrix service not available",
                    "timestamp": time.time()
                }
            
            # Format content for Matrix
            formatted_content = format_for_matrix(content)
            
            result = await self._observer.send_reply(channel_id, formatted_content, reply_to_id)
            
            if result.get("success"):
                return {
                    "status": "success",
                    "message": f"Successfully sent reply in Matrix room {channel_id}",
                    "event_id": result.get("event_id"),
                    "reply_to": reply_to_id,
                    "content": formatted_content,
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
        """React to a message with an emoji"""
        try:
            if not await self.is_available():
                return {
                    "status": "failure",
                    "error": "Matrix service not available",
                    "timestamp": time.time()
                }
            
            result = await self._observer.react_to_message(channel_id, event_id, reaction)
            
            if result.get("success"):
                return {
                    "status": "success",
                    "message": f"Successfully reacted to message {event_id} in room {channel_id}",
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
    
    # === MediaServiceInterface Implementation ===
    
    async def send_image(self, channel_id: str, image_url: str, caption: str = None, **kwargs) -> Dict[str, Any]:
        """Send an image to a Matrix room"""
        try:
            if not await self.is_available():
                return {
                    "status": "failure",
                    "error": "Matrix service not available",
                    "timestamp": time.time()
                }
            
            # Get filename and content from kwargs
            filename = kwargs.get("filename")
            content = caption or kwargs.get("content")
            
            result = await self._observer.send_image(channel_id, image_url, filename, content)
            
            if result.get("success"):
                return {
                    "status": "success",
                    "message": f"Successfully sent image to Matrix room {channel_id}",
                    "event_id": result.get("event_id"),
                    "image_url": image_url,
                    "caption": content,
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
        """Send a video to a Matrix room"""
        try:
            if not await self.is_available():
                return {
                    "status": "failure",
                    "error": "Matrix service not available - video sending not yet implemented",
                    "timestamp": time.time()
                }
            
            # Video sending not yet implemented in Matrix observer
            # This would need to be added to the observer first
            return {
                "status": "failure",
                "error": "Video sending not yet implemented for Matrix",
                "timestamp": time.time()
            }
                
        except Exception as e:
            logger.error(f"Error sending Matrix video: {e}")
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time()
            }
    
    # === Additional Matrix-specific methods ===
    
    async def join_room(self, room_id: str) -> Dict[str, Any]:
        """
        Join a Matrix room.
        
        Args:
            room_id: Matrix room ID or alias to join
            
        Returns:
            Dict with success status and room details
        """
        if not await self.is_available():
            return {
                "status": "failure",
                "error": "Matrix service not available",
                "timestamp": time.time()
            }
        
        try:
            result = await self._observer.join_room(room_id)
            
            if result.get("success"):
                return {
                    "status": "success",
                    "message": f"Successfully joined Matrix room {room_id}",
                    "room_id": result.get("room_id", room_id),
                    "timestamp": time.time()
                }
            else:
                return {
                    "status": "failure",
                    "error": result.get("error", "Unknown error joining room"),
                    "timestamp": time.time()
                }
                
        except Exception as e:
            logger.error(f"Error joining Matrix room: {e}")
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time()
            }

    async def leave_room(self, room_id: str, reason: str = None) -> Dict[str, Any]:
        """
        Leave a Matrix room.
        
        Args:
            room_id: Matrix room ID to leave
            reason: Optional reason for leaving
            
        Returns:
            Dict with success status
        """
        if not await self.is_available():
            return {
                "status": "failure",
                "error": "Matrix service not available",
                "timestamp": time.time()
            }
        
        try:
            result = await self._observer.leave_room(room_id, reason)
            
            if result.get("success"):
                return {
                    "status": "success",
                    "message": f"Successfully left Matrix room {room_id}",
                    "room_id": room_id,
                    "timestamp": time.time()
                }
            else:
                return {
                    "status": "failure",
                    "error": result.get("error", "Unknown error leaving room"),
                    "timestamp": time.time()
                }
                
        except Exception as e:
            logger.error(f"Error leaving Matrix room: {e}")
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time()
            }

    async def accept_invite(self, room_id: str) -> Dict[str, Any]:
        """
        Accept a Matrix room invitation.
        
        Args:
            room_id: Matrix room ID to accept invitation for
            
        Returns:
            Dict with success status
        """
        if not await self.is_available():
            return {
                "status": "failure",
                "error": "Matrix service not available",
                "timestamp": time.time()
            }
        
        try:
            result = await self._observer.accept_invite(room_id)
            
            if result.get("success"):
                return {
                    "status": "success",
                    "message": f"Successfully accepted invitation to Matrix room {room_id}",
                    "room_id": room_id,
                    "timestamp": time.time()
                }
            else:
                return {
                    "status": "failure",
                    "error": result.get("error", "Unknown error accepting invite"),
                    "timestamp": time.time()
                }
                
        except Exception as e:
            logger.error(f"Error accepting Matrix room invite: {e}")
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time()
            }

    async def ignore_invite(self, room_id: str) -> Dict[str, Any]:
        """
        Ignore a Matrix room invitation.
        
        Args:
            room_id: Matrix room ID to ignore invitation for
            
        Returns:
            Dict with success status
        """
        if not await self.is_available():
            return {
                "status": "failure",
                "error": "Matrix service not available",
                "timestamp": time.time()
            }
        
        try:
            # Most Matrix clients don't have a specific "ignore invite" method
            # Instead, we'll just return success as ignoring is often passive
            # (not accepting is effectively ignoring)
            return {
                "status": "success",
                "message": f"Ignored invitation to Matrix room {room_id}",
                "room_id": room_id,
                "timestamp": time.time()
            }
                
        except Exception as e:
            logger.error(f"Error ignoring Matrix room invite: {e}")
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time()
            }
