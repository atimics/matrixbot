"""
Matrix Encryption Handler

Handles Matrix end-to-end encryption, Megolm decryption errors, and key management.
Enhanced with persistent retry queue and broadcast key requests.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional, Set, List

from nio import AsyncClient, MatrixRoom, MegolmEvent
from sqlmodel import select

# Import database models and manager
from ....core.persistence import DatabaseManager, UndecryptableEventRecord

logger = logging.getLogger(__name__)


class MatrixEncryptionHandler:
    """
    Handles Matrix encryption and decryption error recovery.
    
    Enhanced features:
    - Persistent retry queue using SQLModel database
    - Broadcast key requests to all room members
    - Improved key recovery strategies
    """
    
    def __init__(self, client: AsyncClient, user_id: str, db_manager: Optional[DatabaseManager] = None):
        self.client = client
        self.user_id = user_id
        self.failed_decryption_events: Set[str] = set()
        self.key_request_retries: Dict[str, int] = {}
        self.max_key_retries = 5  # Increased from 3
        
        # Database manager for persistent storage
        self.db_manager = db_manager or DatabaseManager()
        
        # Background task for periodic retry
        self._retry_task: Optional[asyncio.Task] = None
        self._start_retry_background_task()
    
    def _start_retry_background_task(self):
        """Start background task for periodic retry of undecryptable events."""
        if self._retry_task is None or self._retry_task.done():
            self._retry_task = asyncio.create_task(self._periodic_retry_loop())
    
    async def _periodic_retry_loop(self):
        """Periodically retry decryption of undecryptable events."""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                await self._retry_undecryptable_events()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"MatrixEncryption: Error in periodic retry loop: {e}")
                await asyncio.sleep(60)  # Wait a minute before retrying
    
    async def _retry_undecryptable_events(self):
        """Retry decryption for events in the persistent queue."""
        current_time = time.time()
        
        try:
            # Initialize database if needed
            if not self.db_manager._initialized:
                await self.db_manager.initialize()
            
            async with self.db_manager.get_session() as session:
                # Get events that need retrying
                query = select(UndecryptableEventRecord).where(
                    UndecryptableEventRecord.retry_count < UndecryptableEventRecord.max_retries,
                    UndecryptableEventRecord.last_retry_time < current_time - 300  # 5 minutes since last retry
                )
                
                result = await session.execute(query)
                events_to_retry = result.scalars().all()
                
                if events_to_retry:
                    logger.debug(f"MatrixEncryption: Retrying {len(events_to_retry)} undecryptable events")
                    
                    for event_record in events_to_retry:
                        await self._retry_event_decryption(session, event_record)
                    
                    await session.commit()
                    
        except Exception as e:
            logger.error(f"MatrixEncryption: Error retrying undecryptable events: {e}")
    
    async def _retry_event_decryption(self, session, event_record: UndecryptableEventRecord):
        """Retry decryption for a specific event."""
        try:
            event_record.retry_count += 1
            event_record.last_retry_time = time.time()
            
            # Broadcast key request to all room members
            await self._broadcast_key_request(event_record.room_id, event_record.sender)
            
            logger.debug(f"MatrixEncryption: Retry #{event_record.retry_count} for event {event_record.event_id}")
            
            # If we've exceeded max retries, remove from queue
            if event_record.retry_count >= event_record.max_retries:
                await session.delete(event_record)
                logger.debug(f"MatrixEncryption: Removed event {event_record.event_id} after {event_record.retry_count} retries")
            else:
                session.add(event_record)  # Update the record
                    
        except Exception as e:
            logger.error(f"MatrixEncryption: Error retrying event {event_record.event_id}: {e}")
    
    async def _broadcast_key_request(self, room_id: str, original_sender: str):
        """Broadcast key request to all verified devices of all room members."""
        try:
            if not self.client or not hasattr(self.client, 'rooms'):
                return
            
            if room_id not in self.client.rooms:
                return
            
            room = self.client.rooms[room_id]
            
            # Request keys from all room members, not just the original sender
            for user_id in room.users:
                if user_id == self.user_id:
                    continue  # Skip ourselves
                
                try:
                    # Request room key from this specific user
                    if hasattr(self.client, 'request_room_key'):
                        await self.client.request_room_key(room_id=room_id)
                    
                    # Also try to query their device keys
                    if hasattr(self.client, 'keys_query'):
                        await self.client.keys_query(user_keys={user_id: []})
                        
                except Exception as e:
                    logger.debug(f"MatrixEncryption: Failed to request keys from {user_id}: {e}")
            
            logger.debug(f"MatrixEncryption: Broadcast key request completed for room {room_id}")
            
        except Exception as e:
            logger.error(f"MatrixEncryption: Error broadcasting key request: {e}")
    
    async def handle_decryption_failure(
        self, 
        room: MatrixRoom, 
        event: MegolmEvent
    ) -> Dict[str, Any]:
        """
        Handle decryption failures and attempt recovery.
        Enhanced with persistent database queue and broadcast key requests.
        """
        try:
            room_id = room.room_id
            event_id = event.event_id
            sender = event.sender
            error_type = "megolm_undecryptable"  # From event type
            
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
            
            # Add to persistent database retry queue
            try:
                if not self.db_manager._initialized:
                    await self.db_manager.initialize()
                
                async with self.db_manager.get_session() as session:
                    # Check if event already exists in database
                    existing_query = select(UndecryptableEventRecord).where(
                        UndecryptableEventRecord.event_id == event_id,
                        UndecryptableEventRecord.room_id == room_id
                    )
                    existing_result = await session.execute(existing_query)
                    existing_event = existing_result.scalar_one_or_none()
                    
                    if not existing_event:
                        # Create new record
                        undecryptable_record = UndecryptableEventRecord(
                            event_id=event_id,
                            room_id=room_id,
                            sender=sender,
                            timestamp=time.time(),
                            error_type=error_type
                        )
                        session.add(undecryptable_record)
                        await session.commit()
                        logger.debug(f"MatrixEncryption: Added event {event_id} to persistent retry queue")
                    else:
                        logger.debug(f"MatrixEncryption: Event {event_id} already in retry queue")
                        
            except Exception as db_error:
                logger.error(f"MatrixEncryption: Error saving to database: {db_error}")
            
            # Immediate broadcast key request to all room members
            await self._broadcast_key_request(room_id, sender)
            
            # Attempt recovery strategies
            recovery_result = await self._attempt_key_recovery(room, event)
            
            return {
                "success": True,
                "event_id": event_id,
                "room_id": room_id,
                "sender": sender,
                "error_type": error_type,
                "recovery_attempted": True,
                "recovery_result": recovery_result,
                "added_to_retry_queue": True
            }
            
        except Exception as e:
            logger.error(f"MatrixEncryption: Error handling decryption failure: {e}")
            return {"success": False, "error": str(e)}
    
    async def _immediate_key_request(self, room_id: str, sender: str):
        """Immediately request keys for a failed decryption."""
        try:
            if not self.client:
                return
            
            # Request keys from the sender immediately
            if hasattr(self.client, 'request_room_key'):
                logger.debug(f"MatrixEncryption: Immediate key request for {room_id} from {sender}")
                await self.client.request_room_key(room_id=room_id)
            
            # Also try to start a key sharing session
            if hasattr(self.client, 'share_group_session'):
                await self.client.share_group_session(room_id)
                
        except Exception as e:
            logger.debug(f"MatrixEncryption: Immediate key request failed: {e}")

    async def _attempt_key_recovery(
        self, 
        room: MatrixRoom, 
        event: MegolmEvent
    ) -> Dict[str, Any]:
        """Attempt various key recovery strategies."""
        room_id = room.room_id
        event_id = event.event_id  # Extract for logging/retry key
        sender = event.sender  # Extract for logging/retry key
        recovery_attempts = []
        
        # Strategy 1: Request keys from other room members
        if self.client and hasattr(self.client, 'request_room_key'):
            try:
                logger.debug(f"MatrixEncryption: Requesting room key for event {event_id}")
                # Pass the full event object, not just the ID
                await self.client.request_room_key(event)
                recovery_attempts.append({"strategy": "room_key_request", "success": True})
            except Exception as e:
                logger.warning(f"MatrixEncryption: Room key request failed: {e}")
                recovery_attempts.append({"strategy": "room_key_request", "success": False, "error": str(e)})
        
        # Strategy 2: Share keys with room if we're able to
        if hasattr(self.client, 'share_group_session'):
            try:
                logger.debug(f"MatrixEncryption: Attempting to share group session for room {room_id}")
                await self.client.share_group_session(room_id, ignore_unverified_devices=True)
                recovery_attempts.append({"strategy": "group_session_share", "success": True})
            except Exception as e:
                logger.warning(f"MatrixEncryption: Group session share failed: {e}")
                recovery_attempts.append({"strategy": "group_session_share", "success": False, "error": str(e)})
        
        # Strategy 3: Trigger key exchange if supported
        if hasattr(self.client, 'keys_query'):
            try:
                # Query keys for the sender to potentially start key exchange
                # Pass the dictionary as a keyword argument, not a positional argument
                await self.client.keys_query(user_keys={sender: []})
                recovery_attempts.append({"strategy": "keys_query", "success": True})
            except Exception as e:
                logger.warning(f"MatrixEncryption: Keys query failed: {e}")
                recovery_attempts.append({"strategy": "keys_query", "success": False, "error": str(e)})
        
        # Strategy 4: Schedule retry after delay
        retry_key = f"{room_id}:{event_id}"
        current_retries = self.key_request_retries.get(retry_key, 0)
        
        if current_retries < self.max_key_retries:
            self.key_request_retries[retry_key] = current_retries + 1
            retry_delay = min(300, 30 * (2 ** current_retries))  # Exponential backoff, max 5 minutes
            
            logger.debug(
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
            
            logger.debug(f"MatrixEncryption: Retrying decryption for event {event_id}")
            
            # Attempt to decrypt the event again
            # Note: This would require access to the original encrypted event
            # In a real implementation, we'd need to store the encrypted event
            # and attempt decryption again
            
            # For now, just log that we attempted the retry
            logger.debug(f"MatrixEncryption: Retry attempted for event {event_id}")
            
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
            
            logger.debug(f"MatrixEncryption: Cleaned up {len(expired_keys)} expired retry attempts")
            
        except Exception as e:
            logger.error(f"MatrixEncryption: Error cleaning up old failures: {e}")
