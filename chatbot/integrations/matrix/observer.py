#!/usr/bin/env python3
"""
Matrix Observer

This module observes Matrix channels and updates the world state with new messages.
It's a simple observer that doesn't respond to messages directly.
"""

import asyncio
import logging
import os
import time
from typing import Optional, Dict, Any
from pathlib import Path
import json

from nio import AsyncClient, MatrixRoom, RoomMessageText, LoginResponse, RoomSendResponse, RoomSendError
from dotenv import load_dotenv

from ...core.world_state import WorldStateManager, Message, Channel

logger = logging.getLogger(__name__)
load_dotenv()

class MatrixObserver:
    """Observes Matrix channels and reports to world state"""
    
    def __init__(self, world_state_manager: WorldStateManager):
        self.world_state = world_state_manager
        self.homeserver = os.getenv("MATRIX_HOMESERVER")
        self.user_id = os.getenv("MATRIX_USER_ID")
        self.password = os.getenv("MATRIX_PASSWORD")
        self.client: Optional[AsyncClient] = None
        self.sync_task: Optional[asyncio.Task] = None
        self.channels_to_monitor = []
        
        # Create store directory for Matrix client data
        self.store_path = Path("matrix_store")
        self.store_path.mkdir(exist_ok=True)
        
        if not all([self.homeserver, self.user_id, self.password]):
            raise ValueError("Matrix configuration missing. Check MATRIX_HOMESERVER, MATRIX_USER_ID, and MATRIX_PASSWORD environment variables.")
        
        logger.info(f"MatrixObserver: Initialized for {self.user_id}@{self.homeserver}")
    
    def add_channel(self, channel_id: str, channel_name: str):
        """Add a channel to monitor"""
        self.channels_to_monitor.append(channel_id)
        self.world_state.add_channel(channel_id, "matrix", channel_name)
        logger.info(f"MatrixObserver: Added channel {channel_name} ({channel_id}) to monitoring")
    
    async def start(self):
        """Start the Matrix observer"""
        logger.info("MatrixObserver: Starting Matrix client...")
        
        # Create client with device configuration and store path
        device_name = os.getenv("DEVICE_NAME", "ratichat_bot")
        device_id = os.getenv("MATRIX_DEVICE_ID")
        
        self.client = AsyncClient(
            self.homeserver, 
            self.user_id,
            device_id=device_id,
            store_path=str(self.store_path)
        )
        
        # Set up event callbacks
        self.client.add_event_callback(self._on_message, RoomMessageText)
        
        try:
            # Try to load saved token
            if await self._load_token():
                logger.info("MatrixObserver: Using saved authentication token")
            else:
                # Login with password and device configuration
                logger.info("MatrixObserver: Logging in with password...")
                response = await self.client.login(
                    password=self.password,
                    device_name=device_name
                )
                if isinstance(response, LoginResponse):
                    logger.info(f"MatrixObserver: Login successful as {response.user_id}")
                    logger.info(f"MatrixObserver: Device ID: {response.device_id}")
                    await self._save_token()
                else:
                    logger.error(f"MatrixObserver: Login failed: {response}")
                    raise Exception(f"Login failed: {response}")
            
            # Update world state
            self.world_state.update_system_status({"matrix_connected": True})
            
            # Join channels we want to monitor
            for channel_id in self.channels_to_monitor:
                try:
                    response = await self.client.join(channel_id)
                    logger.info(f"MatrixObserver: Joined channel {channel_id}")
                    
                    # If we joined by alias, update our monitoring list with the real room ID
                    if hasattr(response, 'room_id') and response.room_id != channel_id:
                        logger.info(f"MatrixObserver: Room alias {channel_id} resolved to {response.room_id}")
                        # Add the real room ID to our world state
                        self.world_state.add_channel(response.room_id, "matrix", f"Room {response.room_id}")
                        
                except Exception as e:
                    logger.warning(f"MatrixObserver: Failed to join {channel_id}: {e}")
            
            # Start syncing in background task
            logger.info("MatrixObserver: Starting sync...")
            self.sync_task = asyncio.create_task(self._sync_forever())
            logger.info("MatrixObserver: Sync task started successfully")
            
        except Exception as e:
            logger.error(f"MatrixObserver: Error starting Matrix client: {e}")
            self.world_state.update_system_status({"matrix_connected": False})
            raise
    
    async def _on_message(self, room: MatrixRoom, event: RoomMessageText):
        """Handle incoming Matrix messages and update room details"""
        # Skip our own messages
        if event.sender == self.user_id:
            return
        
        # Extract comprehensive room details
        room_details = self._extract_room_details(room)
        
        # Auto-register room if not known
        if room.room_id not in self.world_state.state.channels:
            logger.info(f"MatrixObserver: Auto-registering room {room.room_id}")
            self._register_room(room.room_id, room_details)
        else:
            # Update existing room details
            self._update_room_details(room.room_id, room_details)
        
        logger.debug(f"MatrixObserver: Processing message from {room.room_id} ({room.display_name})")
        
        # Create message object
        message = Message(
            id=event.event_id,
            channel_id=room.room_id,
            channel_type="matrix",
            sender=event.sender,
            content=event.body,
            timestamp=time.time(),
            reply_to=None  # TODO: Extract reply information if present
        )
        
        # Add to world state
        self.world_state.add_message(room.room_id, message)
        
        logger.info(f"MatrixObserver: New message in {room.display_name or room.room_id}: "
                   f"{event.sender}: {event.body[:100]}...")
    
    def _extract_room_details(self, room: MatrixRoom) -> Dict[str, Any]:
        """Extract comprehensive details from a Matrix room"""
        return {
            "name": room.display_name or room.name or "Unnamed Room",
            "canonical_alias": getattr(room, 'canonical_alias', None),
            "alt_aliases": getattr(room, 'alt_aliases', []),
            "topic": getattr(room, 'topic', None),
            "avatar_url": getattr(room, 'avatar', None),
            "member_count": getattr(room, 'member_count', len(room.users)),
            "encrypted": getattr(room, 'encrypted', False),
            "public": getattr(room, 'join_rule', 'invite') == 'public',
            "power_levels": self._extract_power_levels(room),
            "creation_time": getattr(room, 'creation_time', None),
            "last_checked": time.time()
        }
    
    def _extract_power_levels(self, room: MatrixRoom) -> Dict[str, int]:
        """Extract user power levels from room"""
        power_levels = {}
        try:
            if hasattr(room, 'power_levels') and room.power_levels:
                for user_id, level in room.power_levels.users.items():
                    power_levels[user_id] = level
            # Add room members with default power level
            for user_id in room.users:
                if user_id not in power_levels:
                    power_levels[user_id] = 0
        except Exception as e:
            logger.debug(f"Error extracting power levels: {e}")
        return power_levels
    
    def _register_room(self, room_id: str, room_details: Dict[str, Any]):
        """Register a new room with the world state"""
        channel = Channel(
            id=room_id,
            type="matrix",
            name=room_details["name"],
            recent_messages=[],
            last_checked=room_details["last_checked"],
            canonical_alias=room_details["canonical_alias"],
            alt_aliases=room_details["alt_aliases"],
            topic=room_details["topic"],
            avatar_url=room_details["avatar_url"],
            member_count=room_details["member_count"],
            encrypted=room_details["encrypted"],
            public=room_details["public"],
            power_levels=room_details["power_levels"],
            creation_time=room_details["creation_time"]
        )
        
        self.world_state.state.channels[room_id] = channel
        logger.info(f"WorldState: Added matrix channel '{room_details['name']}' ({room_id})")
        
        # Log room details for AI context
        logger.info(f"  - Alias: {room_details['canonical_alias']}")
        logger.info(f"  - Members: {room_details['member_count']}")
        logger.info(f"  - Topic: {room_details['topic']}")
        logger.info(f"  - Encrypted: {room_details['encrypted']}")
    
    def _update_room_details(self, room_id: str, room_details: Dict[str, Any]):
        """Update existing room details"""
        if room_id in self.world_state.state.channels:
            channel = self.world_state.state.channels[room_id]
            channel.name = room_details["name"]
            channel.member_count = room_details["member_count"]
            channel.topic = room_details["topic"]
            channel.power_levels.update(room_details["power_levels"])
            channel.last_checked = room_details["last_checked"]
    
    async def _load_token(self) -> bool:
        """Load saved authentication token"""
        token_file = Path("matrix_token.json")
        if not token_file.exists():
            return False
        
        try:
            with open(token_file, 'r') as f:
                token_data = json.load(f)
            
            self.client.access_token = token_data["access_token"]
            self.client.user_id = token_data["user_id"]
            self.client.device_id = token_data["device_id"]
            
            # Verify token is still valid
            response = await self.client.whoami()
            if hasattr(response, 'user_id') and response.user_id:
                logger.info(f"MatrixObserver: Token verified for user {response.user_id}")
                return True
            else:
                logger.warning(f"MatrixObserver: Saved token is invalid: {response}")
                return False
                
        except Exception as e:
            logger.warning(f"MatrixObserver: Failed to load token: {e}")
            return False
    
    async def _save_token(self):
        """Save authentication token for reuse"""
        try:
            token_data = {
                "access_token": self.client.access_token,
                "user_id": self.client.user_id,
                "device_id": self.client.device_id,
                "homeserver": self.homeserver
            }
            
            with open("matrix_token.json", 'w') as f:
                json.dump(token_data, f, indent=2)
            
            # Set restrictive permissions
            os.chmod("matrix_token.json", 0o600)
            
            logger.info("MatrixObserver: Saved authentication token")
            
        except Exception as e:
            logger.error(f"MatrixObserver: Failed to save token: {e}")
    
    async def _sync_forever(self):
        """Background sync task that runs the Matrix client sync"""
        try:
            await self.client.sync_forever(timeout=30000, full_state=True)
        except Exception as e:
            logger.error(f"MatrixObserver: Sync error: {e}")
            self.world_state.update_system_status({"matrix_connected": False})
    
    async def stop(self):
        """Stop the Matrix observer"""
        if self.sync_task and not self.sync_task.done():
            logger.info("MatrixObserver: Cancelling sync task...")
            self.sync_task.cancel()
            try:
                await self.sync_task
            except asyncio.CancelledError:
                logger.info("MatrixObserver: Sync task cancelled")
        
        if self.client:
            await self.client.close()
            logger.info("MatrixObserver: Client closed")
        
        self.world_state.update_system_status({"matrix_connected": False})
    
    def get_room_details(self) -> Dict[str, Dict[str, Any]]:
        """Get comprehensive details of all monitored rooms for AI context"""
        room_details = {}
        
        if not self.client:
            return room_details
            
        try:
            for room_id, room in self.client.rooms.items():
                details = self._extract_room_details(room)
                details.update({
                    "room_id": room_id,
                    "is_monitoring": room_id in self.channels_to_monitor,
                    "user_list": list(room.users.keys()),
                    "last_message_time": max([msg.server_timestamp for msg in room.timeline.events if hasattr(msg, 'server_timestamp')], default=0)
                })
                room_details[room_id] = details
                
        except Exception as e:
            logger.error(f"Error getting room details: {e}")
            
        return room_details
    
    def get_user_details(self) -> Dict[str, Dict[str, Any]]:
        """Get details about users across all rooms for AI context"""
        user_details = {}
        
        if not self.client:
            return user_details
            
        try:
            for room_id, room in self.client.rooms.items():
                for user_id, user in room.users.items():
                    if user_id not in user_details:
                        user_details[user_id] = {
                            "user_id": user_id,
                            "display_name": getattr(user, 'display_name', None),
                            "avatar_url": getattr(user, 'avatar_url', None),
                            "rooms": [],
                            "power_levels": {}
                        }
                    
                    user_details[user_id]["rooms"].append(room_id)
                    if hasattr(room, 'power_levels') and room.power_levels:
                        if user_id in room.power_levels.users:
                            user_details[user_id]["power_levels"][room_id] = room.power_levels.users[user_id]
                        
        except Exception as e:
            logger.error(f"Error getting user details: {e}")
            
        return user_details
    
    async def send_message(self, room_id: str, content: str) -> Dict[str, Any]:
        """Send a message to a Matrix room"""
        if not self.client:
            return {"success": False, "error": "Matrix client not connected"}
        
        try:
            response = await self.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content={
                    "msgtype": "m.text",
                    "body": content
                }
            )
            
            if isinstance(response, RoomSendResponse):
                logger.info(f"MatrixObserver: Sent message to {room_id} (event: {response.event_id})")
                return {
                    "success": True,
                    "event_id": response.event_id,
                    "room_id": room_id
                }
            else:
                logger.error(f"MatrixObserver: Failed to send message: {response}")
                return {
                    "success": False,
                    "error": str(response)
                }
                
        except Exception as e:
            logger.error(f"MatrixObserver: Error sending message: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def send_reply(self, room_id: str, content: str, reply_to_event_id: str) -> Dict[str, Any]:
        """Send a reply to a specific message in a Matrix room"""
        logger.info(f"MatrixObserver.send_reply called: room_id={room_id}, content_length={len(content)}, reply_to={reply_to_event_id}")
        
        if not self.client:
            logger.error("Matrix client not connected")
            return {"success": False, "error": "Matrix client not connected"}
        
        # Validate message content and length
        if len(content) > 4000:  # Matrix has message size limits
            logger.warning(f"Message too long ({len(content)} chars), truncating...")
            content = content[:3997] + "..."
        
        try:
            # Format as a reply with Matrix reply formatting
            reply_content = {
                "msgtype": "m.text",
                "body": content,
                "m.relates_to": {
                    "m.in_reply_to": {
                        "event_id": reply_to_event_id
                    }
                }
            }
            
            logger.info(f"Sending reply with content: {reply_content}")
            
            # Add retry logic with exponential backoff
            max_retries = 3
            for attempt in range(max_retries):
                response = await self.client.room_send(
                    room_id=room_id,
                    message_type="m.room.message",
                    content=reply_content
                )
                
                logger.info(f"Matrix client room_send response (attempt {attempt + 1}): {response} (type: {type(response)})")
                
                if isinstance(response, RoomSendResponse):
                    logger.info(f"MatrixObserver: Sent reply to {room_id} (event: {response.event_id}, reply_to: {reply_to_event_id})")
                    return {
                        "success": True,
                        "event_id": response.event_id,
                        "room_id": room_id,
                        "reply_to_event_id": reply_to_event_id
                    }
                elif isinstance(response, RoomSendError):
                    # Enhanced error logging for RoomSendError
                    error_details = {
                        "message": getattr(response, 'message', 'unknown error'),
                        "status_code": getattr(response, 'status_code', None),
                        "retry_after_ms": getattr(response, 'retry_after_ms', None),
                        "transport_response": str(getattr(response, 'transport_response', None))
                    }
                    
                    logger.error(f"MatrixObserver: RoomSendError (attempt {attempt + 1}/{max_retries}): {error_details}")
                    
                    # Handle rate limiting
                    if error_details["retry_after_ms"]:
                        wait_time = error_details["retry_after_ms"] / 1000
                        logger.info(f"Rate limited, waiting {wait_time}s before retry")
                        await asyncio.sleep(wait_time)
                        continue
                    
                    # For other errors, wait with exponential backoff
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        logger.info(f"Waiting {wait_time}s before retry")
                        await asyncio.sleep(wait_time)
                        continue
                    
                    # Final attempt failed
                    return {
                        "success": False,
                        "error": f"RoomSendError: {error_details['message']} (Status: {error_details['status_code']})"
                    }
                else:
                    # Unknown response type
                    logger.error(f"MatrixObserver: Unknown response type: {type(response)}, value: {response}")
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        logger.info(f"Waiting {wait_time}s before retry")
                        await asyncio.sleep(wait_time)
                        continue
                    
                    return {
                        "success": False,
                        "error": f"Unknown response type: {type(response)} - {str(response)}"
                    }
            
            # Should not reach here, but just in case
            return {
                "success": False,
                "error": f"Failed after {max_retries} attempts"
            }
                
        except Exception as e:
            logger.error(f"MatrixObserver: Exception while sending reply: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Exception: {str(e)}"
            }
