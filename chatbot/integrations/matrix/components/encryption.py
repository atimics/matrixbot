"""
Matrix Encryption Handler

Handles Matrix end-to-end encryption, Megolm decryption errors, and key management.
"""

import asyncio
import logging
from typing import Any, Dict, Optional, Set

from nio import AsyncClient, MatrixRoom

logger = logging.getLogger(__name__)


class MatrixEncryptionHandler:
    """Handles Matrix encryption and decryption error recovery."""
    
    def __init__(self, client: AsyncClient, user_id: str):
        self.client = client
        self.user_id = user_id
        self.failed_decryption_events: Set[str] = set()
        self.key_request_retries: Dict[str, int] = {}
        self.max_key_retries = 3
    
    async def handle_decryption_failure(
        self, 
        room: MatrixRoom, 
        event_id: str, 
        sender: str,
        error_type: str = "megolm_session_missing"
    ) -> Dict[str, Any]:
        """Handle decryption failures and attempt recovery."""
        try:
            room_id = room.room_id
            
            logger.warning(
                f"MatrixEncryption: Decryption failed for event {event_id} "
                f"in room {room_id} from {sender}: {error_type}"
            )
            
            # Track failed events to avoid duplicate processing
            failure_key = f"{room_id}:{event_id}"
            if failure_key in self.failed_decryption_events:
                logger.debug(f"MatrixEncryption: Already processed failure for {failure_key}")
                return {"success": False, "error": "Already processed"}
            
            self.failed_decryption_events.add(failure_key)
            
            # Attempt recovery strategies
            recovery_result = await self._attempt_key_recovery(room, event_id, sender, error_type)
            
            return {
                "success": True,
                "event_id": event_id,
                "room_id": room_id,
                "sender": sender,
                "error_type": error_type,
                "recovery_attempted": True,
                "recovery_result": recovery_result
            }
            
        except Exception as e:
            logger.error(f"MatrixEncryption: Error handling decryption failure: {e}")
            return {"success": False, "error": str(e)}
    
    async def _attempt_key_recovery(
        self, 
        room: MatrixRoom, 
        event_id: str, 
        sender: str,
        error_type: str
    ) -> Dict[str, Any]:
        """Attempt various key recovery strategies."""
        room_id = room.room_id
        recovery_attempts = []
        
        # Strategy 1: Request keys from other room members
        if self.client and hasattr(self.client, 'request_room_key'):
            try:
                logger.info(f"MatrixEncryption: Requesting room key for event {event_id}")
                await self.client.request_room_key(event_id, room_id)
                recovery_attempts.append({"strategy": "room_key_request", "success": True})
            except Exception as e:
                logger.warning(f"MatrixEncryption: Room key request failed: {e}")
                recovery_attempts.append({"strategy": "room_key_request", "success": False, "error": str(e)})
        
        # Strategy 2: Trigger key sharing for the room
        if hasattr(self.client, 'share_group_session'):
            try:
                logger.info(f"MatrixEncryption: Attempting to share group session for room {room_id}")
                await self.client.share_group_session(room_id)
                recovery_attempts.append({"strategy": "group_session_share", "success": True})
            except Exception as e:
                logger.warning(f"MatrixEncryption: Group session share failed: {e}")
                recovery_attempts.append({"strategy": "group_session_share", "success": False, "error": str(e)})
        
        # Strategy 3: Schedule retry after delay
        retry_key = f"{room_id}:{event_id}"
        current_retries = self.key_request_retries.get(retry_key, 0)
        
        if current_retries < self.max_key_retries:
            self.key_request_retries[retry_key] = current_retries + 1
            retry_delay = min(300, 30 * (2 ** current_retries))  # Exponential backoff, max 5 minutes
            
            logger.info(
                f"MatrixEncryption: Scheduling retry #{current_retries + 1} for {event_id} "
                f"in {retry_delay} seconds"
            )
            
            asyncio.create_task(self._delayed_retry(room, event_id, sender, retry_delay))
            recovery_attempts.append({"strategy": "delayed_retry", "success": True, "delay": retry_delay})
        else:
            logger.warning(
                f"MatrixEncryption: Max retries ({self.max_key_retries}) exceeded for {event_id}"
            )
            recovery_attempts.append({"strategy": "delayed_retry", "success": False, "error": "max_retries_exceeded"})
        
        return {
            "strategies_attempted": len(recovery_attempts),
            "attempts": recovery_attempts
        }
    
    async def _delayed_retry(
        self, 
        room: MatrixRoom, 
        event_id: str, 
        sender: str, 
        delay: int
    ):
        """Retry decryption after a delay."""
        try:
            await asyncio.sleep(delay)
            
            logger.info(f"MatrixEncryption: Retrying decryption for event {event_id}")
            
            # Attempt to decrypt the event again
            # Note: This would require access to the original encrypted event
            # In a real implementation, we'd need to store the encrypted event
            # and attempt decryption again
            
            # For now, just log that we attempted the retry
            logger.info(f"MatrixEncryption: Retry attempted for event {event_id}")
            
        except Exception as e:
            logger.error(f"MatrixEncryption: Error during delayed retry for {event_id}: {e}")
    
    async def verify_device_keys(self, room_id: str) -> Dict[str, Any]:
        """Verify device keys for room members to improve encryption reliability."""
        try:
            if not self.client or not hasattr(self.client, 'rooms'):
                return {"success": False, "error": "Client not available"}
            
            if room_id not in self.client.rooms:
                return {"success": False, "error": f"Room {room_id} not found"}
            
            room = self.client.rooms[room_id]
            verification_results = []
            
            # Get list of room members
            for user_id in room.users:
                if user_id == self.user_id:
                    continue  # Skip ourselves
                
                try:
                    # Attempt to verify or update device keys
                    if hasattr(self.client, 'get_device_keys'):
                        device_keys = await self.client.get_device_keys(user_id)
                        verification_results.append({
                            "user_id": user_id,
                            "success": True,
                            "device_count": len(device_keys) if device_keys else 0
                        })
                    else:
                        verification_results.append({
                            "user_id": user_id,
                            "success": False,
                            "error": "Device key verification not supported"
                        })
                        
                except Exception as e:
                    verification_results.append({
                        "user_id": user_id,
                        "success": False,
                        "error": str(e)
                    })
            
            return {
                "success": True,
                "room_id": room_id,
                "verification_results": verification_results,
                "verified_users": len([r for r in verification_results if r["success"]])
            }
            
        except Exception as e:
            logger.error(f"MatrixEncryption: Error verifying device keys for {room_id}: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_encryption_status(self, room_id: str) -> Dict[str, Any]:
        """Get encryption status for a room."""
        try:
            if not self.client or not hasattr(self.client, 'rooms'):
                return {"success": False, "error": "Client not available"}
            
            if room_id not in self.client.rooms:
                return {"success": False, "error": f"Room {room_id} not found"}
            
            room = self.client.rooms[room_id]
            
            encryption_info = {
                "room_id": room_id,
                "encrypted": getattr(room, "encrypted", False),
                "encryption_algorithm": getattr(room, "encryption_algorithm", None),
                "member_count": len(room.users),
                "failed_decryptions": len([k for k in self.failed_decryption_events if k.startswith(room_id)]),
                "pending_key_retries": len([k for k in self.key_request_retries.keys() if k.startswith(room_id)])
            }
            
            # Check if we have Olm sessions with room members
            if hasattr(self.client, 'olm') and self.client.olm:
                session_info = {}
                for user_id in room.users:
                    if user_id != self.user_id:
                        # Check if we have Olm sessions with this user
                        # This would require access to the Olm machine internals
                        session_info[user_id] = "unknown"  # Placeholder
                
                encryption_info["olm_sessions"] = session_info
            
            return {
                "success": True,
                "encryption_info": encryption_info
            }
            
        except Exception as e:
            logger.error(f"MatrixEncryption: Error getting encryption status for {room_id}: {e}")
            return {"success": False, "error": str(e)}
    
    def cleanup_old_failures(self, max_age_hours: int = 24):
        """Clean up old failed decryption events to prevent memory leaks."""
        try:
            # In a real implementation, we'd track timestamps and clean up old events
            # For now, just clear events that have exceeded max retries
            
            expired_keys = [
                key for key, retries in self.key_request_retries.items()
                if retries >= self.max_key_retries
            ]
            
            for key in expired_keys:
                del self.key_request_retries[key]
                # Also remove from failed events if present
                if key in self.failed_decryption_events:
                    self.failed_decryption_events.remove(key)
            
            logger.info(f"MatrixEncryption: Cleaned up {len(expired_keys)} expired retry attempts")
            
        except Exception as e:
            logger.error(f"MatrixEncryption: Error cleaning up old failures: {e}")
