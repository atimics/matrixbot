#!/usr/bin/env python3
"""
Farcaster Observer

This module observes Farcaster feeds and converts posts into standardized messages
for the world state. It monitors for new posts, replies, and other activity.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from ...core.world_state import Message

logger = logging.getLogger(__name__)


class FarcasterObserver:
    """
    Observes Farcaster feeds and converts posts to messages.
    
    This observer can monitor:
    - User feeds (specific FIDs)
    - Channel feeds (e.g., dev, warpcast, base)
    - Notifications (replies to bot, reactions, etc.)
    - Mentions and replies to the bot
    """

    def __init__(
        self, api_key: Optional[str] = None, signer_uuid: Optional[str] = None, bot_fid: Optional[str] = None
    ):
        self.api_key = api_key
        self.signer_uuid = signer_uuid
        self.bot_fid = bot_fid
        self.base_url = "https://api.neynar.com/v2"  # Neynar API for Farcaster
        self.last_check_time = time.time()
        self.observed_channels = set()  # Track which channels we're monitoring
        self.last_seen_hashes = set()  # Track seen post hashes to avoid duplicates

        logger.info("Farcaster observer initialized")

    async def start(self):
        """Start the Farcaster observer"""
        if not self.api_key:
            logger.warning("No Farcaster API key provided - observer will be inactive")
            return

        logger.info("Starting Farcaster observer...")
        # TODO: Initialize API connection, validate credentials

    async def stop(self):
        """Stop the Farcaster observer"""
        logger.info("Stopping Farcaster observer...")
        # TODO: Cleanup connections

    async def observe_feeds(
        self,
        fids: List[int] = None,
        channels: List[str] = None,
        include_notifications: bool = False,
        include_home_feed: bool = False,
    ) -> List[Message]:
        """
        Observe Farcaster feeds for new posts

        Args:
            fids: List of Farcaster user IDs to monitor
            channels: List of channel names to monitor (e.g., ['warpcast', 'dev'])
            include_notifications: Whether to include notifications (mentions, replies to bot)

        Returns:
            List of new messages since last check
        """
        if not self.api_key:
            return []

        new_messages = []
        current_time = time.time()

        try:
            # Observe user feeds if FIDs provided
            if fids:
                for fid in fids:
                    user_messages = await self._observe_user_feed(fid)
                    new_messages.extend(user_messages)

            # Observe channels if provided
            if channels:
                for channel in channels:
                    channel_messages = await self._observe_channel_feed(channel)
                    new_messages.extend(channel_messages)
            # Observe global home feed if requested
            if include_home_feed:
                home_messages = await self._observe_home_feed()
                new_messages.extend(home_messages)
                    
            # Observe notifications if requested and we have bot FID
            if include_notifications and self.bot_fid:
                notification_messages = await self._observe_notifications()
                new_messages.extend(notification_messages)
                
                # Also observe mentions
                mention_messages = await self._observe_mentions()
                new_messages.extend(mention_messages)

            # Update last check time
            self.last_check_time = current_time

            logger.info(f"Observed {len(new_messages)} new Farcaster messages")
            return new_messages

        except Exception as e:
            logger.error(f"Error observing Farcaster feeds: {e}")
            return []

    async def _observe_user_feed(self, fid: int) -> List[Message]:
        """Observe a specific user's feed"""
        try:
            async with httpx.AsyncClient() as client:
                headers = {"accept": "application/json", "api_key": self.api_key}

                # Get recent casts from user
                response = await client.get(
                    f"{self.base_url}/farcaster/casts",
                    headers=headers,
                    params={"fid": fid, "limit": 25, "include_replies": True},
                )

                if response.status_code != 200:
                    logger.error(
                        f"Farcaster API error for user {fid}: {response.status_code}"
                    )
                    return []

                data = response.json()
                return self._convert_casts_to_messages(
                    data.get("casts", []), f"user_{fid}"
                )

        except Exception as e:
            logger.error(f"Error observing user {fid}: {e}")
            return []

    async def _observe_home_feed(self) -> List[Message]:
        """Observe the global Farcaster home feed"""
        try:
            async with httpx.AsyncClient() as client:
                headers = {"accept": "application/json", "api_key": self.api_key}

                # Get recent casts from global feed
                response = await client.get(
                    f"{self.base_url}/farcaster/feed",
                    headers=headers,
                    params={
                        "limit": 25,
                        "include_replies": True,
                    },
                )

                if response.status_code != 200:
                    logger.error(f"Farcaster API error for home feed: {response.status_code}")
                    return []

                data = response.json()
                return self._convert_casts_to_messages(data.get("casts", []), "farcaster:home")

        except Exception as e:
            logger.error(f"Error observing home feed: {e}")
            return []

    async def _observe_channel_feed(self, channel: str) -> List[Message]:
        """Observe a specific channel's feed"""
        try:
            async with httpx.AsyncClient() as client:
                headers = {"accept": "application/json", "api_key": self.api_key}

                # Get recent casts from channel
                response = await client.get(
                    f"{self.base_url}/farcaster/feed/channels",
                    headers=headers,
                    params={
                        "channel_ids": channel,
                        "limit": 25,
                        "include_replies": True,
                    },
                )

                if response.status_code != 200:
                    logger.error(
                        f"Farcaster API error for channel {channel}: {response.status_code}"
                    )
                    return []

                data = response.json()
                return self._convert_casts_to_messages(
                    data.get("casts", []), f"channel_{channel}"
                )

        except Exception as e:
            logger.error(f"Error observing channel {channel}: {e}")
            return []

    async def _observe_notifications(self) -> List[Message]:
        """Observe notifications (mentions, replies to bot, etc.)"""
        try:
            async with httpx.AsyncClient() as client:
                headers = {"accept": "application/json", "api_key": self.api_key}

                # Get notifications for the bot's FID
                response = await client.get(
                    f"{self.base_url}/farcaster/notifications",
                    headers=headers,
                    params={
                        "fid": self.bot_fid,
                        "limit": 25,
                    },
                )

                if response.status_code != 200:
                    logger.error(
                        f"Farcaster API error for notifications: {response.status_code}"
                    )
                    return []

                data = response.json()
                notifications = data.get("notifications", [])
                
                messages = []
                for notification in notifications:
                    try:
                        # Convert different notification types to messages
                        cast_data = notification.get("cast")
                        if not cast_data:
                            continue
                            
                        # Skip if we've already seen this notification
                        notif_hash = cast_data.get("hash", "")
                        if notif_hash in self.last_seen_hashes:
                            continue

                        # Only process notifications newer than our last check
                        cast_timestamp = self._parse_timestamp(cast_data.get("timestamp", ""))
                        if cast_timestamp <= self.last_check_time:
                            continue

                        # Extract message content
                        content = cast_data.get("text", "")
                        if not content:
                            continue

                        # Get sender info
                        author = cast_data.get("author", {})
                        sender = author.get("display_name", author.get("username", "unknown"))

                        # Determine notification type and channel ID
                        notif_type = notification.get("type", "unknown")
                        channel_id = f"farcaster:notifications:{notif_type}"
                        
                        # Check for replies
                        reply_to = None
                        if cast_data.get("parent_hash"):
                            reply_to = cast_data.get("parent_hash")

                        # Create standardized message
                        message = Message(
                            id=notif_hash,
                            channel_id=channel_id,
                            channel_type="farcaster",
                            sender=sender,
                            content=content,
                            timestamp=cast_timestamp,
                            reply_to=reply_to,
                        )

                        messages.append(message)
                        self.last_seen_hashes.add(notif_hash)

                    except Exception as e:
                        logger.error(f"Error converting notification to message: {e}")
                        continue

                logger.info(f"Observed {len(messages)} new Farcaster notifications")
                return messages

        except Exception as e:
            logger.error(f"Error observing notifications: {e}")
            return []

    async def _observe_mentions(self) -> List[Message]:
        """Observe mentions of the bot across Farcaster"""
        try:
            async with httpx.AsyncClient() as client:
                headers = {"accept": "application/json", "api_key": self.api_key}

                # Get mentions and replies for the bot's FID using the correct endpoint
                response = await client.get(
                    f"{self.base_url}/farcaster/feed/user/replies_and_recasts",
                    headers=headers,
                    params={
                        "fid": self.bot_fid,
                        "limit": 25,
                        "filter_type": "replies",
                    },
                )

                if response.status_code != 200:
                    logger.warning(
                        f"Farcaster API error for mentions (trying alternative): {response.status_code}"
                    )
                    # Try alternative approach - search for mentions in notifications
                    return []

                data = response.json()
                casts = data.get("casts", [])
                
                messages = []
                for cast in casts:
                    try:
                        # Skip if we've already seen this cast
                        cast_hash = cast.get("hash", "")
                        if cast_hash in self.last_seen_hashes:
                            continue

                        # Only process casts newer than our last check
                        cast_timestamp = self._parse_timestamp(cast.get("timestamp", ""))
                        if cast_timestamp <= self.last_check_time:
                            continue

                        # Extract message content
                        content = cast.get("text", "")
                        if not content:
                            continue

                        # Get sender info
                        author = cast.get("author", {})
                        sender = author.get("display_name", author.get("username", "unknown"))

                        # Check for replies
                        reply_to = None
                        if cast.get("parent_hash"):
                            reply_to = cast.get("parent_hash")

                        # Create standardized message for mentions
                        message = Message(
                            id=cast_hash,
                            channel_id="farcaster:mentions",
                            channel_type="farcaster",
                            sender=sender,
                            content=content,
                            timestamp=cast_timestamp,
                            reply_to=reply_to,
                        )

                        messages.append(message)
                        self.last_seen_hashes.add(cast_hash)

                    except Exception as e:
                        logger.error(f"Error converting mention to message: {e}")
                        continue

                logger.info(f"Observed {len(messages)} new Farcaster mentions/replies")
                return messages

        except Exception as e:
            logger.error(f"Error observing mentions: {e}")
            return []

    def _convert_casts_to_messages(
        self, casts: List[Dict], channel_id: str
    ) -> List[Message]:
        """Convert Farcaster casts to standardized Message objects"""
        messages = []

        for cast in casts:
            try:
                # Skip if we've already seen this cast
                cast_hash = cast.get("hash", "")
                if cast_hash in self.last_seen_hashes:
                    continue

                # Only process casts newer than our last check
                cast_timestamp = self._parse_timestamp(cast.get("timestamp", ""))
                if cast_timestamp <= self.last_check_time:
                    continue

                # Extract message content
                content = cast.get("text", "")
                if not content:
                    continue

                # Get sender info
                author = cast.get("author", {})
                sender = author.get("display_name", author.get("username", "unknown"))

                # Check for replies
                reply_to = None
                if cast.get("parent_hash"):
                    reply_to = cast.get("parent_hash")

                # Create standardized message
                message = Message(
                    id=cast_hash,
                    channel_id=channel_id,
                    channel_type="farcaster",
                    sender=sender,
                    content=content,
                    timestamp=cast_timestamp,
                    reply_to=reply_to,
                )

                messages.append(message)
                self.last_seen_hashes.add(cast_hash)

            except Exception as e:
                logger.error(f"Error converting cast to message: {e}")
                continue

        return messages

    def _convert_notifications_to_messages(
        self, notifications: List[Dict]
    ) -> List[Message]:
        """Convert Farcaster notifications to standardized Message objects"""
        messages = []

        for notification in notifications:
            try:
                # Extract relevant info from notification
                notification_type = notification.get("type", "")
                actor = notification.get("actor", {})
                target = notification.get("target", {})

                # Skip notifications that are not mentions or replies
                if notification_type not in ["mention", "reply"]:
                    continue

                # Get the cast (post) associated with the notification
                cast = target.get("cast", {})
                if not cast:
                    continue

                # Extract message content
                content = cast.get("text", "")
                if not content:
                    continue

                # Get sender info
                sender = actor.get("display_name", actor.get("username", "unknown"))

                # Check for replies
                reply_to = None
                if cast.get("parent_hash"):
                    reply_to = cast.get("parent_hash")

                # Create standardized message
                message = Message(
                    id=cast.get("hash", ""),
                    channel_id=f"notification_{notification_type}",
                    channel_type="farcaster",
                    sender=sender,
                    content=content,
                    timestamp=self._parse_timestamp(cast.get("timestamp", "")),
                    reply_to=reply_to,
                )

                messages.append(message)

            except Exception as e:
                logger.error(f"Error converting notification to message: {e}")
                continue

        return messages

    def _parse_timestamp(self, timestamp_str: str) -> float:
        """Parse Farcaster timestamp to Unix timestamp"""
        try:
            # Farcaster timestamps are typically ISO format
            from datetime import datetime

            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            return dt.timestamp()
        except Exception:
            return time.time()

    async def post_cast(
        self, content: str, channel: str = None, reply_to: str = None
    ) -> Dict[str, Any]:
        """
        Post a cast to Farcaster

        Args:
            content: Text content to post
            channel: Channel to post in (optional)
            reply_to: Hash of cast to reply to (optional)

        Returns:
            Result dictionary with success status and cast hash
        """
        if not self.api_key:
            return {"success": False, "error": "No API key configured"}

        if not self.signer_uuid:
            return {"success": False, "error": "No signer UUID configured"}

        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "accept": "application/json",
                    "api_key": self.api_key,
                    "content-type": "application/json",
                }

                payload = {"text": content, "signer_uuid": self.signer_uuid}

                if channel:
                    payload["channel_id"] = channel

                if reply_to:
                    payload["parent"] = reply_to

                response = await client.post(
                    f"{self.base_url}/farcaster/cast", headers=headers, json=payload
                )

                if response.status_code == 200:
                    data = response.json()
                    cast_hash = data.get("cast", {}).get("hash", "")
                    logger.info(f"Successfully posted cast: {cast_hash}")
                    return {"success": True, "cast_hash": cast_hash}
                else:
                    error_msg = f"API error: {response.status_code}"
                    logger.error(f"Failed to post cast: {error_msg}")
                    return {"success": False, "error": error_msg}

        except Exception as e:
            logger.error(f"Error posting cast: {e}")
            return {"success": False, "error": str(e)}

    async def reply_to_cast(self, content: str, reply_to_hash: str) -> Dict[str, Any]:
        """
        Reply to a cast on Farcaster

        Args:
            content: Text content of the reply
            reply_to_hash: Hash of the cast to reply to

        Returns:
            Result dictionary with success status and cast hash
        """
        # For replies, we use post_cast with the reply_to parameter
        return await self.post_cast(content, reply_to=reply_to_hash)

    async def like_cast(self, cast_hash: str) -> Dict[str, Any]:
        """
        Like (react to) a cast on Farcaster

        Args:
            cast_hash: Hash of the cast to like

        Returns:
            Result dictionary with success status
        """
        if not self.api_key:
            return {"success": False, "error": "No API key configured"}

        if not self.signer_uuid:
            return {"success": False, "error": "No signer UUID configured"}

        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "accept": "application/json",
                    "api_key": self.api_key,
                    "content-type": "application/json",
                }

                payload = {
                    "signer_uuid": self.signer_uuid,
                    "reaction_type": "like",
                    "target": cast_hash,
                }

                response = await client.post(
                    f"{self.base_url}/farcaster/reaction", headers=headers, json=payload
                )

                if response.status_code == 200:
                    logger.info(f"Successfully liked cast: {cast_hash}")
                    return {"success": True, "cast_hash": cast_hash}
                else:
                    error_msg = f"API error: {response.status_code}"
                    logger.error(f"Failed to like cast: {error_msg}")
                    return {"success": False, "error": error_msg}

        except Exception as e:
            logger.error(f"Error liking cast: {e}")
            return {"success": False, "error": str(e)}

    async def quote_cast(self, content: str, quoted_cast_hash: str, channel: str = None) -> Dict[str, Any]:
        """
        Quote cast (recast with comment) on Farcaster

        Args:
            content: Text content of the quote
            quoted_cast_hash: Hash of the cast to quote
            channel: Channel to post in (optional)

        Returns:
            Result dictionary with success status and cast hash
        """
        if not self.api_key:
            return {"success": False, "error": "No API key configured"}

        if not self.signer_uuid:
            return {"success": False, "error": "No signer UUID configured"}

        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "accept": "application/json",
                    "api_key": self.api_key,
                    "content-type": "application/json",
                }

                payload = {
                    "text": content,
                    "signer_uuid": self.signer_uuid,
                    "embeds": [{"cast_id": {"hash": quoted_cast_hash}}],
                }

                if channel:
                    payload["channel_id"] = channel

                response = await client.post(
                    f"{self.base_url}/farcaster/cast", headers=headers, json=payload
                )

                if response.status_code == 200:
                    data = response.json()
                    cast_hash = data.get("cast", {}).get("hash", "")
                    logger.info(f"Successfully posted quote cast: {cast_hash}")
                    return {"success": True, "cast_hash": cast_hash, "quoted_cast": quoted_cast_hash}
                else:
                    error_msg = f"API error: {response.status_code}"
                    logger.error(f"Failed to post quote cast: {error_msg}")
                    return {"success": False, "error": error_msg}

        except Exception as e:
            logger.error(f"Error posting quote cast: {e}")
            return {"success": False, "error": str(e)}

    def is_connected(self) -> bool:
        """Check if the Farcaster observer is connected and ready"""
        return self.api_key is not None and self.signer_uuid is not None

    def can_observe_notifications(self) -> bool:
        """Check if the observer can fetch notifications (requires bot FID)"""
        return self.api_key is not None and self.bot_fid is not None

    def get_status(self) -> Dict[str, Any]:
        """Get current observer status"""
        return {
            "connected": self.is_connected(),
            "can_observe_notifications": self.can_observe_notifications(),
            "last_check_time": self.last_check_time,
            "observed_channels": list(self.observed_channels),
            "seen_hashes_count": len(self.last_seen_hashes),
            "bot_fid": self.bot_fid,
        }
