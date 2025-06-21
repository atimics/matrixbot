"""
Matrix Room Operations

Handles room-related operations like joining, leaving, accepting invites, and managing room state.
"""

import logging
from typing import Any, Dict, List, Optional

from nio import AsyncClient, JoinError, JoinResponse, RoomLeaveError, RoomLeaveResponse

from ....core.world_state import WorldStateManager
from .rooms import MatrixRoomManager

logger = logging.getLogger(__name__)


class MatrixRoomOperations:
    """Handles Matrix room operations."""
    
    def __init__(
        self, 
        client: AsyncClient, 
        user_id: str, 
        world_state: WorldStateManager,
        room_manager: MatrixRoomManager,
        channels_to_monitor: list = None
    ):
        self.client = client
        self.user_id = user_id
        self.world_state = world_state
        self.room_manager = room_manager
        self.channels_to_monitor = channels_to_monitor or []
    
    async def join_room(self, room_identifier: str) -> Dict[str, Any]:
        """Join a room by ID or alias."""
        try:
            if not self.client:
                return {"success": False, "error": "Matrix client not available"}
            
            logger.debug(f"MatrixRoomOps: Attempting to join room: {room_identifier}")
            
            response = await self.client.join(room_identifier)
            
            if isinstance(response, JoinResponse):
                room_id = response.room_id
                logger.info(f"MatrixRoomOps: Successfully joined room {room_id}")
                
                # Add to monitoring list
                if room_id not in self.channels_to_monitor:
                    self.channels_to_monitor.append(room_id)
                
                # Get room details and register in world state if we have access to the room
                if hasattr(self.client, 'rooms') and room_id in self.client.rooms:
                    room = self.client.rooms[room_id]
                    room_details = self.room_manager.extract_room_details(room)
                    self.room_manager.register_room(room_id, room_details)
                
                return {
                    "success": True,
                    "room_id": room_id,
                    "room_identifier": room_identifier
                }
            else:
                error_msg = f"Failed to join room: {response}"
                logger.error(f"MatrixRoomOps: {error_msg}")
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            error_msg = f"Error joining room {room_identifier}: {e}"
            logger.error(f"MatrixRoomOps: {error_msg}")
            return {"success": False, "error": error_msg}
    
    async def leave_room(
        self, 
        room_id: str, 
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Leave a room."""
        try:
            if not self.client:
                return {"success": False, "error": "Matrix client not available"}
            
            logger.debug(f"MatrixRoomOps: Attempting to leave room: {room_id}")
            
            response = await self.client.room_leave(room_id, reason)
            
            if isinstance(response, RoomLeaveResponse):
                logger.info(f"MatrixRoomOps: Successfully left room {room_id}")
                
                # Remove from monitoring list
                if room_id in self.channels_to_monitor:
                    self.channels_to_monitor.remove(room_id)
                
                # Update world state
                if hasattr(self.world_state, "update_channel_status"):
                    self.world_state.update_channel_status(room_id, "left")
                
                return {
                    "success": True,
                    "room_id": room_id,
                    "reason": reason
                }
            else:
                error_msg = f"Failed to leave room: {response}"
                logger.error(f"MatrixRoomOps: {error_msg}")
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            error_msg = f"Error leaving room {room_id}: {e}"
            logger.error(f"MatrixRoomOps: {error_msg}")
            return {"success": False, "error": error_msg}
    
    async def accept_invite(self, room_id: str) -> Dict[str, Any]:
        """Accept a room invitation."""
        try:
            if not self.client:
                return {"success": False, "error": "Matrix client not available"}
            
            logger.debug(f"MatrixRoomOps: Accepting invite for room: {room_id}")
            
            # Join the room (which accepts the invite)
            response = await self.client.join(room_id)
            
            if isinstance(response, JoinResponse):
                logger.info(f"MatrixRoomOps: Successfully accepted invite and joined {room_id}")
                
                # Add to monitoring list
                if room_id not in self.channels_to_monitor:
                    self.channels_to_monitor.append(room_id)
                
                # Remove from pending invites
                if hasattr(self.world_state, "remove_pending_matrix_invite"):
                    self.world_state.remove_pending_matrix_invite(room_id)
                
                # Get room details and register in world state
                if hasattr(self.client, 'rooms') and room_id in self.client.rooms:
                    room = self.client.rooms[room_id]
                    room_details = self.room_manager.extract_room_details(room)
                    self.room_manager.register_room(room_id, room_details)
                
                # Update channel status
                if hasattr(self.world_state, "update_channel_status"):
                    self.world_state.update_channel_status(room_id, "joined")
                
                return {
                    "success": True,
                    "room_id": room_id,
                    "action": "invite_accepted"
                }
            else:
                error_msg = f"Failed to accept invite: {response}"
                logger.error(f"MatrixRoomOps: {error_msg}")
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            error_msg = f"Error accepting invite for {room_id}: {e}"
            logger.error(f"MatrixRoomOps: {error_msg}")
            return {"success": False, "error": error_msg}
    
    async def get_invites(self) -> Dict[str, Any]:
        """Get list of pending room invitations."""
        try:
            invites = []
            
            # Get invites from Matrix client if available
            if self.client and hasattr(self.client, 'invited_rooms'):
                for room_id, room in self.client.invited_rooms.items():
                    invite_info = {
                        "room_id": room_id,
                        "room_name": getattr(room, 'name', None) or getattr(room, 'display_name', 'Unknown Room'),
                        "room_topic": getattr(room, 'topic', None),
                        "member_count": getattr(room, 'member_count', 0),
                        "source": "matrix_client"
                    }
                    invites.append(invite_info)
            
            # Also get invites from world state if available
            if hasattr(self.world_state, "get_pending_matrix_invites"):
                world_state_invites = self.world_state.get_pending_matrix_invites()
                for room_id, invite_details in world_state_invites.items():
                    # Avoid duplicates
                    if not any(inv["room_id"] == room_id for inv in invites):
                        invite_info = {
                            "room_id": room_id,
                            "room_name": invite_details.get("room_name", "Unknown Room"),
                            "room_topic": invite_details.get("room_topic"),
                            "member_count": invite_details.get("member_count", 0),
                            "inviter": invite_details.get("inviter"),
                            "invited_at": invite_details.get("invited_at"),
                            "source": "world_state"
                        }
                        invites.append(invite_info)
            
            logger.debug(f"MatrixRoomOps: Found {len(invites)} pending invites")
            return {
                "success": True,
                "invites": invites,
                "count": len(invites)
            }
            
        except Exception as e:
            error_msg = f"Error getting invites: {e}"
            logger.error(f"MatrixRoomOps: {error_msg}")
            return {"success": False, "error": error_msg}
    
    async def check_room_permissions(self, room_id: str) -> Dict[str, Any]:
        """Check the bot's permissions in a room."""
        try:
            if not self.client or not hasattr(self.client, 'rooms'):
                return {"success": False, "error": "Matrix client not available or no room data"}
            
            if room_id not in self.client.rooms:
                return {"success": False, "error": f"Room {room_id} not found in client rooms"}
            
            room = self.client.rooms[room_id]
            
            # Get bot's power level
            bot_power_level = 0
            if hasattr(room, 'power_levels') and room.power_levels:
                bot_power_level = room.power_levels.users.get(self.user_id, 0)
            
            # Check various permissions based on power level
            permissions = {
                "can_send_messages": bot_power_level >= 0,  # Usually 0 is required
                "can_send_media": bot_power_level >= 0,
                "can_invite_users": bot_power_level >= 50,  # Usually 50 is required
                "can_kick_users": bot_power_level >= 50,
                "can_ban_users": bot_power_level >= 50,
                "can_change_room_name": bot_power_level >= 50,
                "can_change_room_topic": bot_power_level >= 50,
                "can_change_room_avatar": bot_power_level >= 50,
                "is_admin": bot_power_level >= 100,
                "power_level": bot_power_level
            }
            
            # Additional room information
            room_info = {
                "room_id": room_id,
                "room_name": room.display_name or room.name or "Unnamed Room",
                "encrypted": getattr(room, "encrypted", False),
                "member_count": len(room.users),
                "is_public": getattr(room, "join_rule", "invite") == "public"
            }
            
            return {
                "success": True,
                "permissions": permissions,
                "room_info": room_info
            }
            
        except Exception as e:
            error_msg = f"Error checking room permissions for {room_id}: {e}"
            logger.error(f"MatrixRoomOps: {error_msg}")
            return {"success": False, "error": error_msg}
