"""
Matrix Integration Service

Service wrapper for Matrix platform integration.
Provides a clean service-oriented interface for Matrix communication.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional
import logging

from ..base_service import BaseIntegrationService, ServiceStatus
from ...core.world_state import Message
from .observer import MatrixObserver

logger = logging.getLogger(__name__)


class MatrixService(BaseIntegrationService):
    """
    Matrix integration service providing clean abstraction over Matrix observer.
    
    This service encapsulates Matrix-specific logic and provides standardized
    interfaces for messaging, channel management, and user interaction.
    """
    
    def __init__(self, service_id: str = "matrix_service", config: Dict[str, Any] = None,
                 world_state_manager=None, arweave_client=None):
        super().__init__(service_id, "matrix", config)
        self.world_state_manager = world_state_manager
        self.arweave_client = arweave_client
        self._matrix_observer: Optional[MatrixObserver] = None
        
    @property
    def enabled(self) -> bool:
        """Check if Matrix service is enabled and properly configured."""
        return (self._matrix_observer is not None and 
                self._matrix_observer.enabled)
    
    async def connect(self) -> bool:
        """Connect to Matrix server and initialize observer."""
        try:
            self._log_operation("Connecting to Matrix")
            
            # Create Matrix observer if not exists
            if not self._matrix_observer:
                self._matrix_observer = MatrixObserver(
                    integration_id=f"{self.service_id}_observer",
                    display_name="Matrix Observer",
                    config=self.config,
                    world_state_manager=self.world_state_manager,
                    arweave_client=self.arweave_client
                )
                self._set_observer(self._matrix_observer)
            
            # Connect the observer
            await self._matrix_observer.connect()
            
            self.is_connected = True
            self.connection_time = time.time()
            self.last_error = None
            
            self._log_operation("Connected successfully")
            return True
            
        except Exception as e:
            await self._handle_error(e, "Matrix connection failed")
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from Matrix server."""
        try:
            self._log_operation("Disconnecting from Matrix")
            
            if self._matrix_observer:
                await self._matrix_observer.disconnect()
            
            self.is_connected = False
            self.connection_time = None
            
            self._log_operation("Disconnected successfully")
            
        except Exception as e:
            await self._handle_error(e, "Matrix disconnection error")
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test Matrix connection without full initialization."""
        try:
            if not self._matrix_observer:
                return {"success": False, "error": "Matrix observer not initialized"}
                
            # Test connection through observer
            result = await self._matrix_observer.test_connection()
            return {"success": result, "error": None if result else "Connection test failed"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # === MESSAGING INTERFACE ===
    
    async def send_message(self, content: str, channel_id: str, **kwargs) -> Dict[str, Any]:
        """
        Send a message to a Matrix room.
        
        Args:
            content: Message content (supports Markdown)
            channel_id: Matrix room ID
            **kwargs: Additional options (reply_to, formatted_body, etc.)
            
        Returns:
            Dict with success status and message details
        """
        try:
            if not self.is_connected or not self._matrix_observer:
                return {"success": False, "error": "Not connected to Matrix"}
            
            self._log_operation(f"Sending message to {channel_id}")
            
            # Use observer's send_message method
            result = await self._matrix_observer.send_message(
                room_id=channel_id,
                content=content,
                **kwargs
            )
            
            return {"success": True, "message_id": result.get("event_id"), "details": result}
            
        except Exception as e:
            await self._handle_error(e, "Failed to send Matrix message")
            return {"success": False, "error": str(e)}
    
    async def reply_to_message(self, content: str, message_id: str, **kwargs) -> Dict[str, Any]:
        """
        Reply to a specific Matrix message.
        
        Args:
            content: Reply content
            message_id: Matrix event ID to reply to
            **kwargs: Additional options
            
        Returns:
            Dict with success status and reply details
        """
        try:
            if not self.is_connected or not self._matrix_observer:
                return {"success": False, "error": "Not connected to Matrix"}
            
            self._log_operation(f"Replying to message {message_id}")
            
            # Extract room_id from kwargs or determine from message context
            room_id = kwargs.get('room_id')
            if not room_id:
                return {"success": False, "error": "room_id required for Matrix replies"}
            
            # Use observer's reply functionality
            result = await self._matrix_observer.send_message(
                room_id=room_id,
                content=content,
                reply_to=message_id,
                **kwargs
            )
            
            return {"success": True, "reply_id": result.get("event_id"), "details": result}
            
        except Exception as e:
            await self._handle_error(e, "Failed to reply to Matrix message")
            return {"success": False, "error": str(e)}
    
    # === FEED OBSERVATION INTERFACE ===
    
    async def get_available_channels(self) -> List[Dict[str, Any]]:
        """
        Get list of Matrix rooms the bot can access.
        
        Returns:
            List of room info dicts with keys: id, name, type, description
        """
        try:
            if not self.is_connected or not self._matrix_observer:
                return []
            
            self._log_operation("Getting available Matrix rooms")
            
            # Get joined rooms from observer
            rooms = []
            if hasattr(self._matrix_observer, 'get_joined_rooms'):
                joined_rooms = await self._matrix_observer.get_joined_rooms()
                for room_id, room_info in joined_rooms.items():
                    rooms.append({
                        "id": room_id,
                        "name": room_info.get("display_name", room_id),
                        "type": "matrix_room",
                        "description": room_info.get("topic", "Matrix room"),
                        "member_count": room_info.get("member_count", 0),
                        "is_public": room_info.get("is_public", False)
                    })
            
            return rooms
        
        except Exception as e:
            await self._handle_error(e, "Failed to get Matrix channels")
            return []
    
    async def observe_channel_messages(self, channel_id: str, limit: int = 50) -> List[Message]:
        """
        Observe recent messages from a specific Matrix room.
        
        Args:
            channel_id: Matrix room ID
            limit: Maximum number of messages to retrieve
            
        Returns:
            List of Message objects
        """
        try:
            if not self.is_connected or not self._matrix_observer:
                return []
            
            self._log_operation(f"Observing messages from {channel_id}")
            
            # Use observer's message observation capability
            if hasattr(self._matrix_observer, 'get_room_messages'):
                messages = await self._matrix_observer.get_room_messages(channel_id, limit)
                return messages
            else:
                logger.warning("Matrix observer does not support room message retrieval")
                return []
                
        except Exception as e:
            await self._handle_error(e, f"Failed to observe Matrix channel {channel_id}")
            return []
    
    async def observe_all_feeds(self, feed_types: List[str] = None) -> Dict[str, List[Message]]:
        """
        Observe messages from Matrix rooms and feeds.
        
        Args:
            feed_types: List of feed types ('rooms', 'direct_messages', 'notifications')
            
        Returns:
            Dict mapping feed_type -> List[Message]
        """
        try:
            if not self.is_connected or not self._matrix_observer:
                return {}
            
            feed_types = feed_types or ['rooms', 'direct_messages']
            results = {}
            
            self._log_operation(f"Observing Matrix feeds: {feed_types}")
            
            for feed_type in feed_types:
                if feed_type == 'rooms':
                    # Get messages from all joined rooms
                    room_messages = []
                    available_channels = await self.get_available_channels()
                    for channel in available_channels:
                        messages = await self.observe_channel_messages(channel['id'], 20)
                        room_messages.extend(messages)
                    results['rooms'] = room_messages
                    
                elif feed_type == 'direct_messages':
                    # Get direct messages if observer supports it
                    if hasattr(self._matrix_observer, 'get_direct_messages'):
                        dm_messages = await self._matrix_observer.get_direct_messages()
                        results['direct_messages'] = dm_messages
                    else:
                        results['direct_messages'] = []
                        
                elif feed_type == 'notifications':
                    # Get notification messages if observer supports it
                    if hasattr(self._matrix_observer, 'get_notifications'):
                        notification_messages = await self._matrix_observer.get_notifications()
                        results['notifications'] = notification_messages
                    else:
                        results['notifications'] = []
            
            return results
            
        except Exception as e:
            await self._handle_error(e, "Failed to observe Matrix feeds")
            return {}
    
    # === USER INTERACTION INTERFACE ===
    
    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """
        Get information about a Matrix user.
        
        Args:
            user_id: Matrix user ID (@user:server.com)
            
        Returns:
            Dict with user information
        """
        try:
            if not self.is_connected or not self._matrix_observer:
                return {}
            
            self._log_operation(f"Getting Matrix user info for {user_id}")
            
            # Get user profile from observer if available
            if hasattr(self._matrix_observer, 'get_user_profile'):
                user_info = await self._matrix_observer.get_user_profile(user_id)
                return {
                    "user_id": user_id,
                    "display_name": user_info.get("displayname", user_id),
                    "avatar_url": user_info.get("avatar_url"),
                    "platform": "matrix"
                }
            else:
                return {
                    "user_id": user_id,
                    "display_name": user_id,
                    "platform": "matrix"
                }
                
        except Exception as e:
            await self._handle_error(e, f"Failed to get Matrix user info for {user_id}")
            return {"user_id": user_id, "platform": "matrix"}
    
    async def get_user_context(self, message: Message) -> Dict[str, Any]:
        """
        Get contextual information about a Matrix user from a message.
        
        Args:
            message: Message object
            
        Returns:
            Dict with user context information
        """
        try:
            if self._matrix_observer and hasattr(self._matrix_observer, 'get_user_context'):
                return self._matrix_observer.get_user_context(message)
            
            # Fallback context
            return {
                "user_id": message.sender_id,
                "display_name": getattr(message, 'sender_display_name', message.sender_id),
                "platform": "matrix",
                "room_id": message.channel_id,
                "engagement_level": "medium"  # Default for Matrix users
            }
            
        except Exception as e:
            await self._handle_error(e, "Failed to get Matrix user context")
            return {"user_id": message.sender_id, "platform": "matrix"}
    
    # === STATUS AND METRICS ===
    
    def _get_service_metrics(self) -> Dict[str, Any]:
        """Get Matrix service-specific metrics."""
        metrics = {
            "connected_rooms": 0,
            "sync_token": None,
            "last_sync_time": None,
            "homeserver": None
        }
        
        if self._matrix_observer:
            try:
                if hasattr(self._matrix_observer, 'client') and self._matrix_observer.client:
                    client = self._matrix_observer.client
                    metrics.update({
                        "homeserver": getattr(client, 'homeserver', None),
                        "user_id": getattr(client, 'user_id', None),
                        "device_id": getattr(client, 'device_id', None),
                        "sync_token": getattr(client, 'next_batch', None)
                    })
                    
                # Get room count
                metrics["connected_rooms"] = len(getattr(self._matrix_observer, 'channels_to_monitor', []))
                
            except Exception as e:
                logger.debug(f"Error getting Matrix metrics: {e}")
        
        return metrics
    
    # === MATRIX-SPECIFIC METHODS ===
    
    async def join_room(self, room_id: str, server_name: str = None) -> Dict[str, Any]:
        """
        Join a Matrix room.
        
        Args:
            room_id: Room ID or alias
            server_name: Optional server name for room aliases
            
        Returns:
            Dict with success status and room details
        """
        try:
            if not self.is_connected or not self._matrix_observer:
                return {"success": False, "error": "Not connected to Matrix"}
            
            self._log_operation(f"Joining Matrix room {room_id}")
            
            if hasattr(self._matrix_observer, 'join_room'):
                result = await self._matrix_observer.join_room(room_id, server_name)
                return {"success": True, "room_id": result.get("room_id"), "details": result}
            else:
                return {"success": False, "error": "Join room not supported"}
                
        except Exception as e:
            await self._handle_error(e, f"Failed to join Matrix room {room_id}")
            return {"success": False, "error": str(e)}
    
    async def leave_room(self, room_id: str) -> Dict[str, Any]:
        """
        Leave a Matrix room.
        
        Args:
            room_id: Room ID to leave
            
        Returns:
            Dict with success status
        """
        try:
            if not self.is_connected or not self._matrix_observer:
                return {"success": False, "error": "Not connected to Matrix"}
            
            self._log_operation(f"Leaving Matrix room {room_id}")
            
            if hasattr(self._matrix_observer, 'leave_room'):
                await self._matrix_observer.leave_room(room_id)
                return {"success": True}
            else:
                return {"success": False, "error": "Leave room not supported"}
                
        except Exception as e:
            await self._handle_error(e, f"Failed to leave Matrix room {room_id}")
            return {"success": False, "error": str(e)}
    
    def add_monitored_channel(self, channel_id: str, display_name: str = None) -> None:
        """Add a channel to monitoring list."""
        if self._matrix_observer:
            self._matrix_observer.add_channel(channel_id, display_name or channel_id)
            self._log_operation(f"Added channel {channel_id} to monitoring")
    
    def remove_monitored_channel(self, channel_id: str) -> None:
        """Remove a channel from monitoring list."""
        if self._matrix_observer and hasattr(self._matrix_observer, 'remove_channel'):
            self._matrix_observer.remove_channel(channel_id)
            self._log_operation(f"Removed channel {channel_id} from monitoring")
    
    def get_monitored_channels(self) -> List[str]:
        """Get list of monitored channel IDs."""
        if self._matrix_observer:
            return getattr(self._matrix_observer, 'channels_to_monitor', [])
        return []
