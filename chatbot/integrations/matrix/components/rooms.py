"""
Matrix Room Manager

Handles room details extraction, registration, and management operations.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from nio import MatrixRoom

from ....core.world_state import Channel, WorldStateManager
from ....core.world_state.data_structures.message import Message

logger = logging.getLogger(__name__)


class MatrixRoomManager:
    """Manages Matrix room operations and details."""
    
    def __init__(self, world_state: WorldStateManager):
        self.world_state = world_state
    
    def extract_room_details(self, room: MatrixRoom) -> Dict[str, Any]:
        """Extract comprehensive details from a Matrix room."""
        return {
            "name": room.display_name or room.name or "Unnamed Room",
            "canonical_alias": getattr(room, "canonical_alias", None),
            "alt_aliases": getattr(room, "alt_aliases", []),
            "topic": getattr(room, "topic", None),
            "avatar_url": getattr(room, "avatar", None),
            "member_count": getattr(room, "member_count", len(room.users)),
            "encrypted": getattr(room, "encrypted", False),
            "public": getattr(room, "join_rule", "invite") == "public",
            "power_levels": self.extract_power_levels(room),
            "creation_time": getattr(room, "creation_time", None),
            "last_checked": time.time(),
        }
    
    def extract_recent_messages(self, room: MatrixRoom, limit: int = 50) -> List[Message]:
        """Extract recent messages from room timeline."""
        messages = []
        try:
            if hasattr(room, 'timeline') and room.timeline:
                # Get timeline events and filter for text messages
                timeline_events = list(room.timeline.events)
                
                # Sort by server timestamp, most recent first
                timeline_events.sort(
                    key=lambda evt: getattr(evt, 'server_timestamp', 0), 
                    reverse=True
                )
                
                for event in timeline_events[:limit]:
                    try:
                        # Handle different event types
                        if hasattr(event, 'body') and hasattr(event, 'sender'):
                            # Regular message events
                            content = event.body
                            
                            # Handle formatted messages
                            if hasattr(event, 'formatted_body') and event.formatted_body:
                                content = event.formatted_body
                            
                            # Handle image/media events
                            if hasattr(event, 'url') and event.url:
                                if hasattr(event, 'body'):
                                    content = f"[{event.body}]"
                                else:
                                    content = "[Media]"
                            
                            message = Message(
                                id=getattr(event, 'event_id', f"unknown_{time.time()}"),
                                content=content,
                                author=event.sender,
                                timestamp=getattr(event, 'server_timestamp', time.time() * 1000) / 1000,
                                channel_id=room.room_id,
                                platform='matrix',
                                metadata={
                                    'event_type': getattr(event, '__class__', {}).get('__name__', 'unknown'),
                                    'encrypted': getattr(room, 'encrypted', False),
                                    'decryption_success': True  # If we can read the content, decryption worked
                                }
                            )
                            messages.append(message)
                            
                        elif hasattr(event, 'event_id'):
                            # Handle undecryptable events
                            logger.debug(f"MatrixRoomManager: Skipping non-text event {event.event_id} in {room.room_id}")
                            
                    except Exception as e:
                        logger.debug(f"MatrixRoomManager: Error processing timeline event in {room.room_id}: {e}")
                        continue
                
                logger.info(f"MatrixRoomManager: Extracted {len(messages)} messages from {room.room_id} timeline")
                
        except Exception as e:
            logger.warning(f"MatrixRoomManager: Error extracting messages from {room.room_id}: {e}")
        
        return messages
    
    def extract_power_levels(self, room: MatrixRoom) -> Dict[str, int]:
        """Extract user power levels from room."""
        power_levels = {}
        try:
            if hasattr(room, "power_levels") and room.power_levels:
                for user_id, level in room.power_levels.users.items():
                    power_levels[user_id] = level
            # Add room members with default power level
            for user_id in room.users:
                if user_id not in power_levels:
                    power_levels[user_id] = 0
        except Exception as e:
            logger.debug(f"MatrixRoomManager: Error extracting power levels: {e}")
        return power_levels
    
    def extract_recent_messages(self, room: MatrixRoom, limit: int = 50) -> List[Message]:
        """Extract recent messages from room timeline."""
        messages = []
        try:
            if hasattr(room, 'timeline') and room.timeline and hasattr(room.timeline, 'events'):
                # Get timeline events and filter for text messages
                timeline_events = list(room.timeline.events)
                
                # Sort by server timestamp, most recent first
                timeline_events.sort(
                    key=lambda evt: getattr(evt, 'server_timestamp', 0), 
                    reverse=True
                )
                
                for event in timeline_events[:limit]:
                    try:
                        # Handle different event types
                        if hasattr(event, 'body') and hasattr(event, 'sender'):
                            # Regular message events
                            content = event.body
                            
                            # Handle formatted messages
                            if hasattr(event, 'formatted_body') and event.formatted_body:
                                content = event.formatted_body
                            
                            # Handle image/media events
                            if hasattr(event, 'url') and event.url:
                                if hasattr(event, 'body'):
                                    content = f"[{event.body}]"
                                else:
                                    content = "[Media]"
                            
                            message = Message(
                                id=getattr(event, 'event_id', f"unknown_{time.time()}"),
                                content=content,
                                author=event.sender,
                                timestamp=getattr(event, 'server_timestamp', time.time() * 1000) / 1000,
                                channel_id=room.room_id,
                                platform='matrix',
                                metadata={
                                    'event_type': getattr(event, '__class__', {}).get('__name__', 'unknown'),
                                    'encrypted': getattr(room, 'encrypted', False),
                                    'decryption_success': True  # If we can read the content, decryption worked
                                }
                            )
                            messages.append(message)
                            
                        elif hasattr(event, 'event_id'):
                            # Handle undecryptable events
                            logger.debug(f"MatrixRoomManager: Skipping non-text event {event.event_id} in {room.room_id}")
                            
                    except Exception as e:
                        logger.debug(f"MatrixRoomManager: Error processing timeline event in {room.room_id}: {e}")
                        continue
                
                if messages:
                    logger.info(f"MatrixRoomManager: Extracted {len(messages)} messages from {room.room_id} timeline")
                else:
                    logger.debug(f"MatrixRoomManager: No readable messages found in {room.room_id} (may be encrypted or empty)")
                
        except Exception as e:
            logger.warning(f"MatrixRoomManager: Error extracting messages from {room.room_id}: {e}")
        
        return messages
    
    def register_room(self, room_id: str, room_details: Dict[str, Any], room: MatrixRoom = None):
        """Register a room in the world state with message history."""
        try:
            # Extract recent messages if room object is provided
            recent_messages = []
            if room:
                recent_messages = self.extract_recent_messages(room)
            
            channel = Channel(
                id=room_id,
                name=room_details.get("name", "Unnamed Room"),
                channel_type="matrix",
                topic=room_details.get("topic"),
                recent_messages=recent_messages,
                canonical_alias=room_details.get("canonical_alias"),
                alt_aliases=room_details.get("alt_aliases", []),
                avatar_url=room_details.get("avatar_url"),
                member_count=room_details.get("member_count", 0),
                encrypted=room_details.get("encrypted", False),
                public=room_details.get("public", False),
                power_levels=room_details.get("power_levels", {}),
                creation_time=room_details.get("creation_time"),
                last_checked=room_details.get("last_checked")
            )
            
            self.world_state.add_channel(channel)
            message_count = len(recent_messages)
            logger.info(
                f"MatrixRoomManager: Registered room {room_id} "
                f"({room_details.get('name', 'Unnamed Room')}) with {message_count} messages"
            )
            
        except Exception as e:
            logger.error(f"MatrixRoomManager: Error registering room {room_id}: {e}")
    
    def update_room_details(self, room_id: str, room_details: Dict[str, Any]):
        """Update existing room details in world state."""
        try:
            existing_channel = self.world_state.get_channel(room_id, "matrix")
            if existing_channel:
                # Update channel properties
                existing_channel.name = room_details.get("name", existing_channel.name)
                existing_channel.topic = room_details.get("topic", existing_channel.topic)
                existing_channel.member_count = room_details.get("member_count", existing_channel.member_count)
                existing_channel.encrypted = room_details.get("encrypted", existing_channel.encrypted)
                existing_channel.public = room_details.get("public", existing_channel.public)
                existing_channel.power_levels = room_details.get("power_levels", existing_channel.power_levels)
                existing_channel.canonical_alias = room_details.get("canonical_alias", existing_channel.canonical_alias)
                existing_channel.alt_aliases = room_details.get("alt_aliases", existing_channel.alt_aliases)
                existing_channel.avatar_url = room_details.get("avatar_url", existing_channel.avatar_url)
                
                logger.debug(f"MatrixRoomManager: Updated room details for {room_id}")
            
        except Exception as e:
            logger.error(f"MatrixRoomManager: Error updating room {room_id}: {e}")
    
    def get_room_details(self) -> Dict[str, Dict[str, Any]]:
        """Get all room details from world state."""
        try:
            # Access Matrix channels directly from the nested structure
            matrix_channels = self.world_state.state.channels.get("matrix", {})
            room_details = {}
            
            for channel_id, channel in matrix_channels.items():
                room_details[channel_id] = {
                    "name": channel.name,
                    "topic": channel.topic,
                    "member_count": channel.member_count,
                    "encrypted": channel.encrypted,
                    "public": channel.public,
                    "power_levels": channel.power_levels
                }
            
            return room_details
            
        except Exception as e:
            logger.error(f"MatrixRoomManager: Error getting room details: {e}")
            return {}
    
    def get_user_details(self) -> Dict[str, Dict[str, Any]]:
        """Get user details across all Matrix rooms."""
        try:
            # Access Matrix channels directly from the nested structure
            matrix_channels = self.world_state.state.channels.get("matrix", {})
            user_details = {}
            
            # Aggregate user information from all rooms
            for channel_id, channel in matrix_channels.items():
                if channel.power_levels:
                    for user_id, power_level in channel.power_levels.items():
                        if user_id not in user_details:
                            user_details[user_id] = {
                                "rooms": [],
                                "max_power_level": power_level,
                                "total_rooms": 0
                            }
                        
                        user_details[user_id]["rooms"].append({
                            "room_id": channel.id,
                            "room_name": channel.name,
                            "power_level": power_level
                        })
                        user_details[user_id]["max_power_level"] = max(
                            user_details[user_id]["max_power_level"], 
                            power_level
                        )
                        user_details[user_id]["total_rooms"] += 1
            
            return user_details
            
        except Exception as e:
            logger.error(f"MatrixRoomManager: Error getting user details: {e}")
            return {}
