#!/usr/bin/env python3
"""
Matrix Observer

This module observes Matrix channels and updates the world state with new messages.
It's a simple observer that doesn't respond to messages directly.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv
from nio import (
    AsyncClient,
    LoginResponse,
    MatrixRoom,
    RoomMessageImage,
    RoomMessageText,
    RoomSendError,
    RoomSendResponse,
)

from ...config import settings
from ...core.world_state import Channel, Message, WorldStateManager
from ..base import Integration, IntegrationError, IntegrationConnectionError
from ..base_observer import BaseObserver, ObserverStatus

logger = logging.getLogger(__name__)
load_dotenv()


class MatrixObserver(Integration, BaseObserver):
    """Observes Matrix channels and reports to world state"""

    def __init__(self, integration_id: str = "matrix", display_name: str = "Matrix Integration", 
                 config: Dict[str, Any] = None, world_state_manager: WorldStateManager = None, 
                 arweave_client=None):
        # Support positional usage: if first arg is not str, treat as world_state_manager
        if not isinstance(integration_id, str) and world_state_manager is None:
            # Shift positional parameters
            ws_manager = integration_id
            arw_client = display_name
            integration_id = "matrix"
            display_name = "Matrix Integration"
            config = config or {}
            world_state_manager = ws_manager
            arweave_client = arw_client
        
        Integration.__init__(self, integration_id, display_name, config or {})
        BaseObserver.__init__(self, integration_id, display_name)
        
        # Assign world state manager and optional Arweave client
        self.world_state = world_state_manager
        self.arweave_client = arweave_client
        self.homeserver = settings.MATRIX_HOMESERVER
        self.user_id = settings.MATRIX_USER_ID
        self.password = settings.MATRIX_PASSWORD
        self.client: Optional[AsyncClient] = None
        self.sync_task: Optional[asyncio.Task] = None
        self.channels_to_monitor = []
        
        # Processing hub connection for trigger generation
        self.processing_hub = None
        
        # Channel activity tracking to prevent spam responses
        self.channel_activity_triggers = {}  # channel_id -> timestamp of last trigger
        self.channel_response_cooldown = 300  # 5 minutes between triggers per channel

        # Create store directory for Matrix client data
        self.store_path = Path("matrix_store")
        self.store_path.mkdir(parents=True, exist_ok=True)
        
        # Check for Matrix configuration - disable if not available
        self._enabled = all([self.homeserver, self.user_id, self.password])
        if not self._enabled:
            error_msg = ("Matrix configuration incomplete. Check MATRIX_HOMESERVER, "
                        "MATRIX_USER_ID, and MATRIX_PASSWORD environment variables.")
            self._set_status(ObserverStatus.ERROR, error_msg)
            return

        self._set_status(ObserverStatus.DISCONNECTED)
        logger.info(f"MatrixObserver: Initialized for {self.user_id}@{self.homeserver}")
        logger.debug(f"MatrixObserver: User ID set to: '{self.user_id}' (type: {type(self.user_id)})")

    @property
    def enabled(self) -> bool:
        """Check if integration is enabled and properly configured."""
        return self._enabled

    @property
    def integration_type(self) -> str:
        """Return the integration type identifier."""
        return "matrix"

    async def connect(self, credentials: Optional[Dict[str, Any]] = None) -> bool:
        """Connect to Matrix server and start observing."""
        if not self.enabled:
            self._set_status(ObserverStatus.ERROR, "Matrix observer is disabled due to missing configuration")
            return False
            
        try:
            self._set_status(ObserverStatus.CONNECTING)
            self._increment_connection_attempts()
            
            logger.info("MatrixObserver: Starting Matrix client...")

            # Create client with device configuration and store path
            device_name = settings.DEVICE_NAME
            device_id = settings.MATRIX_DEVICE_ID

            self.client = AsyncClient(
                self.homeserver,
                self.user_id,
                device_id=device_id,
                store_path=str(self.store_path),
            )

            # Set up event callbacks
            self.client.add_event_callback(self._on_message, RoomMessageText)
            self.client.add_event_callback(self._on_message, RoomMessageImage)

            # Import required Matrix event types
            from nio import InviteMemberEvent, RoomMemberEvent

            self.client.add_event_callback(self._on_invite, InviteMemberEvent)
            self.client.add_event_callback(self._on_membership_change, RoomMemberEvent)

            # Try to load saved token with improved verification
            if await self._load_token():
                logger.info("MatrixObserver: Using saved authentication token")
            else:
                # Login with password and device configuration with retry logic
                logger.info("MatrixObserver: Logging in with password...")
                
                login_success = False
                max_login_attempts = 3
                
                for attempt in range(max_login_attempts):
                    try:
                        response = await self.client.login(
                            password=self.password, device_name=device_name
                        )
                        
                        if isinstance(response, LoginResponse):
                            logger.info(f"MatrixObserver: Login successful as {response.user_id}")
                            logger.info(f"MatrixObserver: Device ID: {response.device_id}")
                            
                            # Update our user_id with the actual value from the server
                            self.user_id = response.user_id
                            logger.info(f"MatrixObserver: Updated user_id to {self.user_id}")
                            
                            await self._save_token()
                            login_success = True
                            break
                        else:
                            logger.error(f"MatrixObserver: Login failed: {response}")
                            if attempt < max_login_attempts - 1:
                                wait_time = 2 ** attempt * 5  # 5, 10, 20 seconds
                                logger.info(f"MatrixObserver: Retrying login in {wait_time}s...")
                                await asyncio.sleep(wait_time)
                            continue
                            
                    except Exception as login_error:
                        error_str = str(login_error)
                        
                        # Handle rate limiting during login
                        if '429' in error_str or 'rate' in error_str.lower():
                            if attempt < max_login_attempts - 1:
                                wait_time = 60  # Wait 1 minute for rate limits
                                logger.warning(f"MatrixObserver: Login rate limited, waiting {wait_time}s...")
                                await asyncio.sleep(wait_time)
                                continue
                        
                        logger.error(f"MatrixObserver: Login attempt {attempt + 1} failed: {login_error}")
                        if attempt == max_login_attempts - 1:
                            raise login_error
                
                if not login_success:
                    raise IntegrationConnectionError("Failed to login after multiple attempts")

            # Update world state
            self.world_state.update_system_status({"matrix_connected": True})

            # Join channels we want to monitor
            for channel_id in self.channels_to_monitor:
                try:
                    response = await self.client.join(channel_id)
                    logger.info(f"MatrixObserver: Joined channel {channel_id}")

                    # If we joined by alias, update our monitoring list with the real room ID
                    if hasattr(response, "room_id") and response.room_id != channel_id:
                        logger.info(
                            f"MatrixObserver: Room alias {channel_id} resolved to {response.room_id}"
                        )
                        # Add the real room ID to our world state
                        self.world_state.add_channel(
                            response.room_id, "matrix", f"Room {response.room_id}"
                        )

                except Exception as e:
                    logger.warning(f"MatrixObserver: Failed to join {channel_id}: {e}")

            # Start syncing in background task
            logger.info("MatrixObserver: Starting sync...")
            self.sync_task = asyncio.create_task(self._sync_forever())
            logger.info("MatrixObserver: Sync task started successfully")
            
            self.is_connected = True
            self._set_status(ObserverStatus.CONNECTED)
            self._reset_connection_attempts()
            return True

        except Exception as e:
            error_msg = f"Failed to connect to Matrix: {e}"
            self._set_status(ObserverStatus.ERROR, error_msg)
            logger.error(f"MatrixObserver: Error starting Matrix client: {e}")
            self.world_state.update_system_status({"matrix_connected": False})
            return False

    async def disconnect(self) -> None:
        """Disconnect from Matrix server."""
        if not self.enabled:
            return
            
        logger.info("MatrixObserver: Disconnecting from Matrix...")
        
        try:
            if self.sync_task:
                self.sync_task.cancel()
                try:
                    await self.sync_task
                except asyncio.CancelledError:
                    pass
                self.sync_task = None
                
            if self.client:
                await self.client.close()
                self.client = None
                
            self.world_state.update_system_status({"matrix_connected": False})
            self.is_connected = False
            self._set_status(ObserverStatus.DISCONNECTED)
            logger.info("MatrixObserver: Disconnected from Matrix")
            
        except Exception as e:
            error_msg = f"Error during Matrix disconnect: {e}"
            self._set_status(ObserverStatus.ERROR, error_msg)
            logger.error(error_msg, exc_info=True)

    async def is_healthy(self) -> bool:
        """Check if the observer is healthy and operational."""
        if not self.enabled:
            return False
            
        if not self.client:
            return False
            
        if self.status != ObserverStatus.CONNECTED:
            return False
            
        try:
            # Test connectivity by checking if we have a valid access token
            return bool(self.client.access_token)
        except Exception as e:
            logger.warning(f"Matrix health check failed: {e}")
            return False

    async def get_status(self) -> Dict[str, Any]:
        """Get current status of the Matrix integration."""
        base_status = self.get_status_info()
        
        if not self.enabled:
            return {
                **base_status,
                "connected": False,
                "enabled": False,
                "error": "Missing configuration"
            }
            
        return {
            **base_status,
            "connected": self.is_connected,
            "enabled": self.enabled,
            "homeserver": self.homeserver,
            "user_id": self.user_id,
            "channels_monitored": len(self.channels_to_monitor),
            "sync_task_running": self.sync_task is not None and not self.sync_task.done()
        }

    async def test_connection(self) -> Dict[str, Any]:
        """Test if Matrix connection is working."""
        if not self.enabled:
            return {"success": False, "error": "Matrix integration disabled"}
            
        try:
            # Create a temporary client for testing
            test_client = AsyncClient(self.homeserver, self.user_id)
            
            # Try to login with credentials
            response = await test_client.login(password=self.password)
            
            if isinstance(response, LoginResponse):
                await test_client.close()
                return {"success": True, "message": "Connection test successful"}
            else:
                await test_client.close()
                return {"success": False, "error": f"Login failed: {response}"}
                
        except Exception as e:
            error_msg = f"Matrix connection test failed: {e}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}

    async def set_credentials(self, credentials: Dict[str, str]) -> None:
        """Set Matrix credentials."""
        required_keys = ["homeserver", "user_id", "password"]
        missing_keys = [key for key in required_keys if key not in credentials]
        if missing_keys:
            error_msg = f"Missing required credentials: {missing_keys}"
            self._set_status(ObserverStatus.ERROR, error_msg)
            self._enabled = False
            return
            
        try:
            self.homeserver = credentials["homeserver"]
            self.user_id = credentials["user_id"]
            self.password = credentials["password"]
            
            # Update enabled status
            self._enabled = all([self.homeserver, self.user_id, self.password])
            
            if self._enabled:
                self._clear_error()
                logger.info(f"Matrix credentials updated for {self.user_id}@{self.homeserver}")
            
        except Exception as e:
            error_msg = f"Failed to set Matrix credentials: {e}"
            self._set_status(ObserverStatus.ERROR, error_msg)
            self._enabled = False
            raise

    # Removed methods - use connect() and disconnect() instead

    async def _on_message(self, room: MatrixRoom, event):
        """Handle incoming Matrix messages and update room details"""
        # Ensure world_state is available
        if self.world_state is None:
            # Fallback to default WorldStateManager if not provided
            from ...core.world_state import WorldStateManager
            self.world_state = WorldStateManager()
        # Include all messages, including our own, for full conversation context
        logger.info(f"MatrixObserver: Processing message from sender='{event.sender}' (user_id='{self.user_id}')")

        # Extract comprehensive room details
        room_details = self._extract_room_details(room)

        # Auto-register room if not known
        existing_channel = self.world_state.get_channel(room.room_id, "matrix")
        if not existing_channel:
            logger.info(f"MatrixObserver: Auto-registering room {room.room_id}")
            self._register_room(room.room_id, room_details)
        else:
            # Update existing room details
            self._update_room_details(room.room_id, room_details)

        logger.debug(
            f"MatrixObserver: Processing message from {room.room_id} ({room.display_name})"
        )

        # Detect image URLs
        image_urls_list = []
        content = ""

        # Handle image messages (detect by presence of URL attribute)
        if hasattr(event, 'url'):
            # Handle image messages
            mxc_uri = event.url
            if mxc_uri and self.client:  # Ensure client is available
                try:
                    # Check if client is authenticated
                    if not self.client.access_token:
                        logger.warning(
                            f"MatrixObserver: Client not authenticated, cannot download {mxc_uri}"
                        )
                    else:
                        # Use nio client's built-in download method which handles authentication
                        download_response = await self.client.download(mxc_uri)

                        if hasattr(download_response, "body") and download_response.body:
                            # Upload Matrix image data directly to Arweave for permanent access
                            original_filename = getattr(event, "body", "matrix_image.jpg")

                            # Use the content-type from download response if available
                            content_type = getattr(
                                download_response, "content_type", "image/jpeg"
                            )

                            if self.arweave_client:
                                arweave_tx_id = await self.arweave_client.upload_data(
                                    download_response.body, content_type, tags={"source": "matrix"}
                                )
                                if arweave_tx_id:
                                    arweave_url = self.arweave_client.get_arweave_url(arweave_tx_id)
                                    image_urls_list.append(arweave_url)
                                    logger.info(
                                        f"MatrixObserver: Uploaded Matrix image to Arweave: {arweave_url}"
                                    )
                                else:
                                    logger.warning("Failed to upload Matrix media to Arweave, no URL available.")
                            else:
                                logger.warning("Arweave client not configured, cannot upload Matrix media.")
                        else:
                            # Enhanced error logging
                            error_type = type(download_response).__name__
                            error_details = getattr(download_response, 'message', str(download_response))
                            logger.warning(
                                f"MatrixObserver: Failed to download Matrix image {mxc_uri}: {error_type} - {error_details}"
                            )
                            
                            # Try alternative approach with HTTP conversion
                            try:
                                http_url = await self.client.mxc_to_http(mxc_uri)
                                if http_url:
                                    image_urls_list.append(http_url)
                                    logger.info(
                                        f"MatrixObserver: Using HTTP fallback URL: {http_url}"
                                    )
                            except Exception as convert_error:
                                logger.warning(
                                    f"MatrixObserver: MXC to HTTP conversion also failed: {convert_error}"
                                )
                except Exception as e:
                    logger.error(
                        f"MatrixObserver: Failed to process Matrix image {mxc_uri}: {e}"
                    )

            # For image messages, enhance content to reduce AI confusion
            original_body = getattr(event, "body", "Image")
            
            # Check if the body looks like just a filename
            if original_body and any(original_body.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg']):
                # Store the filename in metadata and use a generic content
                content = "[Image]"
                image_filename = original_body
            else:
                # Use the original body (might be a caption)
                content = original_body
                image_filename = None

        elif isinstance(event, RoomMessageText):
            # Handle text messages
            content = event.body
        else:
            # Handle other message types
            content = getattr(event, "body", str(event.content))

        # Create message object
        metadata = {
            "matrix_event_type": getattr(event, "msgtype", type(event).__name__)
        }
        
        # Add original filename to metadata for image messages if available
        if isinstance(event, RoomMessageImage) and 'image_filename' in locals() and image_filename:
            metadata["original_filename"] = image_filename
        
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
            f"MatrixObserver: New message in {room.display_name or room.room_id}: "
            f"{event.sender}: {log_content}"
        )

        # Generate triggers for processing hub if connected
        if self.processing_hub:
            from ...core.orchestration.processing_hub import Trigger
            
            logger.debug(f"MatrixObserver: Checking trigger conditions for message from {event.sender}")
            logger.debug(f"MatrixObserver: self.user_id = '{self.user_id}', content = '{content[:100]}'")
            
            # Skip trigger generation for the bot's own messages - CRITICAL SELF-LOOP PREVENTION
            # This prevents the bot from triggering processing cycles on its own automated messages
            is_bot_message = event.sender == self.user_id
            
            if is_bot_message:
                logger.debug(f"MatrixObserver: Skipping trigger generation for bot's own message (sender: {event.sender})")
                return
            
            # Check for direct mention from OTHER users only (since we already filtered out bot's own messages)
            has_mention = self.user_id and self.user_id in content
            
            if has_mention:
                logger.info(f"MatrixObserver: Direct mention detected for {self.user_id} from {event.sender}: {content[:50]}...")
                trigger = Trigger(
                    type='mention',
                    priority=9,
                    data={'channel_id': room.room_id, 'message_id': event.event_id, 'sender': event.sender}
                )
                self.processing_hub.add_trigger(trigger)
                logger.info(f"MatrixObserver: Added mention trigger to processing hub")
            # Check if it's an actively monitored ("expanded") channel (only if not a mention)
            elif self.world_state.is_channel_expanded(room.room_id, "matrix"):
                # Check if bot has recently responded to this channel to avoid spam
                should_trigger = self._should_trigger_for_channel_activity(room.room_id, event.sender)
                
                if should_trigger:
                    logger.info(f"MatrixObserver: New message in expanded channel {room.room_id} - triggering response")
                    trigger = Trigger(
                        type='channel_activity', 
                        priority=6,  # Lower priority than mentions
                        data={'channel_id': room.room_id, 'message_id': event.event_id, 'sender': event.sender}
                    )
                    self.processing_hub.add_trigger(trigger)
                    logger.info(f"MatrixObserver: Added channel_activity trigger to processing hub")
                    
                    # Mark that we've triggered for this channel
                    self._mark_channel_activity_trigger(room.room_id)
                else:
                    logger.debug(f"MatrixObserver: Skipping trigger for channel {room.room_id} - recent bot activity detected")
            else:
                # Message is in a non-active channel. Just log it, don't trigger a full cycle.
                logger.debug(f"MatrixObserver: Message in non-expanded channel {room.room_id}, no trigger generated.")
                # Let's also debug why it's not expanded
                is_expanded = self.world_state.is_channel_expanded(room.room_id, "matrix")
                logger.debug(f"MatrixObserver: Channel {room.room_id} is_expanded = {is_expanded}")
        else:
            logger.warning(f"MatrixObserver: No processing_hub connected, cannot generate triggers")
    async def _on_invite(self, room, event):
        """Handle incoming Matrix room invites"""
        from nio import InviteMemberEvent

        # Check if this is an invite for our user
        if not isinstance(event, InviteMemberEvent):
            return

        if event.state_key != self.user_id or event.membership != "invite":
            return

        logger.info(
            f"MatrixObserver: Received room invite for {room.room_id} from {event.sender}"
        )

        try:
            # Create invite info for world state
            invite_info = {
                "room_id": room.room_id,
                "inviter": event.sender,
                "room_name": getattr(room, "display_name", None)
                or getattr(room, "name", None)
                or getattr(room, "canonical_alias", None)
                or "Unknown Room",
                "timestamp": time.time(),
                # InviteMemberEvent doesn't have event_id, use a combination of room_id and timestamp
                "event_id": f"invite_{room.room_id}_{int(time.time() * 1000)}",
            }

            # Add to world state manager
            if hasattr(self, "world_state") and self.world_state:
                self.world_state.add_pending_matrix_invite(invite_info)
                logger.info(
                    f"MatrixObserver: Added pending invite to world state: {invite_info}"
                )
            else:
                logger.warning(
                    "MatrixObserver: No world state manager available for invite"
                )

        except Exception as e:
            logger.error(f"MatrixObserver: Error processing invite: {e}", exc_info=True)

    async def _on_membership_change(self, room, event):
        """Handle Matrix room membership changes (joins, leaves, kicks, bans)"""
        from nio import RoomMemberEvent

        if not isinstance(event, RoomMemberEvent):
            return

        # Only track changes involving our bot user
        if event.state_key != self.user_id:
            return

        room_id = room.room_id
        membership = event.membership
        sender = event.sender

        logger.info(
            f"MatrixObserver: Membership change in {room_id}: {membership} by {sender}"
        )

        try:
            if membership == "leave":
                # Determine if this was a self-leave, kick, or ban
                if sender == self.user_id:
                    # Self-initiated leave
                    status = "left_by_bot"
                    logger.info(f"MatrixObserver: Bot left room {room_id} voluntarily")
                else:
                    # Check if it was a ban by looking at the event content
                    reason = event.content.get("reason", "")
                    if (
                        "ban" in reason.lower()
                        or event.content.get("membership") == "ban"
                    ):
                        status = "banned"
                        logger.warning(
                            f"MatrixObserver: Bot was banned from room {room_id} by {sender}. Reason: {reason}"
                        )
                    else:
                        status = "kicked"
                        logger.warning(
                            f"MatrixObserver: Bot was kicked from room {room_id} by {sender}. Reason: {reason}"
                        )

                # Update world state
                if hasattr(self, "world_state") and self.world_state:
                    self.world_state.update_channel_status(room_id, status)

                # Remove from monitoring if kicked/banned (but not if we left voluntarily)
                if (
                    status in ["kicked", "banned"]
                    and room_id in self.channels_to_monitor
                ):
                    self.channels_to_monitor.remove(room_id)
                    logger.info(
                        f"MatrixObserver: Removed {room_id} from monitoring due to {status}"
                    )

            elif membership == "join":
                # Bot joined a room (usually handled by join/accept methods, but this catches edge cases)
                logger.info(f"MatrixObserver: Bot joined room {room_id}")

                # Ensure the channel is registered in the world state
                existing_channel = self.world_state.get_channel(room_id, "matrix")
                if not existing_channel:
                    room_details = self._extract_room_details(room)
                    self._register_room(room_id, room_details)

                # Ensure room is in monitoring if not already
                if room_id not in self.channels_to_monitor:
                    self.channels_to_monitor.append(room_id)

                # Remove any pending invite for this room
                if hasattr(self, "world_state") and self.world_state:
                    self.world_state.remove_pending_matrix_invite(room_id)
                    self.world_state.update_channel_status(room_id, "joined")

            elif membership == "ban":
                # Explicit ban event
                status = "banned"
                reason = event.content.get("reason", "")
                logger.warning(
                    f"MatrixObserver: Bot was banned from room {room_id} by {sender}. Reason: {reason}"
                )

                # Update world state and remove from monitoring
                if hasattr(self, "world_state") and self.world_state:
                    self.world_state.update_channel_status(room_id, status)

                if room_id in self.channels_to_monitor:
                    self.channels_to_monitor.remove(room_id)

        except Exception as e:
            logger.error(
                f"MatrixObserver: Error processing membership change: {e}",
                exc_info=True,
            )

    def _extract_room_details(self, room: MatrixRoom) -> Dict[str, Any]:
        """Extract comprehensive details from a Matrix room"""
        return {
            "name": room.display_name or room.name or "Unnamed Room",
            "canonical_alias": getattr(room, "canonical_alias", None),
            "alt_aliases": getattr(room, "alt_aliases", []),
            "topic": getattr(room, "topic", None),
            "avatar_url": getattr(room, "avatar", None),
            "member_count": getattr(room, "member_count", len(room.users)),
            "encrypted": getattr(room, "encrypted", False),
            "public": getattr(room, "join_rule", "invite") == "public",
            "power_levels": self._extract_power_levels(room),
            "creation_time": getattr(room, "creation_time", None),
            "last_checked": time.time(),
        }

    def _extract_power_levels(self, room: MatrixRoom) -> Dict[str, int]:
        """Extract user power levels from room"""
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
            creation_time=room_details["creation_time"],
        )

        # Use WorldStateManager's add_channel method to handle nested structure correctly
        self.world_state.add_channel(channel)
        logger.info(
            f"WorldState: Added matrix channel '{room_details['name']}' ({room_id})"
        )

        # Log room details for AI context
        logger.info(f"  - Alias: {room_details['canonical_alias']}")
        logger.info(f"  - Members: {room_details['member_count']}")
        logger.info(f"  - Topic: {room_details['topic']}")
        logger.info(f"  - Encrypted: {room_details['encrypted']}")

    def _update_room_details(self, room_id: str, room_details: Dict[str, Any]):
        """Update existing room details"""
        channel = self.world_state.get_channel(room_id, "matrix")
        if channel:
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
            with open(token_file, "r") as f:
                token_data = json.load(f)

            self.client.access_token = token_data["access_token"]
            self.client.user_id = token_data["user_id"]
            self.client.device_id = token_data["device_id"]

            # Verify token is still valid with improved error handling
            return await self._verify_token_with_backoff()

        except Exception as e:
            logger.warning(f"MatrixObserver: Failed to load token: {e}")
            return False

    async def _verify_token_with_backoff(self, max_retries: int = 3) -> bool:
        """Verify token with exponential backoff for rate limiting"""
        for attempt in range(max_retries):
            try:
                response = await self.client.whoami()
                if hasattr(response, "user_id") and response.user_id:
                    logger.info(f"MatrixObserver: Token verified for user {response.user_id}")
                    return True
                else:
                    logger.warning(f"MatrixObserver: Token verification returned invalid response: {response}")
                    return False
                    
            except Exception as whoami_error:
                error_str = str(whoami_error)
                
                # Check for authentication errors that indicate invalid token
                if any(auth_error in error_str.lower() for auth_error in [
                    'm_unknown_token', 'm_forbidden', 'unauthorized', 'invalid_token'
                ]):
                    logger.error(f"MatrixObserver: Token is invalid/expired: {whoami_error}")
                    return False
                
                # Check for rate limiting
                if '429' in error_str or 'rate' in error_str.lower():
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt * 5  # 5, 10, 20 seconds
                        logger.info(f"MatrixObserver: Rate limited during token verification, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.warning(f"MatrixObserver: Rate limited during token verification, assuming token is valid")
                        return True
                
                # For other errors (network, etc.), retry with backoff
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"MatrixObserver: Token verification failed (attempt {attempt + 1}/{max_retries}): {whoami_error}")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # On final attempt, assume token might be valid but server is having issues
                    logger.warning(f"MatrixObserver: Token verification failed after {max_retries} attempts, assuming valid: {whoami_error}")
                    return True
                    
        return False

    async def _save_token(self):
        """Save authentication token for reuse"""
        try:
            token_data = {
                "access_token": self.client.access_token,
                "user_id": self.client.user_id,
                "device_id": self.client.device_id,
                "homeserver": self.homeserver,
                "saved_at": time.time(),  # Add timestamp for token age tracking
            }

            with open("matrix_token.json", "w") as f:
                json.dump(token_data, f, indent=2)

            # Set restrictive permissions
            os.chmod("matrix_token.json", 0o600)

            logger.info("MatrixObserver: Saved authentication token")

        except Exception as e:
            logger.error(f"MatrixObserver: Failed to save token: {e}")

    async def _handle_auth_error(self, error: Exception) -> bool:
        """
        Handle authentication errors by attempting to re-authenticate
        Returns True if re-authentication was successful, False otherwise
        """
        error_str = str(error)
        
        # Check if this is an authentication error
        if not any(auth_error in error_str.lower() for auth_error in [
            'm_unknown_token', 'm_forbidden', 'unauthorized', 'invalid_token'
        ]):
            return False
            
        logger.warning(f"MatrixObserver: Authentication error detected, attempting re-login: {error}")
        
        try:
            # Clear the invalid token
            self.client.access_token = ""
            
            # Attempt fresh login
            response = await self.client.login(
                password=self.password, 
                device_name=settings.DEVICE_NAME
            )
            
            if isinstance(response, LoginResponse):
                logger.info(f"MatrixObserver: Re-authentication successful as {response.user_id}")
                await self._save_token()
                return True
            else:
                logger.error(f"MatrixObserver: Re-authentication failed: {response}")
                return False
                
        except Exception as reauth_error:
            logger.error(f"MatrixObserver: Re-authentication attempt failed: {reauth_error}")
            return False

    async def _sync_forever(self):
        """Background sync task that runs the Matrix client sync with improved error handling"""
        retry_count = 0
        max_retries = 5
        base_delay = 1
        
        while retry_count < max_retries:
            try:
                # Store rate limit information in world state
                self.world_state.set_rate_limits("matrix", {
                    "status": "active",
                    "last_sync_attempt": time.time(),
                    "retry_count": retry_count
                })
                
                await self.client.sync_forever(timeout=30000, full_state=True)
                # If we get here, sync completed normally (shouldn't happen in sync_forever)
                break
                
            except Exception as e:
                error_str = str(e)
                retry_count += 1
                
                logger.error(f"MatrixObserver: Sync error (attempt {retry_count}/{max_retries}): {e}")
                
                # Update world state with error info
                self.world_state.set_rate_limits("matrix", {
                    "status": "error",
                    "last_error": error_str,
                    "last_error_time": time.time(),
                    "retry_count": retry_count
                })
                
                # Handle authentication errors
                if await self._handle_auth_error(e):
                    logger.info("MatrixObserver: Re-authentication successful, retrying sync...")
                    retry_count = 0  # Reset retry count after successful re-auth
                    continue
                
                # Handle rate limiting with exponential backoff
                if '429' in error_str or 'rate' in error_str.lower():
                    # Extract retry-after if available
                    retry_after = 60  # Default fallback
                    if hasattr(e, 'retry_after_ms') and e.retry_after_ms:
                        retry_after = e.retry_after_ms / 1000
                    elif 'sleeping for' in error_str:
                        # Extract from nio client message format
                        import re
                        match = re.search(r'sleeping for (\d+)ms', error_str)
                        if match:
                            retry_after = int(match.group(1)) / 1000
                    
                    logger.info(f"MatrixObserver: Rate limited, waiting {retry_after}s before retry")
                    
                    # Update world state with rate limit info
                    self.world_state.set_rate_limits("matrix", {
                        "status": "rate_limited",
                        "retry_after": retry_after,
                        "retry_after_until": time.time() + retry_after,
                        "last_rate_limit": time.time()
                    })
                    
                    await asyncio.sleep(retry_after)
                    continue
                
                # For other errors, use exponential backoff
                if retry_count < max_retries:
                    delay = min(base_delay * (2 ** (retry_count - 1)), 300)  # Cap at 5 minutes
                    logger.info(f"MatrixObserver: Retrying sync in {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"MatrixObserver: Max retries exceeded, giving up on sync")
                    break
        
        # If we exit the loop, update world state
        self.world_state.update_system_status({"matrix_connected": False})
        self.world_state.set_rate_limits("matrix", {
            "status": "disconnected",
            "last_disconnect": time.time()
        })

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
                details.update(
                    {
                        "room_id": room_id,
                        "is_monitoring": room_id in self.channels_to_monitor,
                        "user_list": list(room.users.keys()),
                        "last_message_time": max(
                            [
                                msg.server_timestamp
                                for msg in room.timeline.events
                                if hasattr(msg, "server_timestamp")
                            ],
                            default=0,
                        ),
                    }
                )
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
                            "display_name": getattr(user, "display_name", None),
                            "avatar_url": getattr(user, "avatar_url", None),
                            "rooms": [],
                            "power_levels": {},
                        }

                    user_details[user_id]["rooms"].append(room_id)
                    if hasattr(room, "power_levels") and room.power_levels:
                        if user_id in room.power_levels.users:
                            user_details[user_id]["power_levels"][
                                room_id
                            ] = room.power_levels.users[user_id]

        except Exception as e:
            logger.error(f"Error getting user details: {e}")

        return user_details

    async def send_message(self, room_id: str, content: str) -> Dict[str, Any]:
        """Send a message to a Matrix room"""
        if not self.client:
            return {"success": False, "error": "Matrix client not connected"}

        try:
            # Handle formatted content dictionary from format_for_matrix
            if isinstance(content, dict) and 'plain' in content:
                # Properly unpack the formatted content dictionary
                message_content = {
                    "msgtype": "m.text",
                    "body": content.get("plain", "Error: message content unavailable."),
                    "format": "org.matrix.custom.html",
                    "formatted_body": content.get("html", ""),
                }
            else:
                # Fallback for plain string content
                message_content = {"msgtype": "m.text", "body": str(content)}
                
            response = await self.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content=message_content,
            )

            if isinstance(response, RoomSendResponse):
                logger.info(
                    f"MatrixObserver: Sent message to {room_id} (event: {response.event_id})"
                )
                return {
                    "success": True,
                    "event_id": response.event_id,
                    "room_id": room_id,
                }
            else:
                logger.error(f"MatrixObserver: Failed to send message: {response}")
                return {"success": False, "error": str(response)}

        except Exception as e:
            logger.error(f"MatrixObserver: Error sending message: {e}")
            return {"success": False, "error": str(e)}

    async def send_reply(
        self, room_id: str, content: str, reply_to_event_id: str
    ) -> Dict[str, Any]:
        """Send a reply to a specific message in a Matrix room"""
        logger.info(
            f"MatrixObserver.send_reply called: room_id={room_id}, content_length={len(content)}, reply_to={reply_to_event_id}"
        )

        if not self.client:
            logger.error("Matrix client not connected")
            return {"success": False, "error": "Matrix client not connected"}

        # Validate message content and length
        if len(content) > 4000:  # Matrix has message size limits
            logger.warning(f"Message too long ({len(content)} chars), truncating...")
            content = content[:3997] + "..."

        try:
            # Handle formatted content dictionary from format_for_matrix
            if isinstance(content, dict) and 'plain' in content:
                # Properly unpack the formatted content dictionary
                reply_content = {
                    "msgtype": "m.text",
                    "body": content.get("plain", "Error: message content unavailable."),
                    "format": "org.matrix.custom.html",
                    "formatted_body": content.get("html", ""),
                    "m.relates_to": {"m.in_reply_to": {"event_id": reply_to_event_id}},
                }
            else:
                # Fallback for plain string content
                reply_content = {
                    "msgtype": "m.text",
                    "body": str(content),
                    "m.relates_to": {"m.in_reply_to": {"event_id": reply_to_event_id}},
                }

            logger.info(f"Sending reply with content: {reply_content}")

            # Add retry logic with exponential backoff
            max_retries = 3
            for attempt in range(max_retries):
                response = await self.client.room_send(
                    room_id=room_id,
                    message_type="m.room.message",
                    content=reply_content,
                )

                logger.info(
                    f"Matrix client room_send response (attempt {attempt + 1}): {response} (type: {type(response)})"
                )

                if isinstance(response, RoomSendResponse):
                    logger.info(
                        f"MatrixObserver: Sent reply to {room_id} (event: {response.event_id}, reply_to: {reply_to_event_id})"
                    )
                    return {
                        "success": True,
                        "event_id": response.event_id,
                        "room_id": room_id,
                        "reply_to_event_id": reply_to_event_id,
                    }
                elif isinstance(response, RoomSendError):
                    # Enhanced error logging for RoomSendError
                    error_details = {
                        "message": getattr(response, "message", "unknown error"),
                        "status_code": getattr(response, "status_code", None),
                        "retry_after_ms": getattr(response, "retry_after_ms", None),
                        "transport_response": str(
                            getattr(response, "transport_response", None)
                        ),
                    }

                    logger.error(
                        f"MatrixObserver: RoomSendError (attempt {attempt + 1}/{max_retries}): {error_details}"
                    )

                    # Handle rate limiting
                    if error_details["retry_after_ms"]:
                        wait_time = error_details["retry_after_ms"] / 1000
                        logger.info(f"Rate limited, waiting {wait_time}s before retry")
                        await asyncio.sleep(wait_time)
                        continue

                    # For other errors, wait with exponential backoff
                    if attempt < max_retries - 1:
                        wait_time = 2**attempt
                        logger.info(f"Waiting {wait_time}s before retry")
                        await asyncio.sleep(wait_time)
                        continue

                    # Final attempt failed
                    return {
                        "success": False,
                        "error": f"RoomSendError: {error_details['message']} (Status: {error_details['status_code']})",
                    }
                else:
                    # Unknown response type
                    logger.error(
                        f"MatrixObserver: Unknown response type: {type(response)}, value: {response}"
                    )
                    if attempt < max_retries - 1:
                        wait_time = 2**attempt
                        logger.info(f"Waiting {wait_time}s before retry")
                        await asyncio.sleep(wait_time)
                        continue

                    return {
                        "success": False,
                        "error": f"Unknown response type: {type(response)} - {str(response)}",
                    }

            # Should not reach here, but just in case
            return {"success": False, "error": f"Failed after {max_retries} attempts"}

        except Exception as e:
            logger.error(
                f"MatrixObserver: Exception while sending reply: {e}", exc_info=True
            )
            return {"success": False, "error": f"Exception: {str(e)}"}

    async def send_formatted_message(
        self, room_id: str, plain_content: str, html_content: str
    ) -> Dict[str, Any]:
        """Send a formatted message with both plain text and HTML versions."""
        logger.info(f"MatrixObserver.send_formatted_message called: room={room_id}")

        if not self.client:
            logger.error("Matrix client not connected")
            return {"success": False, "error": "Matrix client not connected"}

        # Check connection health before sending
        try:
            await self.ensure_connection()
        except Exception as e:
            logger.error(f"Failed to ensure connection before sending message: {e}")
            return {"success": False, "error": f"Connection issue: {str(e)}"}

        try:
            # Create formatted message content
            content = {
                "msgtype": "m.text",
                "body": plain_content,  # Fallback plain text
                "format": "org.matrix.custom.html",
                "formatted_body": html_content,
            }

            # Add retry logic with exponential backoff
            max_retries = 3
            for attempt in range(max_retries):
                response = await self.client.room_send(
                    room_id=room_id, message_type="m.room.message", content=content
                )

                logger.info(
                    f"Matrix client room_send response (attempt {attempt + 1}): {response} (type: {type(response)})"
                )

                if isinstance(response, RoomSendResponse):
                    logger.info(
                        f"MatrixObserver: Successfully sent formatted message to {room_id} (event: {response.event_id})"
                    )
                    return {
                        "success": True,
                        "event_id": response.event_id,
                        "room_id": room_id,
                    }
                elif isinstance(response, RoomSendError):
                    # Enhanced error logging for RoomSendError
                    error_details = {
                        "message": getattr(response, "message", "unknown error"),
                        "status_code": getattr(response, "status_code", None),
                        "retry_after_ms": getattr(response, "retry_after_ms", None),
                        "transport_response": str(
                            getattr(response, "transport_response", None)
                        ),
                    }

                    logger.error(
                        f"MatrixObserver: RoomSendError (attempt {attempt + 1}/{max_retries}): {error_details}"
                    )

                    # Handle rate limiting
                    if error_details["retry_after_ms"]:
                        wait_time = error_details["retry_after_ms"] / 1000
                        logger.info(f"Rate limited, waiting {wait_time}s before retry")
                        await asyncio.sleep(wait_time)
                        continue

                    # For other errors, wait with exponential backoff
                    if attempt < max_retries - 1:
                        wait_time = 2**attempt
                        logger.info(f"Waiting {wait_time}s before retry")
                        await asyncio.sleep(wait_time)
                        continue

                    # Final attempt failed
                    return {
                        "success": False,
                        "error": f"RoomSendError: {error_details['message']} (Status: {error_details['status_code']})",
                    }
                else:
                    # Unknown response type
                    logger.error(
                        f"MatrixObserver: Unknown response type: {type(response)}, value: {response}"
                    )
                    if attempt < max_retries - 1:
                        wait_time = 2**attempt
                        logger.info(f"Waiting {wait_time}s before retry")
                        await asyncio.sleep(wait_time)
                        continue

                    return {
                        "success": False,
                        "error": f"Unknown response type: {type(response)} - {str(response)}",
                    }

            # Should not reach here, but just in case
            return {"success": False, "error": f"Failed after {max_retries} attempts"}

        except Exception as e:
            logger.error(f"MatrixObserver: Error sending formatted message: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def send_formatted_reply(
        self,
        room_id: str,
        plain_content: str,
        html_content: str,
        reply_to_event_id: str,
    ) -> Dict[str, Any]:
        """Send a formatted reply with both plain text and HTML versions."""
        logger.info(
            f"MatrixObserver.send_formatted_reply called: room={room_id}, reply_to={reply_to_event_id}"
        )

        if not self.client:
            logger.error("Matrix client not connected")
            return {"success": False, "error": "Matrix client not connected"}

        # Check connection health before sending
        try:
            await self.ensure_connection()
        except Exception as e:
            logger.error(f"Failed to ensure connection before sending reply: {e}")
            return {"success": False, "error": f"Connection issue: {str(e)}"}

        try:
            # Create formatted reply content with reply metadata
            content = {
                "msgtype": "m.text",
                "body": plain_content,
                "format": "org.matrix.custom.html",
                "formatted_body": html_content,
                "m.relates_to": {"m.in_reply_to": {"event_id": reply_to_event_id}},
            }

            # Add retry logic with exponential backoff
            max_retries = 3
            for attempt in range(max_retries):
                response = await self.client.room_send(
                    room_id=room_id, message_type="m.room.message", content=content
                )

                logger.info(
                    f"Matrix client room_send response (attempt {attempt + 1}): {response} (type: {type(response)})"
                )

                if isinstance(response, RoomSendResponse):
                    logger.info(
                        f"MatrixObserver: Successfully sent formatted reply to {room_id} (event: {response.event_id}, reply_to: {reply_to_event_id})"
                    )
                    return {
                        "success": True,
                        "event_id": response.event_id,
                        "room_id": room_id,
                        "reply_to": reply_to_event_id,
                    }
                elif isinstance(response, RoomSendError):
                    # Enhanced error logging for RoomSendError
                    error_details = {
                        "message": getattr(response, "message", "unknown error"),
                        "status_code": getattr(response, "status_code", None),
                        "retry_after_ms": getattr(response, "retry_after_ms", None),
                        "transport_response": str(
                            getattr(response, "transport_response", None)
                        ),
                    }

                    logger.error(
                        f"MatrixObserver: RoomSendError (attempt {attempt + 1}/{max_retries}): {error_details}"
                    )

                    # Handle rate limiting
                    if error_details["retry_after_ms"]:
                        wait_time = error_details["retry_after_ms"] / 1000
                        logger.info(f"Rate limited, waiting {wait_time}s before retry")
                        await asyncio.sleep(wait_time)
                        continue

                    # For other errors, wait with exponential backoff
                    if attempt < max_retries - 1:
                        wait_time = 2**attempt
                        logger.info(f"Waiting {wait_time}s before retry")
                        await asyncio.sleep(wait_time)
                        continue

                    # Final attempt failed
                    return {
                        "success": False,
                        "error": f"RoomSendError: {error_details['message']} (Status: {error_details['status_code']})",
                    }
                else:
                    # Unknown response type
                    logger.error(
                        f"MatrixObserver: Unknown response type: {type(response)}, value: {response}"
                    )
                    if attempt < max_retries - 1:
                        wait_time = 2**attempt
                        logger.info(f"Waiting {wait_time}s before retry")
                        await asyncio.sleep(wait_time)
                        continue

                    return {
                        "success": False,
                        "error": f"Unknown response type: {type(response)} - {str(response)}",
                    }

            # Should not reach here, but just in case
            return {"success": False, "error": f"Failed after {max_retries} attempts"}

        except Exception as e:
            logger.error(f"MatrixObserver: Error sending formatted reply: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def join_room(self, room_identifier: str) -> Dict[str, Any]:
        """Join a Matrix room by room ID or alias"""
        logger.info(
            f"MatrixObserver.join_room called: room_identifier={room_identifier}"
        )

        if not self.client:
            logger.error("Matrix client not connected")
            return {"success": False, "error": "Matrix client not connected"}

        try:
            # Use the Matrix client to join the room
            response = await self.client.join(room_identifier)

            if hasattr(response, "room_id"):
                # Successful join
                room_id = response.room_id
                logger.info(
                    f"MatrixObserver: Successfully joined room {room_id} (identifier: {room_identifier})"
                )

                # Add to monitoring channels if it's not already there
                if room_id not in self.channels_to_monitor:
                    self.channels_to_monitor.append(room_id)

                # Register the room in world state if not already known
                existing_channel = self.world_state.get_channel(room_id, "matrix")
                if not existing_channel:
                    # Get room details after joining
                    if room_id in self.client.rooms:
                        room = self.client.rooms[room_id]
                        room_details = self._extract_room_details(room)
                        self._register_room(room_id, room_details)
                    else:
                        # Fallback registration
                        self.world_state.add_channel(
                            room_id, "matrix", f"Room {room_id}"
                        )

                return {
                    "success": True,
                    "room_id": room_id,
                    "room_identifier": room_identifier,
                }
            else:
                error_msg = f"Failed to join room: {response}"
                logger.error(f"MatrixObserver: {error_msg}")
                return {"success": False, "error": error_msg}

        except Exception as e:
            error_msg = f"Exception while joining room: {str(e)}"
            logger.error(f"MatrixObserver: {error_msg}", exc_info=True)
            return {"success": False, "error": error_msg}

    async def leave_room(
        self, room_id: str, reason: str = "Leaving room"
    ) -> Dict[str, Any]:
        """Leave a Matrix room"""
        logger.info(
            f"MatrixObserver.leave_room called: room_id={room_id}, reason={reason}"
        )

        if not self.client:
            logger.error("Matrix client not connected")
            return {"success": False, "error": "Matrix client not connected"}

        try:
            # Use the Matrix client to leave the room
            response = await self.client.room_leave(room_id, reason)

            if hasattr(response, "message") and "left" in response.message.lower():
                # Successful leave - although nio doesn't return success indicator directly
                logger.info(f"MatrixObserver: Left room {room_id}")

                # Remove from monitoring channels
                if room_id in self.channels_to_monitor:
                    self.channels_to_monitor.remove(room_id)

                if hasattr(self, "world_state") and self.world_state:
                    self.world_state.update_channel_status(room_id, "left_by_bot")

                return {
                    "success": True,
                    "room_id": room_id,
                    "reason": reason,
                }
            else:
                # Assume success if no error was raised
                logger.info(
                    f"MatrixObserver: Left room {room_id} (response: {response})"
                )

                # Remove from monitoring and update status
                if room_id in self.channels_to_monitor:
                    self.channels_to_monitor.remove(room_id)

                if hasattr(self, "world_state") and self.world_state:
                    self.world_state.update_channel_status(room_id, "left_by_bot")

                return {
                    "success": True,
                    "room_id": room_id,
                    "reason": reason,
                }

        except Exception as e:
            error_msg = f"Exception while leaving room: {str(e)}"
            logger.error(f"MatrixObserver: {error_msg}", exc_info=True)
            return {"success": False, "error": error_msg}

    async def accept_invite(self, room_id: str) -> Dict[str, Any]:
        """Accept a Matrix room invitation"""
        logger.info(f"MatrixObserver.accept_invite called: room_id={room_id}")

        if not self.client:
            logger.error("Matrix client not connected")
            return {"success": False, "error": "Matrix client not connected"}

        try:
            # Determine if invite exists in client or world state
            is_in_client_invites = room_id in getattr(self.client, 'invited_rooms', {})
            is_in_world_state_invites = False
            if hasattr(self, 'world_state') and self.world_state:
                pending = self.world_state.get_pending_matrix_invites()
                is_in_world_state_invites = any(
                    inv.get('room_id') == room_id for inv in pending
                )

            if not is_in_client_invites and not is_in_world_state_invites:
                return {
                    "success": False,
                    "error": f"No pending invitation for room {room_id} in client or world state.",
                }

            # Log if invite was only in world state
            if not is_in_client_invites and is_in_world_state_invites:
                logger.info(
                    f"MatrixObserver: Invite for {room_id} found in world state but not client state. "
                    "Attempting direct join."
                )

            # Accept the invitation by joining the room
            response = await self.client.join(room_id)

            if hasattr(response, "room_id"):
                # Successful acceptance
                actual_room_id = response.room_id
                logger.info(
                    f"MatrixObserver: Successfully accepted invitation and joined room {actual_room_id}"
                )

                # Add to monitoring channels
                if actual_room_id not in self.channels_to_monitor:
                    self.channels_to_monitor.append(actual_room_id)

                # Register the room in world state
                existing_channel = self.world_state.get_channel(actual_room_id, "matrix")
                if not existing_channel:
                    if actual_room_id in self.client.rooms:
                        room = self.client.rooms[actual_room_id]
                        room_details = self._extract_room_details(room)
                        self._register_room(actual_room_id, room_details)
                    else:
                        self.world_state.add_channel(
                            actual_room_id, "matrix", f"Room {actual_room_id}"
                        )

                # Remove from pending invites in world state
                if hasattr(self, "world_state") and self.world_state:
                    self.world_state.remove_pending_matrix_invite(actual_room_id)

                return {
                    "success": True,
                    "room_id": actual_room_id,
                }
            else:
                error_msg = f"Failed to accept invitation: {response}"
                logger.error(f"MatrixObserver: {error_msg}")
                return {"success": False, "error": error_msg}

        except Exception as e:
            error_msg = f"Exception while accepting invitation: {str(e)}"
            logger.error(f"MatrixObserver: {error_msg}", exc_info=True)
            return {"success": False, "error": error_msg}

    async def get_invites(self) -> Dict[str, Any]:
        """Get pending Matrix room invitations from both client and world state"""
        logger.info("MatrixObserver.get_invites called")

        if not self.client:
            logger.error("Matrix client not connected")
            return {"success": False, "error": "Matrix client not connected"}

        try:
            invites = []

            # Get invites from Matrix client
            for room_id, invite_room in self.client.invited_rooms.items():
                invite_info = {
                    "room_id": room_id,
                    "name": getattr(invite_room, "display_name", None)
                    or getattr(invite_room, "name", None)
                    or "Unknown Room",
                    "inviter": getattr(invite_room, "inviter", "Unknown"),
                    "canonical_alias": getattr(invite_room, "canonical_alias", None),
                    "topic": getattr(invite_room, "topic", None),
                    "member_count": getattr(invite_room, "member_count", 0),
                    "encrypted": getattr(invite_room, "encrypted", False),
                    "source": "client",
                }
                invites.append(invite_info)

            # Also get invites from world state (in case they were missed by sync)
            if hasattr(self, "world_state") and self.world_state:
                world_state_invites = self.world_state.get_pending_matrix_invites()
                for invite in world_state_invites:
                    # Check if already in client invites to avoid duplicates
                    room_id = invite.get("room_id")
                    if not any(existing["room_id"] == room_id for existing in invites):
                        invite_copy = invite.copy()
                        invite_copy["source"] = "world_state"
                        invites.append(invite_copy)

            logger.info(f"MatrixObserver: Found {len(invites)} pending invitations")

            return {
                "success": True,
                "invites": invites,
            }

        except Exception as e:
            error_msg = f"Exception while getting invitations: {str(e)}"
            logger.error(f"MatrixObserver: {error_msg}", exc_info=True)
            return {"success": False, "error": error_msg}

    async def react_to_message(
        self, room_id: str, event_id: str, emoji: str
    ) -> Dict[str, Any]:
        """
        React to a Matrix message with an emoji.

        Args:
            room_id: The room ID where the message is located
            event_id: The event ID of the message to react to
            emoji: The emoji to react with

        Returns:
            Dict with success status and optional error message
        """
        logger.info(
            f"MatrixObserver.react_to_message called: room={room_id}, event={event_id}, emoji={emoji}"
        )

        if not self.client:
            logger.error("Matrix client not connected")
            return {"success": False, "error": "Matrix client not connected"}

        try:
            # Import the reaction event type
            from nio import RoomSendError, RoomSendResponse

            # Create reaction content
            reaction_content = {
                "m.relates_to": {
                    "rel_type": "m.annotation",
                    "event_id": event_id,
                    "key": emoji,
                }
            }

            # Send the reaction
            response = await self.client.room_send(
                room_id=room_id,
                message_type="m.reaction",
                content=reaction_content,
                ignore_unverified_devices=True,
            )

            if isinstance(response, RoomSendResponse):
                logger.info(
                    f"MatrixObserver: Successfully reacted to {event_id} with {emoji}"
                )
                return {
                    "success": True,
                    "event_id": response.event_id,
                    "room_id": room_id,
                    "reacted_to": event_id,
                    "emoji": emoji,
                }
            elif isinstance(response, RoomSendError):
                error_msg = f"Failed to send reaction: {response.message}"
                logger.error(f"MatrixObserver: {error_msg}")
                return {"success": False, "error": error_msg}
            else:
                error_msg = f"Unexpected response type: {type(response)}"
                logger.error(f"MatrixObserver: {error_msg}")
                return {"success": False, "error": error_msg}

        except Exception as e:
            error_msg = f"Exception while reacting to message: {str(e)}"
            logger.error(f"MatrixObserver: {error_msg}", exc_info=True)
            return {"success": False, "error": error_msg}

    async def get_pending_invites_from_world_state(self) -> Dict[str, Any]:
        """
        Get pending Matrix invites directly from the world state.

        Returns:
            Dict with success status and invites list
        """
        logger.info("MatrixObserver.get_pending_invites_from_world_state called")

        try:
            if hasattr(self, "world_state") and self.world_state:
                invites = self.world_state.get_pending_matrix_invites()
                return {"success": True, "invites": invites, "count": len(invites)}
            else:
                return {
                    "success": False,
                    "error": "World state not available",
                    "invites": [],
                    "count": 0,
                }
        except Exception as e:
            error_msg = f"Exception while getting world state invites: {str(e)}"
            logger.error(f"MatrixObserver: {error_msg}", exc_info=True)
            return {"success": False, "error": error_msg, "invites": [], "count": 0}

    async def send_image(
        self, room_id: str, image_url: str, filename: str = None, content: str = None
    ) -> Dict[str, Any]:
        """
        Send an image to a Matrix room.
        
        Args:
            room_id: The room ID to send the image to
            image_url: The URL of the image to send (should be publicly accessible)
            filename: Optional filename for the image (defaults to extracted from URL)
            content: Optional text content to accompany the image
        
        Returns:
            Dict with success status and optional error message
        """
        logger.info(f"MatrixObserver.send_image called: room={room_id}, url={image_url}")

        if not self.client:
            logger.error("Matrix client not connected")
            return {"success": False, "error": "Matrix client not connected"}

        try:
            import httpx
            from urllib.parse import urlparse
            import mimetypes
            import io
            from PIL import Image
            
            # Determine filename if not provided
            if not filename:
                parsed_url = urlparse(image_url)
                filename = parsed_url.path.split('/')[-1] or "image.jpg"
            
            # Download the image with redirect following (handles all URLs including Arweave)
            logger.info(f"Downloading and uploading image: {image_url}")
            
            # Download the image with redirect following
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                try:
                    # Add user-agent and other headers to mimic a browser
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                        "Accept": "image/*,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.5",
                        "Connection": "keep-alive",
                    }
                    response = await client.get(image_url, headers=headers)
                    response.raise_for_status()
                    image_data = response.content
                except Exception as e:
                    error_msg = f"Failed to download image from {image_url}: {e}"
                    logger.error(error_msg)
                    return {"success": False, "error": error_msg}
            
            # Determine MIME type and image dimensions
            mime_type, _ = mimetypes.guess_type(filename)
            if not mime_type or not mime_type.startswith('image/'):
                mime_type = "image/jpeg"  # Default fallback
            
            # Extract image properties using Pillow
            actual_mime_type = mime_type
            width, height = None, None
            try:
                img = Image.open(io.BytesIO(image_data))
                width, height = img.size
                if img.format:
                    actual_mime_type = Image.MIME.get(img.format.upper()) or mime_type
                logger.info(f"Image properties: w={width}, h={height}, mime={actual_mime_type}")
            except Exception as e:
                logger.warning(f"Could not get image dimensions/MIME for {filename}: {e}")
                actual_mime_type = mime_type
            
            # Get the file size for content-length
            file_size = len(image_data)
            
            # Upload the image to Matrix media repository
            upload_response = await self.client.upload(
                data_provider=lambda got_429, got_timeouts: image_data,
                content_type=actual_mime_type,
                filename=filename,
                filesize=file_size
            )
            
            from nio import UploadResponse, UploadError
            
            # Handle the upload response
            if isinstance(upload_response, tuple):
                # Some versions of matrix-nio return a tuple (response, error)
                actual_response, error = upload_response
                if error:
                    error_msg = f"Failed to upload image to Matrix: {error}"
                    logger.error(error_msg)
                    return {"success": False, "error": error_msg}
                upload_response = actual_response
            
            if isinstance(upload_response, UploadError):
                error_msg = f"Failed to upload image to Matrix: {upload_response.message}"
                logger.error(error_msg)
                return {"success": False, "error": error_msg}
            
            if not isinstance(upload_response, UploadResponse):
                error_msg = f"Unexpected upload response type: {type(upload_response)}"
                logger.error(error_msg)
                return {"success": False, "error": error_msg}
            
            # Create the image message content with proper info field
            image_info = {
                "mimetype": actual_mime_type,
                "size": file_size,
            }
            if width and height:
                image_info["w"] = width
                image_info["h"] = height
            
            message_content = {
                "msgtype": "m.image",
                "body": content or filename,
                "url": upload_response.content_uri,
                "info": image_info
            }
            
            # Send the image message
            send_response = await self.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content=message_content
            )
            
            from nio import RoomSendResponse, RoomSendError
            
            if isinstance(send_response, RoomSendResponse):
                logger.info(
                    f"MatrixObserver: Successfully sent image to {room_id} (event: {send_response.event_id})"
                )
                return {
                    "success": True,
                    "event_id": send_response.event_id,
                    "room_id": room_id,
                    "image_url": image_url,
                    "matrix_uri": upload_response.content_uri,
                    "filename": filename,
                }
            elif isinstance(send_response, RoomSendError):
                error_msg = f"Failed to send image message: {send_response.message}"
                logger.error(f"MatrixObserver: {error_msg}")
                return {"success": False, "error": error_msg}
            else:
                error_msg = f"Unexpected send response type: {type(send_response)}"
                logger.error(f"MatrixObserver: {error_msg}")
                return {"success": False, "error": error_msg}
            
        except Exception as e:
            error_msg = f"Exception while sending image: {str(e)}"
            logger.error(f"MatrixObserver: {error_msg}", exc_info=True)
            return {"success": False, "error": error_msg}

    def add_channel(self, channel_id: str, channel_name: str):
        """Add a channel to monitor"""
        if not self.enabled:
            logger.warning("Matrix observer is disabled - cannot add channel")
            return
            
        self.channels_to_monitor.append(channel_id)
        self.world_state.add_channel(channel_id, "matrix", channel_name)
        logger.info(
            f"MatrixObserver: Added channel {channel_name} ({channel_id}) to monitoring"
        )

    async def check_connection_health(self) -> bool:
        """Check if the Matrix connection is healthy."""
        if not self.client:
            return False
            
        try:
            # Try a simple whoami request to test the connection
            response = await self.client.whoami()
            if hasattr(response, 'user_id'):
                logger.debug(f"Connection healthy for user: {response.user_id}")
                return True
            else:
                logger.warning(f"Unexpected whoami response: {response}")
                return False
        except Exception as e:
            logger.error(f"Connection health check failed: {e}")
            return False

    async def ensure_connection(self):
        """Ensure the Matrix connection is active and attempt to reconnect if needed."""
        if not await self.check_connection_health():
            logger.info("Connection unhealthy, attempting to reconnect...")
            try:
                # Try a quick sync to refresh the connection
                await self.client.sync(timeout=1000)
                logger.info("Connection refresh successful")
                
                # Verify the connection is now healthy
                if await self.check_connection_health():
                    logger.info("Connection restored successfully")
                else:
                    logger.warning("Connection still unhealthy after reconnection attempt")
            except Exception as e:
                logger.error(f"Connection refresh failed: {e}")
                raise

    async def check_room_permissions(self, room_id: str) -> Dict[str, Any]:
        """Check if the bot has permission to send messages in the room."""
        if not self.client:
            return {"error": "Matrix client not connected"}
            
        try:
            # Get room state to check power levels
            power_levels = await self.client.room_get_state_event(
                room_id, "m.room.power_levels"
            )
            
            # Check if bot has required power level to send messages
            user_id = self.client.user_id
            required_level = power_levels.content.get("events", {}).get("m.room.message", 0)
            user_level = power_levels.content.get("users", {}).get(user_id, 0)
            
            logger.info(f"Room {room_id}: Required level {required_level}, User level {user_level}")
            
            return {
                "can_send": user_level >= required_level,
                "required_level": required_level,
                "user_level": user_level
            }
        except Exception as e:
            logger.error(f"Failed to check room permissions: {e}")
            return {"error": str(e)}

    def _should_trigger_for_channel_activity(self, channel_id: str, sender: str) -> bool:
        """
        Determine if we should trigger a response for channel activity.
        
        This prevents the bot from responding to every message in a channel,
        instead focusing on meaningful bursts of new activity.
        """
        import time
        
        current_time = time.time()
        
        # Always trigger for activity we haven't seen before
        if channel_id not in self.channel_activity_triggers:
            return True
            
        # Check if enough time has passed since last trigger
        last_trigger_time = self.channel_activity_triggers[channel_id]
        time_since_last_trigger = current_time - last_trigger_time
        
        if time_since_last_trigger >= self.channel_response_cooldown:
            return True
            
        # Check if bot has responded to this channel recently to avoid rapid responses
        if self.world_state:
            # Look for recent bot messages in this channel
            try:
                channel = self.world_state.get_channel(channel_id, "matrix")
                if channel and channel.recent_messages:
                    # Check last few messages for bot responses
                    recent_messages = channel.recent_messages[-5:]  # Last 5 messages
                    for msg in reversed(recent_messages):  # Check from newest to oldest
                        if msg.sender == self.user_id:
                            # Found a recent bot message, check how recent
                            time_since_bot_message = current_time - msg.timestamp
                            if time_since_bot_message < self.channel_response_cooldown:
                                logger.debug(f"MatrixObserver: Bot responded to {channel_id} {time_since_bot_message:.1f}s ago, skipping trigger")
                                return False
                            break
            except Exception as e:
                logger.debug(f"MatrixObserver: Error checking recent bot activity for {channel_id}: {e}")
        
        # If no recent bot activity found, allow trigger
        return True
    
    def _mark_channel_activity_trigger(self, channel_id: str):
        """Mark that we've triggered a response for this channel."""
        import time
        self.channel_activity_triggers[channel_id] = time.time()
        logger.debug(f"MatrixObserver: Marked activity trigger for channel {channel_id}")
    
    def _cleanup_old_activity_triggers(self):
        """Clean up old activity trigger timestamps to prevent memory bloat."""
        import time
        
        current_time = time.time()
        cutoff_time = current_time - (self.channel_response_cooldown * 2)  # Keep 2x cooldown period
        
        old_channels = [
            channel_id for channel_id, timestamp in self.channel_activity_triggers.items()
            if timestamp < cutoff_time
        ]
        
        for channel_id in old_channels:
            del self.channel_activity_triggers[channel_id]
            
        if old_channels:
            logger.debug(f"MatrixObserver: Cleaned up {len(old_channels)} old activity triggers")