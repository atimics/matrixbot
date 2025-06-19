"""
Matrix Room Manager

Handles room details extraction, registration, and management operations.
"""

import logging
import time
from typing import Any, Dict, List

from nio import MatrixRoom

from ....core.world_state import Channel, WorldStateManager

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
    
    def register_room(self, room_id: str, room_details: Dict[str, Any]):
        """Register a room in the world state."""
        try:
            channel = Channel(
                id=room_id,
                name=room_details.get("name", "Unnamed Room"),
                channel_type="matrix",
                members=list(room_details.get("power_levels", {}).keys()),
                topic=room_details.get("topic"),
                metadata={
                    "canonical_alias": room_details.get("canonical_alias"),
                    "alt_aliases": room_details.get("alt_aliases", []),
                    "avatar_url": room_details.get("avatar_url"),
                    "member_count": room_details.get("member_count", 0),
                    "encrypted": room_details.get("encrypted", False),
                    "public": room_details.get("public", False),
                    "power_levels": room_details.get("power_levels", {}),
                    "creation_time": room_details.get("creation_time"),
                    "last_checked": room_details.get("last_checked"),
                }
            )
            
            self.world_state.add_channel(channel)
            logger.info(
                f"MatrixRoomManager: Registered room {room_id} "
                f"({room_details.get('name', 'Unnamed Room')})"
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
                existing_channel.members = list(room_details.get("power_levels", {}).keys())
                
                # Update metadata
                if existing_channel.metadata is None:
                    existing_channel.metadata = {}
                
                existing_channel.metadata.update({
                    "member_count": room_details.get("member_count", 0),
                    "encrypted": room_details.get("encrypted", False),
                    "power_levels": room_details.get("power_levels", {}),
                    "last_checked": room_details.get("last_checked"),
                })
                
                logger.debug(f"MatrixRoomManager: Updated room details for {room_id}")
            
        except Exception as e:
            logger.error(f"MatrixRoomManager: Error updating room {room_id}: {e}")
    
    def get_room_details(self) -> Dict[str, Dict[str, Any]]:
        """Get all room details from world state."""
        try:
            matrix_channels = self.world_state.get_channels_by_type("matrix")
            room_details = {}
            
            for channel in matrix_channels:
                room_details[channel.id] = {
                    "name": channel.name,
                    "topic": channel.topic,
                    "members": channel.members,
                    "metadata": channel.metadata or {}
                }
            
            return room_details
            
        except Exception as e:
            logger.error(f"MatrixRoomManager: Error getting room details: {e}")
            return {}
    
    def get_user_details(self) -> Dict[str, Dict[str, Any]]:
        """Get user details across all Matrix rooms."""
        try:
            matrix_channels = self.world_state.get_channels_by_type("matrix")
            user_details = {}
            
            # Aggregate user information from all rooms
            for channel in matrix_channels:
                if channel.metadata and "power_levels" in channel.metadata:
                    for user_id, power_level in channel.metadata["power_levels"].items():
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
