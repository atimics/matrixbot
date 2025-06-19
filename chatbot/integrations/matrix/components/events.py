"""
Matrix Event Handlers

Handles Matrix events including messages, invites, membership changes, and encryption errors.
"""

import logging
import time
from typing import Any, Dict, Optional

import httpx
from nio import MatrixRoom, RoomMessageImage, RoomMessageText

from ....core.world_state import Message, WorldStateManager
from .rooms import MatrixRoomManager

logger = logging.getLogger(__name__)


class MatrixEventHandler:
    """Handles Matrix events and updates world state."""
    
    def __init__(
        self, 
        world_state: WorldStateManager, 
        room_manager: MatrixRoomManager,
        user_id: str,
        arweave_client=None,
        processing_hub=None,
        channels_to_monitor: list = None
    ):
        self.world_state = world_state
        self.room_manager = room_manager
        self.user_id = user_id
        self.arweave_client = arweave_client
        self.processing_hub = processing_hub
        self.channels_to_monitor = channels_to_monitor or []
    
    async def handle_message(self, room: MatrixRoom, event, client=None):
        """Handle incoming Matrix messages and update room details."""
        # Skip our own messages
        logger.info(f"MatrixEventHandler: Comparing event.sender='{event.sender}' with user_id='{self.user_id}'")
        if event.sender == self.user_id:
            logger.info(f"MatrixEventHandler: Skipping own message from {event.sender}")
            return

        # Extract comprehensive room details
        room_details = self.room_manager.extract_room_details(room)

        # Auto-register room if not known
        existing_channel = self.world_state.get_channel(room.room_id, "matrix")
        if not existing_channel:
            logger.info(f"MatrixEventHandler: Auto-registering room {room.room_id}")
            self.room_manager.register_room(room.room_id, room_details)
        else:
            # Update existing room details
            self.room_manager.update_room_details(room.room_id, room_details)

        logger.debug(
            f"MatrixEventHandler: Processing message from {room.room_id} ({room.display_name})"
        )

        # Process message content
        content, image_urls_list = await self._process_message_content(event, client)
        
        # Create message object
        metadata = {
            "matrix_event_type": getattr(event, "msgtype", type(event).__name__)
        }
        
        # Add original filename to metadata for image messages if available
        if isinstance(event, RoomMessageImage) and hasattr(event, 'body') and event.body:
            metadata["original_filename"] = event.body
        
        message = Message(
            id=event.event_id,
            channel_id=room.room_id,
            channel_type="matrix",
            sender=event.sender,
            content=content,
            timestamp=time.time(),
            reply_to=None,  # TODO: Extract reply information if present
            image_urls=image_urls_list if image_urls_list else None,
            metadata=metadata,
        )

        # Add to world state
        self.world_state.add_message(room.room_id, message)

        log_content = content[:100] + "..." if len(content) > 100 else content
        if image_urls_list:
            log_content += f" [Image: {image_urls_list[0]}]"

        logger.info(
            f"MatrixEventHandler: New message in {room.display_name or room.room_id}: "
            f"{event.sender}: {log_content}"
        )

        # Generate triggers for processing hub if connected
        await self._generate_triggers(room, event, message)
    
    async def _process_message_content(self, event, client) -> tuple[str, list]:
        """Process message content and extract images."""
        image_urls_list = []
        content = ""

        # Handle image messages (detect by presence of URL attribute)
        if hasattr(event, 'url'):
            # Handle image messages
            mxc_uri = event.url
            if mxc_uri and client:  # Ensure client is available
                try:
                    # Check if client is authenticated
                    if not client.access_token:
                        logger.warning(
                            f"MatrixEventHandler: Client not authenticated, cannot download {mxc_uri}"
                        )
                    else:
                        # Use nio client's built-in download method which handles authentication
                        download_response = await client.download(mxc_uri)

                        if hasattr(download_response, "body") and download_response.body:
                            # Upload Matrix image data directly to Arweave for permanent access
                            original_filename = getattr(event, "body", "matrix_image.jpg")

                            # Use the content-type from download response if available
                            content_type = getattr(
                                download_response, "content_type", "image/jpeg"
                            )

                            if self.arweave_client:
                                try:
                                    upload_result = await self.arweave_client.upload_data(
                                        download_response.body,
                                        content_type=content_type,
                                        filename=original_filename,
                                    )

                                    if upload_result.get("success"):
                                        arweave_url = upload_result["url"]
                                        image_urls_list.append(arweave_url)
                                        logger.info(
                                            f"MatrixEventHandler: Uploaded Matrix image to Arweave: {arweave_url}"
                                        )
                                    else:
                                        logger.error(
                                            f"MatrixEventHandler: Failed to upload to Arweave: {upload_result}"
                                        )
                                except Exception as upload_error:
                                    logger.error(
                                        f"MatrixEventHandler: Error uploading to Arweave: {upload_error}"
                                    )
                            else:
                                logger.warning(
                                    "MatrixEventHandler: No Arweave client available for image upload"
                                )
                        else:
                            logger.warning(
                                f"MatrixEventHandler: Failed to download image from {mxc_uri}"
                            )

                except httpx.HTTPStatusError as e:
                    logger.error(f"MatrixEventHandler: HTTP error downloading {mxc_uri}: {e}")
                except Exception as e:
                    logger.error(f"MatrixEventHandler: Error processing image {mxc_uri}: {e}")

            # Get the original body (might be a caption or filename)
            original_body = getattr(event, "body", "")
            if original_body and original_body != mxc_uri:
                # Use the original body (might be a caption)
                content = original_body
            else:
                content = f"[Image: {original_filename if 'original_filename' in locals() else 'matrix_image.jpg'}]"

        elif isinstance(event, RoomMessageText):
            # Handle text messages
            content = event.body
        else:
            # Handle other message types
            content = getattr(event, "body", str(event.content))
        
        return content, image_urls_list
    
    async def _generate_triggers(self, room: MatrixRoom, event, message: Message):
        """Generate triggers for processing hub if connected."""
        if not self.processing_hub:
            return
            
        from ....core.orchestration.processing_hub import Trigger
        
        logger.debug(f"MatrixEventHandler: Checking trigger conditions for message from {event.sender}")
        
        # Check for bot mention
        bot_mentioned = self.user_id.lower() in event.body.lower() if hasattr(event, 'body') else False
        
        if bot_mentioned:
            logger.info(f"MatrixEventHandler: Bot mentioned in {room.room_id}")
            trigger = Trigger(
                trigger_type="mention",
                channel_id=room.room_id,
                channel_type="matrix",
                triggering_message_id=event.event_id,
                priority=1,  # High priority for mentions
                metadata={"mentioned_user": self.user_id}
            )
            await self.processing_hub.add_trigger(trigger)
        else:
            # Generate new message trigger with lower priority
            logger.debug(f"MatrixEventHandler: New message trigger for {room.room_id}")
            trigger = Trigger(
                trigger_type="new_message",
                channel_id=room.room_id,
                channel_type="matrix",
                triggering_message_id=event.event_id,
                priority=3,  # Lower priority for regular messages
            )
            await self.processing_hub.add_trigger(trigger)
    
    async def handle_invite(self, room, event):
        """Handle room invitations."""
        try:
            room_id = room.room_id
            inviter = event.sender
            
            logger.info(f"MatrixEventHandler: Received invite to {room_id} from {inviter}")
            
            # Register the invite in world state as a pending invite
            if hasattr(self.world_state, 'add_pending_matrix_invite'):
                invite_details = {
                    "room_id": room_id,
                    "inviter": inviter,
                    "room_name": getattr(room, 'name', None) or getattr(room, 'display_name', 'Unknown Room'),
                    "invited_at": time.time(),
                    "room_topic": getattr(room, 'topic', None),
                    "member_count": getattr(room, 'member_count', 0),
                }
                self.world_state.add_pending_matrix_invite(room_id, invite_details)
                
            logger.info(f"MatrixEventHandler: Added pending invite for room {room_id}")
            
        except Exception as e:
            logger.error(f"MatrixEventHandler: Error processing invite: {e}", exc_info=True)
    
    async def handle_membership_change(self, room, event):
        """Handle membership change events (join, leave, kick, ban)."""
        try:
            sender = event.sender
            membership = event.membership
            target = getattr(event, 'state_key', sender)  # Who the membership change affects
            room_id = room.room_id
            
            logger.info(
                f"MatrixEventHandler: Membership change in {room_id}: "
                f"{sender} -> {target} ({membership})"
            )
            
            # Handle bot's own membership changes
            if target == self.user_id:
                if membership == "leave":
                    # Bot left or was removed from room
                    reason = event.content.get("reason", "")
                    
                    # Check if it was voluntary (bot left) or involuntary (kicked/banned)
                    if sender == self.user_id:
                        status = "left"
                        logger.info(f"MatrixEventHandler: Bot left room {room_id}")
                    else:
                        # Check if it was a ban by looking at the event content
                        reason = event.content.get("reason", "")
                        if (
                            "ban" in reason.lower()
                            or event.content.get("membership") == "ban"
                        ):
                            status = "banned"
                            logger.warning(
                                f"MatrixEventHandler: Bot was banned from room {room_id} by {sender}. Reason: {reason}"
                            )
                        else:
                            status = "kicked"
                            logger.warning(
                                f"MatrixEventHandler: Bot was kicked from room {room_id} by {sender}. Reason: {reason}"
                            )

                    # Update world state
                    if hasattr(self.world_state, "update_channel_status"):
                        self.world_state.update_channel_status(room_id, status)

                    # Remove from monitoring if kicked/banned (but not if we left voluntarily)
                    if (
                        status in ["kicked", "banned"]
                        and room_id in self.channels_to_monitor
                    ):
                        self.channels_to_monitor.remove(room_id)
                        logger.info(
                            f"MatrixEventHandler: Removed {room_id} from monitoring due to {status}"
                        )

                elif membership == "join":
                    # Bot joined a room (usually handled by join/accept methods, but this catches edge cases)
                    logger.info(f"MatrixEventHandler: Bot joined room {room_id}")

                    # Ensure the channel is registered in the world state
                    existing_channel = self.world_state.get_channel(room_id, "matrix")
                    if not existing_channel:
                        room_details = self.room_manager.extract_room_details(room)
                        self.room_manager.register_room(room_id, room_details)

                    # Ensure room is in monitoring if not already
                    if room_id not in self.channels_to_monitor:
                        self.channels_to_monitor.append(room_id)

                    # Remove any pending invite for this room
                    if hasattr(self.world_state, "remove_pending_matrix_invite"):
                        self.world_state.remove_pending_matrix_invite(room_id)
                    if hasattr(self.world_state, "update_channel_status"):
                        self.world_state.update_channel_status(room_id, "joined")

                elif membership == "ban":
                    # Explicit ban event
                    status = "banned"
                    reason = event.content.get("reason", "")
                    logger.warning(
                        f"MatrixEventHandler: Bot was banned from room {room_id} by {sender}. Reason: {reason}"
                    )

                    # Update world state and remove from monitoring
                    if hasattr(self.world_state, "update_channel_status"):
                        self.world_state.update_channel_status(room_id, status)

                    if room_id in self.channels_to_monitor:
                        self.channels_to_monitor.remove(room_id)

        except Exception as e:
            logger.error(
                f"MatrixEventHandler: Error processing membership change: {e}",
                exc_info=True,
            )
    
    async def handle_encryption_error(self, room: MatrixRoom, event):
        """Handle Megolm decryption errors and other encryption issues."""
        try:
            room_id = room.room_id
            event_id = getattr(event, 'event_id', 'unknown')
            sender = getattr(event, 'sender', 'unknown')
            
            logger.warning(
                f"MatrixEventHandler: Encryption error in {room_id} "
                f"(event {event_id} from {sender}): Undecryptable Megolm event"
            )
            
            # Create a placeholder message indicating encryption failure
            error_message = Message(
                id=event_id,
                channel_id=room_id,
                channel_type="matrix",
                sender=sender,
                content="[Encrypted message - decryption failed]",
                timestamp=time.time(),
                reply_to=None,
                image_urls=None,
                metadata={
                    "matrix_event_type": "m.room.encrypted",
                    "encryption_error": True,
                    "error_type": "megolm_decryption_failed"
                },
            )
            
            # Add the error message to world state so AI is aware of missing content
            self.world_state.add_message(room_id, error_message)
            
            # TODO: Implement key recovery strategies:
            # 1. Request keys from other devices
            # 2. Check if keys become available later
            # 3. Mark room for key refresh
            
            logger.info(
                f"MatrixEventHandler: Added placeholder for undecryptable message in {room.display_name or room_id}"
            )
            
        except Exception as e:
            logger.error(f"MatrixEventHandler: Error handling encryption error: {e}", exc_info=True)
