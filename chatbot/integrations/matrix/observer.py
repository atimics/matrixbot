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
from ...tools.s3_service import s3_service

logger = logging.getLogger(__name__)
load_dotenv()


class MatrixObserver:
    """Observes Matrix channels and reports to world state"""

    def __init__(self, world_state_manager: WorldStateManager):
        self.world_state = world_state_manager
        self.homeserver = settings.MATRIX_HOMESERVER
        self.user_id = settings.MATRIX_USER_ID
        self.password = settings.MATRIX_PASSWORD
        self.client: Optional[AsyncClient] = None
        self.sync_task: Optional[asyncio.Task] = None
        self.channels_to_monitor = []

        # Create store directory for Matrix client data
        self.store_path = Path("matrix_store")
        self.store_path.mkdir(exist_ok=True)

        if not all([self.homeserver, self.user_id, self.password]):
            raise ValueError(
                "Matrix configuration missing. Check MATRIX_HOMESERVER, MATRIX_USER_ID, and MATRIX_PASSWORD environment variables."
            )

        logger.info(f"MatrixObserver: Initialized for {self.user_id}@{self.homeserver}")

    def add_channel(self, channel_id: str, channel_name: str):
        """Add a channel to monitor"""
        self.channels_to_monitor.append(channel_id)
        self.world_state.add_channel(channel_id, "matrix", channel_name)
        logger.info(
            f"MatrixObserver: Added channel {channel_name} ({channel_id}) to monitoring"
        )

    async def start(self):
        """Start the Matrix observer"""
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

        try:
            # Try to load saved token
            if await self._load_token():
                logger.info("MatrixObserver: Using saved authentication token")
            else:
                # Login with password and device configuration
                logger.info("MatrixObserver: Logging in with password...")
                response = await self.client.login(
                    password=self.password, device_name=device_name
                )
                if isinstance(response, LoginResponse):
                    logger.info(
                        f"MatrixObserver: Login successful as {response.user_id}"
                    )
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

        except Exception as e:
            logger.error(f"MatrixObserver: Error starting Matrix client: {e}")
            self.world_state.update_system_status({"matrix_connected": False})
            raise

    async def _on_message(self, room: MatrixRoom, event):
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

        logger.debug(
            f"MatrixObserver: Processing message from {room.room_id} ({room.display_name})"
        )

        # Detect image URLs
        image_urls_list = []
        content = ""

        if isinstance(event, RoomMessageImage):
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
                            # Upload Matrix image data directly to S3 for public access
                            original_filename = getattr(event, "body", "matrix_image.jpg")

                            # Use the content-type from download response if available
                            content_type = getattr(
                                download_response, "content_type", "image/jpeg"
                            )

                            s3_url = await s3_service.upload_image_data(
                                download_response.body, original_filename
                            )

                            if s3_url:
                                image_urls_list.append(s3_url)
                                logger.info(
                                    f"MatrixObserver: Uploaded Matrix image to S3: {s3_url}"
                                )
                            else:
                                # Fallback to MXC URI if S3 upload fails (AI won't be able to access it, but it's better than nothing)
                                http_url = await self.client.mxc_to_http(mxc_uri)
                                if http_url:
                                    image_urls_list.append(http_url)
                                    logger.warning(
                                        f"MatrixObserver: S3 upload failed, using Matrix URL: {http_url}"
                                    )
                                else:
                                    logger.warning(
                                        f"MatrixObserver: Both S3 upload and MXC conversion failed for {mxc_uri}"
                                    )
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

        self.world_state.state.channels[room_id] = channel
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
            with open(token_file, "r") as f:
                token_data = json.load(f)

            self.client.access_token = token_data["access_token"]
            self.client.user_id = token_data["user_id"]
            self.client.device_id = token_data["device_id"]

            # Verify token is still valid
            response = await self.client.whoami()
            if hasattr(response, "user_id") and response.user_id:
                logger.info(
                    f"MatrixObserver: Token verified for user {response.user_id}"
                )
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
                "homeserver": self.homeserver,
            }

            with open("matrix_token.json", "w") as f:
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
            response = await self.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": content},
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
            # Format as a reply with Matrix reply formatting
            reply_content = {
                "msgtype": "m.text",
                "body": content,
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
        try:
            logger.info(f"MatrixObserver.send_formatted_message called: room={room_id}")

            # Create formatted message content
            content = {
                "msgtype": "m.text",
                "body": plain_content,  # Fallback plain text
                "format": "org.matrix.custom.html",
                "formatted_body": html_content,
            }

            response = await self.client.room_send(
                room_id=room_id, message_type="m.room.message", content=content
            )

            if isinstance(response, RoomSendResponse):
                logger.info(
                    f"MatrixObserver: Successfully sent formatted message to {room_id}"
                )
                return {
                    "success": True,
                    "event_id": response.event_id,
                    "room_id": room_id,
                }
            else:
                logger.error(
                    f"MatrixObserver: Failed to send formatted message: {response}"
                )
                return {"success": False, "error": str(response)}

        except Exception as e:
            logger.error(f"MatrixObserver: Error sending formatted message: {e}")
            return {"success": False, "error": str(e)}

    async def send_formatted_reply(
        self,
        room_id: str,
        plain_content: str,
        html_content: str,
        reply_to_event_id: str,
    ) -> Dict[str, Any]:
        """Send a formatted reply with both plain text and HTML versions."""
        try:
            logger.info(
                f"MatrixObserver.send_formatted_reply called: room={room_id}, reply_to={reply_to_event_id}"
            )

            # Create formatted reply content with reply metadata
            content = {
                "msgtype": "m.text",
                "body": plain_content,
                "format": "org.matrix.custom.html",
                "formatted_body": html_content,
                "m.relates_to": {"m.in_reply_to": {"event_id": reply_to_event_id}},
            }

            response = await self.client.room_send(
                room_id=room_id, message_type="m.room.message", content=content
            )

            if isinstance(response, RoomSendResponse):
                logger.info(
                    f"MatrixObserver: Successfully sent formatted reply to {room_id}"
                )
                return {
                    "success": True,
                    "event_id": response.event_id,
                    "room_id": room_id,
                    "reply_to": reply_to_event_id,
                }
            else:
                logger.error(
                    f"MatrixObserver: Failed to send formatted reply: {response}"
                )
                return {"success": False, "error": str(response)}

        except Exception as e:
            logger.error(f"MatrixObserver: Error sending formatted reply: {e}")
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
                if room_id not in self.world_state.state.channels:
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
            # Check if we have an invite for this room
            if room_id not in self.client.invited_rooms:
                return {
                    "success": False,
                    "error": f"No pending invitation for room {room_id}",
                }

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
                if actual_room_id not in self.world_state.state.channels:
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
            
            # Download the image
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(image_url)
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
