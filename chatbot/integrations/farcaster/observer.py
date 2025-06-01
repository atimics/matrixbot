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
        self,
        api_key: Optional[str] = None,
        signer_uuid: Optional[str] = None,
        bot_fid: Optional[str] = None,
        world_state_manager=None,
    ):
        self.api_key = api_key
        self.signer_uuid = signer_uuid
        self.bot_fid = bot_fid
        self.world_state_manager = world_state_manager
        self.base_url = "https://api.neynar.com/v2"  # Neynar API for Farcaster
        self.last_check_time = time.time()
        self.observed_channels = set()  # Track which channels we're monitoring
        self.last_seen_hashes = set()  # Track seen post hashes to avoid duplicates
        self.replied_to_hashes = set()  # Track casts we've already replied to
        # Scheduling system to avoid rapid duplicate posts/replies
        self.post_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()  # Store action metadata
        self.reply_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()  # Store action metadata
        self.scheduler_interval: float = 60.0  # seconds between scheduled sends
        self._post_task: Optional[asyncio.Task] = None
        self._reply_task: Optional[asyncio.Task] = None

        logger.info("Farcaster observer initialized")

    async def start(self):
        """Start the Farcaster observer"""
        if not self.api_key:
            logger.warning("No Farcaster API key provided - observer will be inactive")
            return

        logger.info("Starting Farcaster observer with scheduler...")
        # TODO: Initialize API connection, validate credentials
        # Launch background loops for scheduled posts and replies
        self._post_task = asyncio.create_task(self._send_posts_loop())
        self._reply_task = asyncio.create_task(self._send_replies_loop())

    async def stop(self):
        """Stop the Farcaster observer"""
        logger.info("Stopping Farcaster observer and cancelling scheduler tasks...")
        # TODO: Cleanup connections
        
        # Cancel tasks and wait for them to finish
        if self._post_task and not self._post_task.done():
            self._post_task.cancel()
            try:
                await self._post_task
            except asyncio.CancelledError:
                logger.info("Post scheduler task cancelled successfully")
            except Exception as e:
                logger.error(f"Error during post task cancellation: {e}")
                
        if self._reply_task and not self._reply_task.done():
            self._reply_task.cancel()
            try:
                await self._reply_task
            except asyncio.CancelledError:
                logger.info("Reply scheduler task cancelled successfully")
            except Exception as e:
                logger.error(f"Error during reply task cancellation: {e}")
                
        logger.info("Farcaster observer stopped")

    def schedule_post(self, content: str, channel: Optional[str] = None, action_id: Optional[str] = None) -> None:
        """Schedule a new Farcaster post for sending."""
        logger.info(f"🎯 SCHEDULE_POST called with action_id={action_id}, content='{content[:50]}...', channel={channel}")
        
        # Prevent duplicate content in queue
        for queued in list(self.post_queue._queue):  # type: ignore
            if queued.get("content") == content:
                logger.debug("Duplicate content in post queue, skipping schedule")
                return
        
        post_data = {
            "content": content,
            "channel": channel,
            "action_id": action_id,
            "scheduled_at": time.time()
        }
        
        logger.info(f"📝 Adding post to queue: {post_data}")
        self.post_queue.put_nowait(post_data)
        logger.info(f"✅ Successfully added post to queue. New queue size: {self.post_queue.qsize()}")
        logger.info("Scheduled Farcaster post")

    def schedule_reply(self, content: str, reply_to_hash: str, action_id: Optional[str] = None) -> None:
        """Schedule a Farcaster reply for sending."""
        logger.info(f"🎯 SCHEDULE_REPLY called with action_id={action_id}, reply_to_hash={reply_to_hash}, content='{content[:50]}...'")
        
        # Prevent replying twice to the same cast
        if reply_to_hash in self.replied_to_hashes:
            logger.warning(f"Already replied to cast {reply_to_hash}, skipping schedule")
            return
        # Prevent duplicate replies in queue
        for queued in list(self.reply_queue._queue):  # type: ignore
            if queued.get("reply_to_hash") == reply_to_hash:
                logger.warning("Duplicate reply in queue, skipping schedule")
                return
        
        reply_data = {
            "content": content,
            "reply_to_hash": reply_to_hash,
            "action_id": action_id,
            "scheduled_at": time.time()
        }
        
        logger.info(f"📝 Adding reply to queue: {reply_data}")
        self.reply_queue.put_nowait(reply_data)
        logger.info(f"✅ Successfully added reply to queue. New queue size: {self.reply_queue.qsize()}")
        logger.info("Scheduled Farcaster reply")

    async def _send_posts_loop(self) -> None:
        """Background loop to send scheduled posts at controlled intervals."""
        logger.info("Starting Farcaster posts scheduler loop")
        iteration_count = 0
        while True:
            try:
                iteration_count += 1
                logger.info(f"🔄 Post scheduler loop iteration {iteration_count} - waiting for queue item...")
                logger.info(f"📊 Current post queue size: {self.post_queue.qsize()}")
                
                post_data = await self.post_queue.get()
                logger.info(f"✅ Successfully dequeued post data: {post_data}")
                
                content = post_data["content"]
                channel = post_data["channel"] 
                action_id = post_data.get("action_id")
                
                logger.info(f"Dequeued scheduled post for channel {channel or 'default'}: {content[:100]}...")
                
                try:
                    result = await self.post_cast(content, channel)
                    logger.info(f"Post cast result: {result}")
                    
                    # Update world state manager with actual result after sending
                    if hasattr(self, "world_state_manager") and self.world_state_manager:
                        if result.get("success"):
                            cast_hash = result.get("cast", {}).get("hash")
                            if action_id:
                                # Update existing scheduled action
                                self.world_state_manager.update_action_result(
                                    action_id, "success", cast_hash
                                )
                            else:
                                # Fallback: create new action record
                                self.world_state_manager.add_action_result(
                                    action_type="send_farcaster_post",
                                    parameters={"content": content, "channel": channel, "cast_hash": cast_hash},
                                    result="success",
                                )
                            logger.info(
                                f"Successfully sent scheduled post to channel {channel or 'default'}"
                            )
                        else:
                            error_msg = result.get('error', 'unknown error')
                            if action_id:
                                # Update existing scheduled action
                                self.world_state_manager.update_action_result(
                                    action_id, f"failure: {error_msg}"
                                )
                            else:
                                # Fallback: create new action record
                                self.world_state_manager.add_action_result(
                                    action_type="send_farcaster_post",
                                    parameters={"content": content, "channel": channel},
                                    result=f"failure: {error_msg}",
                                )
                            logger.error(
                                f"Failed to send scheduled post: {error_msg}"
                            )
                except Exception as e:
                    logger.error(f"Error sending scheduled post: {e}", exc_info=True)
                    # Update world state manager with exception result
                    if hasattr(self, "world_state_manager") and self.world_state_manager:
                        if action_id:
                            # Update existing scheduled action
                            self.world_state_manager.update_action_result(
                                action_id, f"failure: {str(e)}"
                            )
                        else:
                            # Fallback: create new action record
                            self.world_state_manager.add_action_result(
                                action_type="send_farcaster_post",
                                parameters={"content": content, "channel": channel},
                                result=f"failure: {str(e)}",
                            )
                finally:
                    # Critical: Mark the task as done to prevent queue backup
                    self.post_queue.task_done()
                
                # Wait before processing next item
                await asyncio.sleep(self.scheduler_interval)
                
            except asyncio.CancelledError:
                logger.info("Post scheduler loop cancelled")
                break
            except Exception as e:
                logger.error(f"Unexpected error in post scheduler loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Brief pause before retrying

    async def _send_replies_loop(self) -> None:
        """Background loop to send scheduled replies at controlled intervals."""
        logger.info("Starting Farcaster replies scheduler loop")
        iteration_count = 0
        while True:
            try:
                iteration_count += 1
                logger.info(f"🔄 Reply scheduler loop iteration {iteration_count} - waiting for queue item...")
                logger.info(f"📊 Current reply queue size: {self.reply_queue.qsize()}")
                
                reply_data = await self.reply_queue.get()
                logger.info(f"✅ Successfully dequeued reply data: {reply_data}")
                
                content = reply_data["content"]
                reply_to_hash = reply_data["reply_to_hash"]
                action_id = reply_data.get("action_id")
                
                logger.info(f"Dequeued scheduled reply to {reply_to_hash}: {content[:100]}...")
                
                try:
                    result = await self.reply_to_cast(content, reply_to_hash)
                    logger.info(f"Reply cast result: {result}")
                    
                    # Update world state manager with actual result after sending
                    if hasattr(self, "world_state_manager") and self.world_state_manager:
                        if result.get("success"):
                            cast_hash = result.get("cast", {}).get("hash")
                            
                            if action_id:
                                # Update existing scheduled action
                                self.world_state_manager.update_action_result(
                                    action_id, "success", cast_hash
                                )
                            else:
                                # Fallback: create new action record
                                self.world_state_manager.add_action_result(
                                    action_type="send_farcaster_reply",
                                    parameters={
                                        "content": content,
                                        "reply_to_hash": reply_to_hash,
                                        "cast_hash": cast_hash,
                                    },
                                    result="success",
                                )
                            logger.info(
                                f"Successfully sent scheduled reply to cast {reply_to_hash}"
                            )
                        else:
                            error_msg = result.get('error', 'unknown error')
                            if action_id:
                                # Update existing scheduled action
                                self.world_state_manager.update_action_result(
                                    action_id, f"failure: {error_msg}"
                                )
                            else:
                                # Fallback: create new action record
                                self.world_state_manager.add_action_result(
                                    action_type="send_farcaster_reply",
                                    parameters={
                                        "content": content,
                                        "reply_to_hash": reply_to_hash,
                                    },
                                    result=f"failure: {error_msg}",
                                )
                            logger.error(
                                f"Failed to send scheduled reply to cast {reply_to_hash}: {error_msg}"
                            )
                except Exception as e:
                    logger.error(f"Error sending scheduled reply: {e}", exc_info=True)
                    # Update world state manager with exception result
                    if hasattr(self, "world_state_manager") and self.world_state_manager:
                        if action_id:
                            # Update existing scheduled action
                            self.world_state_manager.update_action_result(
                                action_id, f"failure: {str(e)}"
                            )
                        else:
                            # Fallback: create new action record
                            self.world_state_manager.add_action_result(
                                action_type="send_farcaster_reply",
                                parameters={"content": content, "reply_to_hash": reply_to_hash},
                                result=f"failure: {str(e)}",
                            )
                finally:
                    # Critical: Mark the task as done to prevent queue backup
                    self.reply_queue.task_done()
                
                # Wait before processing next item
                await asyncio.sleep(self.scheduler_interval)
                
            except asyncio.CancelledError:
                logger.info("Reply scheduler loop cancelled")
                break
            except Exception as e:
                logger.error(f"Unexpected error in reply scheduler loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Brief pause before retrying

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

                # Update rate limit tracking
                self._update_rate_limits(response)

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
        # Home feed requires bot FID and feed_type
        if not self.bot_fid:
            logger.warning(
                "FarcasterObserver: bot_fid not configured - skipping home feed"
            )
            return []
        try:
            async with httpx.AsyncClient() as client:
                headers = {"accept": "application/json", "api_key": self.api_key}

                # Get recent casts from home feed of followed accounts
                # Parameters for the "following" (home) feed
                params = {
                    "fid": self.bot_fid,
                    "feed_type": "following",
                    "limit": 25,
                    "include_replies": True,
                    "with_recasts": True,  # include recasts in feed items
                }
                response = await client.get(
                    f"{self.base_url}/farcaster/feed",
                    headers=headers,
                    params=params,
                )

                # Update rate limit tracking
                self._update_rate_limits(response)

                if response.status_code != 200:
                    # Log full error for debugging
                    err_text = response.text if hasattr(response, "text") else ""
                    logger.error(
                        f"Farcaster API error for home feed (following): {response.status_code} - {err_text}"
                    )
                    return []

                data = response.json()
                return self._convert_casts_to_messages(
                    data.get("casts", []), "farcaster:home"
                )

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

                # Update rate limit tracking
                self._update_rate_limits(response)

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

                # Update rate limit tracking
                self._update_rate_limits(response)

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
                        cast_timestamp = self._parse_timestamp(
                            cast_data.get("timestamp", "")
                        )
                        if cast_timestamp <= self.last_check_time:
                            continue

                        # Extract message content
                        content = cast_data.get("text", "")
                        if not content:
                            continue

                        # Get sender info
                        author = cast_data.get("author", {})
                        username = author.get("username", "unknown")
                        display_name = author.get("display_name", username)
                        fid = author.get("fid")
                        # Skip notifications from the bot itself
                        if self.bot_fid and str(fid) == str(self.bot_fid):
                            continue

                        # For Farcaster, prefer username for sender (for tagging)
                        sender = username

                        # Determine notification type and channel ID
                        notif_type = notification.get("type", "unknown")
                        channel_id = f"farcaster:notifications:{notif_type}"

                        # Check for replies
                        reply_to = None
                        if cast_data.get("parent_hash"):
                            reply_to = cast_data.get("parent_hash")

                        # Create standardized message with enhanced user info
                        message = Message(
                            id=notif_hash,
                            channel_id=channel_id,
                            channel_type="farcaster",
                            sender=sender,
                            content=content,
                            timestamp=cast_timestamp,
                            reply_to=reply_to,
                            sender_username=username,
                            sender_display_name=display_name,
                            sender_fid=fid,
                            sender_pfp_url=author.get("pfp_url"),
                            sender_bio=author.get("profile", {})
                            .get("bio", {})
                            .get("text"),
                            sender_follower_count=author.get("follower_count"),
                            sender_following_count=author.get("following_count"),
                            metadata={
                                "notification_type": notif_type,
                                "verified_addresses": author.get(
                                    "verified_addresses", {}
                                ),
                                "power_badge": author.get("power_badge", False),
                            },
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

                # Update rate limit tracking
                self._update_rate_limits(response)

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
                        cast_timestamp = self._parse_timestamp(
                            cast.get("timestamp", "")
                        )
                        if cast_timestamp <= self.last_check_time:
                            continue

                        # Extract message content
                        content = cast.get("text", "")
                        if not content:
                            continue

                        # Get sender info
                        author = cast.get("author", {})
                        username = author.get("username", "unknown")
                        display_name = author.get("display_name", username)
                        fid = author.get("fid")
                        # Skip mentions from the bot itself
                        if self.bot_fid and str(fid) == str(self.bot_fid):
                            continue

                        # For Farcaster, prefer username for sender (for tagging)
                        sender = username

                        # Check for replies
                        reply_to = None
                        if cast.get("parent_hash"):
                            reply_to = cast.get("parent_hash")

                        # Create standardized message for mentions with enhanced user info
                        message = Message(
                            id=cast_hash,
                            channel_id="farcaster:mentions",
                            channel_type="farcaster",
                            sender=sender,
                            content=content,
                            timestamp=cast_timestamp,
                            reply_to=reply_to,
                            sender_username=username,
                            sender_display_name=display_name,
                            sender_fid=fid,
                            sender_pfp_url=author.get("pfp_url"),
                            sender_bio=author.get("profile", {})
                            .get("bio", {})
                            .get("text"),
                            sender_follower_count=author.get("follower_count"),
                            sender_following_count=author.get("following_count"),
                            metadata={
                                "cast_type": "mention",
                                "verified_addresses": author.get(
                                    "verified_addresses", {}
                                ),
                                "power_badge": author.get("power_badge", False),
                            },
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
                # Skip messages from the bot itself
                author = cast.get("author", {})
                fid = author.get("fid")
                if self.bot_fid and fid == self.bot_fid:
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
                username = author.get("username", "unknown")
                display_name = author.get("display_name", username)

                # For Farcaster, prefer username for sender (for tagging)
                sender = username

                # Check for replies
                reply_to = None
                if cast.get("parent_hash"):
                    reply_to = cast.get("parent_hash")

                # Create standardized message with enhanced user info
                message = Message(
                    id=cast_hash,
                    channel_id=channel_id,
                    channel_type="farcaster",
                    sender=sender,
                    content=content,
                    timestamp=cast_timestamp,
                    reply_to=reply_to,
                    sender_username=username,
                    sender_display_name=display_name,
                    sender_fid=fid,
                    sender_pfp_url=author.get("pfp_url"),
                    sender_bio=author.get("profile", {}).get("bio", {}).get("text"),
                    sender_follower_count=author.get("follower_count"),
                    sender_following_count=author.get("following_count"),
                    metadata={
                        "cast_type": "normal",
                        "verified_addresses": author.get("verified_addresses", {}),
                        "power_badge": author.get("power_badge", False),
                        "channel": channel_id,
                    },
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

                # Get sender info (actor is the person who triggered the notification)
                username = actor.get("username", "unknown")
                display_name = actor.get("display_name", username)
                fid = actor.get("fid")

                # For Farcaster, prefer username for sender (for tagging)
                sender = username

                # Check for replies
                reply_to = None
                if cast.get("parent_hash"):
                    reply_to = cast.get("parent_hash")

                # Create standardized message with enhanced user info
                message = Message(
                    id=cast.get("hash", ""),
                    channel_id=f"notification_{notification_type}",
                    channel_type="farcaster",
                    sender=sender,
                    content=content,
                    timestamp=self._parse_timestamp(cast.get("timestamp", "")),
                    reply_to=reply_to,
                    sender_username=username,
                    sender_display_name=display_name,
                    sender_fid=fid,
                    sender_pfp_url=actor.get("pfp_url"),
                    sender_bio=actor.get("profile", {}).get("bio", {}).get("text"),
                    sender_follower_count=actor.get("follower_count"),
                    sender_following_count=actor.get("following_count"),
                    metadata={
                        "notification_type": notification_type,
                        "verified_addresses": actor.get("verified_addresses", {}),
                        "power_badge": actor.get("power_badge", False),
                    },
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

                # Update rate limit tracking
                self._update_rate_limits(response)

                if response.status_code == 200:
                    data = response.json()
                    cast_hash = data.get("cast", {}).get("hash", "")
                    logger.info(f"Successfully posted cast: {cast_hash}")
                    # Prevent duplicate posts of same content by using seen hashes
                    self.last_seen_hashes.add(cast_hash)
                    return {"success": True, "cast_hash": cast_hash}
                else:
                    try:
                        error_data = response.json()
                        error_msg = f"API error {response.status_code}: {error_data.get('message', 'Unknown error')}"
                    except:
                        error_msg = f"API error {response.status_code}: {response.text[:200]}"
                    logger.error(f"Failed to post cast: {error_msg}")
                    return {"success": False, "error": error_msg}

        except Exception as e:
            logger.error(f"Error posting cast: {e}")
            return {"success": False, "error": str(e)}

    async def reply_to_cast(
        self, content: str, reply_to_hash: str, channel: str = None
    ) -> Dict[str, Any]:
        """
        Reply to a specific Farcaster cast (threading a reply), with duplicate detection.

        Args:
            content: Text content of the reply
            reply_to_hash: Hash of the cast to reply to
            channel: Optional channel ID for context

        Returns:
            Result dictionary with success status and reply cast hash
        """
        # Prevent duplicate replies at observer level
        if reply_to_hash in self.replied_to_hashes:
            logger.warning(f"Skipping duplicate reply to cast {reply_to_hash}")
            return {"success": False, "error": "duplicate reply", "cast_hash": None}
        # Use post_cast with parent reply_to parameter
        result = await self.post_cast(
            content=content, channel=channel, reply_to=reply_to_hash
        )
        # Record that we've replied to this cast to prevent future duplicates
        if result.get("success"):
            self.replied_to_hashes.add(reply_to_hash)
            logger.info(f"✅ Added {reply_to_hash} to replied_to_hashes set after successful API call")
        return result

    async def like_cast(self, cast_hash: str) -> Dict[str, Any]:
        """
        Like a cast (reaction) on Farcaster

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

                # Update rate limit tracking
                self._update_rate_limits(response)

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

    async def quote_cast(
        self, content: str, quoted_cast_hash: str, channel: str = None
    ) -> Dict[str, Any]:
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

                # Update rate limit tracking
                self._update_rate_limits(response)

                if response.status_code == 200:
                    data = response.json()
                    cast_hash = data.get("cast", {}).get("hash", "")
                    logger.info(f"Successfully posted quote cast: {cast_hash}")
                    return {
                        "success": True,
                        "cast_hash": cast_hash,
                        "quoted_cast": quoted_cast_hash,
                    }
                else:
                    error_msg = f"API error: {response.status_code}"
                    logger.error(f"Failed to post quote cast: {error_msg}")
                    return {"success": False, "error": error_msg}

        except Exception as e:
            logger.error(f"Error posting quote cast: {e}")
            return {"success": False, "error": str(e)}

    async def follow_user(self, fid: int) -> Dict[str, Any]:
        """
        Follow a Farcaster user by FID
        """
        if not self.api_key:
            return {"success": False, "error": "No API key configured"}
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "accept": "application/json",
                    "api_key": self.api_key,
                    "content-type": "application/json",
                }
                payload = {"signer_uuid": self.signer_uuid, "fid": fid}
                response = await client.post(
                    f"{self.base_url}/farcaster/follow", headers=headers, json=payload
                )
                self._update_rate_limits(response)
                if response.status_code == 200:
                    logger.info(f"Successfully followed user: {fid}")
                    return {"success": True, "fid": fid}
                else:
                    error = f"API error: {response.status_code}"
                    logger.error(f"Failed to follow user: {error}")
                    return {"success": False, "error": error}
        except Exception as e:
            logger.error(f"Error following user: {e}")
            return {"success": False, "error": str(e)}

    async def unfollow_user(self, fid: int) -> Dict[str, Any]:
        """
        Unfollow a Farcaster user by FID
        """
        if not self.api_key:
            return {"success": False, "error": "No API key configured"}
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "accept": "application/json",
                    "api_key": self.api_key,
                    "content-type": "application/json",
                }
                payload = {"signer_uuid": self.signer_uuid, "fid": fid}
                response = await client.post(
                    f"{self.base_url}/farcaster/unfollow", headers=headers, json=payload
                )
                self._update_rate_limits(response)
                if response.status_code == 200:
                    logger.info(f"Successfully unfollowed user: {fid}")
                    return {"success": True, "fid": fid}
                else:
                    error = f"API error: {response.status_code}"
                    logger.error(f"Failed to unfollow user: {error}")
                    return {"success": False, "error": error}
        except Exception as e:
            logger.error(f"Error unfollowing user: {e}")
            return {"success": False, "error": str(e)}

    async def send_dm(self, fid: int, content: str) -> Dict[str, Any]:
        """
        Send a direct message to a Farcaster user
        """
        if not self.api_key:
            return {"success": False, "error": "No API key configured"}
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "accept": "application/json",
                    "api_key": self.api_key,
                    "content-type": "application/json",
                }
                payload = {
                    "signer_uuid": self.signer_uuid,
                    "recipient_fid": fid,
                    "text": content,
                }
                response = await client.post(
                    f"{self.base_url}/farcaster/dm", headers=headers, json=payload
                )
                self._update_rate_limits(response)
                if response.status_code == 200:
                    data = response.json()
                    msg_id = data.get("message", {}).get("id", "")
                    logger.info(f"Successfully sent DM to {fid}: {msg_id}")
                    return {"success": True, "message_id": msg_id}
                else:
                    error = f"API error: {response.status_code}"
                    logger.error(f"Failed to send DM: {error}")
                    return {"success": False, "error": error}
        except Exception as e:
            logger.error(f"Error sending DM: {e}")
            return {"success": False, "error": str(e)}

    # =========================================================================
    # PHASE 1.2: Enhanced Content Discovery Methods
    # =========================================================================

    async def get_user_casts(self, user_identifier: str, limit: int = 10) -> Dict[str, Any]:
        """
        Fetch recent casts from a specific Farcaster user.
        
        Args:
            user_identifier: Either FID (integer as string) or username (e.g., "dwr.eth")
            limit: Number of casts to fetch (default: 10, max: 25)
            
        Returns:
            Dict with success status, casts list, and any error messages
        """
        logger.info(f"FarcasterObserver.get_user_casts: user={user_identifier}, limit={limit}")
        
        if not self.api_key:
            error_msg = "Farcaster API key not configured"
            logger.error(error_msg)
            return {"success": False, "error": error_msg, "casts": []}
        
        try:
            # Determine if user_identifier is FID or username
            if user_identifier.isdigit():
                # It's a FID
                fid = int(user_identifier)
                params = {"fid": fid, "limit": min(limit, 25), "include_replies": False}
            else:
                # It's a username - we need to use the by-username endpoint
                params = {"username": user_identifier, "limit": min(limit, 25), "include_replies": False}
            
            async with httpx.AsyncClient() as client:
                headers = {"accept": "application/json", "api_key": self.api_key}
                
                if user_identifier.isdigit():
                    # Use FID-based endpoint
                    response = await client.get(
                        f"{self.base_url}/farcaster/casts",
                        headers=headers,
                        params=params,
                    )
                else:
                    # First get user info by username to get FID
                    user_response = await client.get(
                        f"{self.base_url}/farcaster/user/by-username",
                        headers=headers,
                        params={"username": user_identifier}
                    )
                    
                    if user_response.status_code != 200:
                        error_msg = f"User not found: {user_identifier}"
                        logger.error(error_msg)
                        return {"success": False, "error": error_msg, "casts": []}
                    
                    user_data = user_response.json()
                    fid = user_data.get("result", {}).get("user", {}).get("fid")
                    
                    if not fid:
                        error_msg = f"Could not get FID for user: {user_identifier}"
                        logger.error(error_msg)
                        return {"success": False, "error": error_msg, "casts": []}
                    
                    # Now get casts using FID
                    response = await client.get(
                        f"{self.base_url}/farcaster/casts",
                        headers=headers,
                        params={"fid": fid, "limit": min(limit, 25), "include_replies": False},
                    )
                
                # Update rate limit tracking
                self._update_rate_limits(response)
                
                if response.status_code != 200:
                    error_msg = f"Farcaster API error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    return {"success": False, "error": error_msg, "casts": []}
                
                data = response.json()
                casts_data = data.get("casts", [])
                
                # Convert to Message objects
                messages = []
                for cast in casts_data:
                    try:
                        cast_hash = cast.get("hash", "")
                        author = cast.get("author", {})
                        content = cast.get("text", "")
                        
                        if not content:
                            continue
                        
                        username = author.get("username", "unknown")
                        display_name = author.get("display_name", username)
                        fid = author.get("fid")
                        cast_timestamp = self._parse_timestamp(cast.get("timestamp", ""))
                        
                        # Check for replies
                        reply_to = None
                        if cast.get("parent_hash"):
                            reply_to = cast.get("parent_hash")
                        
                        message = Message(
                            id=cast_hash,
                            channel_id=f"user_{user_identifier}",
                            channel_type="farcaster",
                            sender=username,
                            content=content,
                            timestamp=cast_timestamp,
                            reply_to=reply_to,
                            sender_username=username,
                            sender_display_name=display_name,
                            sender_fid=fid,
                            sender_pfp_url=author.get("pfp_url"),
                            sender_bio=author.get("profile", {}).get("bio", {}).get("text"),
                            sender_follower_count=author.get("follower_count"),
                            sender_following_count=author.get("following_count"),
                            metadata={
                                "cast_type": "user_timeline",
                                "verified_addresses": author.get("verified_addresses", {}),
                                "power_badge": author.get("power_badge", False),
                                "channel": f"user_{user_identifier}",
                            },
                        )
                        
                        messages.append(message)
                        
                    except Exception as e:
                        logger.error(f"Error processing cast in user timeline: {e}")
                        continue
                
                logger.info(f"FarcasterObserver: Retrieved {len(messages)} casts for user {user_identifier}")
                return {
                    "success": True, 
                    "casts": messages,
                    "user_identifier": user_identifier,
                    "count": len(messages)
                }
                
        except Exception as e:
            error_msg = f"Exception while fetching user casts: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": error_msg, "casts": []}

    async def search_casts(self, query: str, channel_id: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        """
        Search for Farcaster casts matching a query, optionally within a specific channel.
        
        Args:
            query: The search term(s)
            channel_id: Optional Farcaster channel ID (e.g., "/channel/dev")
            limit: Number of casts to return (default: 10, max: 25)
            
        Returns:
            Dict with success status, casts list, and any error messages
        """
        logger.info(f"FarcasterObserver.search_casts: query='{query}', channel={channel_id}, limit={limit}")
        
        if not self.api_key:
            error_msg = "Farcaster API key not configured"
            logger.error(error_msg)
            return {"success": False, "error": error_msg, "casts": []}
        
        if not query.strip():
            error_msg = "Search query cannot be empty"
            logger.error(error_msg)
            return {"success": False, "error": error_msg, "casts": []}
        
        try:
            async with httpx.AsyncClient() as client:
                headers = {"accept": "application/json", "api_key": self.api_key}
                
                # Build search parameters
                params = {
                    "q": query.strip(),
                    "limit": min(limit, 25)
                }
                
                # Add channel filter if specified
                if channel_id:
                    # Remove leading slash if present to normalize channel ID
                    normalized_channel = channel_id.lstrip("/")
                    if normalized_channel.startswith("channel/"):
                        params["channel_id"] = normalized_channel
                    else:
                        params["channel_id"] = f"channel/{normalized_channel}"
                
                response = await client.get(
                    f"{self.base_url}/farcaster/casts/search",
                    headers=headers,
                    params=params,
                )
                
                # Update rate limit tracking
                self._update_rate_limits(response)
                
                if response.status_code != 200:
                    error_msg = f"Farcaster search API error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    return {"success": False, "error": error_msg, "casts": []}
                
                data = response.json()
                casts_data = data.get("casts", [])
                
                # Convert to Message objects
                messages = []
                for cast in casts_data:
                    try:
                        cast_hash = cast.get("hash", "")
                        author = cast.get("author", {})
                        content = cast.get("text", "")
                        
                        if not content:
                            continue
                        
                        username = author.get("username", "unknown")
                        display_name = author.get("display_name", username)
                        fid = author.get("fid")
                        cast_timestamp = self._parse_timestamp(cast.get("timestamp", ""))
                        
                        # Check for replies
                        reply_to = None
                        if cast.get("parent_hash"):
                            reply_to = cast.get("parent_hash")
                        
                        # Determine channel from cast data
                        cast_channel = "search_results"
                        if cast.get("parent_url"):
                            cast_channel = cast.get("parent_url", "search_results")
                        
                        message = Message(
                            id=cast_hash,
                            channel_id=cast_channel,
                            channel_type="farcaster",
                            sender=username,
                            content=content,
                            timestamp=cast_timestamp,
                            reply_to=reply_to,
                            sender_username=username,
                            sender_display_name=display_name,
                            sender_fid=fid,
                            sender_pfp_url=author.get("pfp_url"),
                            sender_bio=author.get("profile", {}).get("bio", {}).get("text"),
                            sender_follower_count=author.get("follower_count"),
                            sender_following_count=author.get("following_count"),
                            metadata={
                                "cast_type": "search_result",
                                "verified_addresses": author.get("verified_addresses", {}),
                                "power_badge": author.get("power_badge", False),
                                "search_query": query,
                                "channel": cast_channel,
                            },
                        )
                        
                        messages.append(message)
                        
                    except Exception as e:
                        logger.error(f"Error processing search result cast: {e}")
                        continue
                
                logger.info(f"FarcasterObserver: Found {len(messages)} casts for query '{query}'")
                return {
                    "success": True, 
                    "casts": messages,
                    "query": query,
                    "channel_id": channel_id,
                    "count": len(messages)
                }
                
        except Exception as e:
            error_msg = f"Exception while searching casts: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": error_msg, "casts": []}

    async def get_trending_casts(self, channel_id: Optional[str] = None, timeframe_hours: int = 24, limit: int = 10) -> Dict[str, Any]:
        """
        Fetch trending Farcaster casts, optionally within a specific channel and timeframe.
        
        Args:
            channel_id: Optional Farcaster channel ID (e.g., "/channel/dev")
            timeframe_hours: Lookback period in hours (default: 24)
            limit: Number of casts to return (default: 10, max: 25)
            
        Returns:
            Dict with success status, casts list, and any error messages
        """
        logger.info(f"FarcasterObserver.get_trending_casts: channel={channel_id}, timeframe={timeframe_hours}h, limit={limit}")
        
        if not self.api_key:
            error_msg = "Farcaster API key not configured"
            logger.error(error_msg)
            return {"success": False, "error": error_msg, "casts": []}
        
        try:
            async with httpx.AsyncClient() as client:
                headers = {"accept": "application/json", "api_key": self.api_key}
                
                # Calculate timeframe cutoff
                cutoff_time = time.time() - (timeframe_hours * 3600)
                cutoff_iso = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(cutoff_time))
                
                # Build parameters for trending feed
                params = {
                    "limit": min(limit, 25),
                    "with_likes": True,
                    "with_recasts": True,
                }
                
                # If channel specified, get channel-specific trending
                if channel_id:
                    # Normalize channel ID
                    normalized_channel = channel_id.lstrip("/")
                    if not normalized_channel.startswith("channel/"):
                        normalized_channel = f"channel/{normalized_channel}"
                    
                    # Use channel feed endpoint with sorting
                    response = await client.get(
                        f"{self.base_url}/farcaster/feed/channels",
                        headers=headers,
                        params={
                            "channel_ids": normalized_channel,
                            "limit": min(limit * 2, 50),  # Get more to filter by timeframe
                            "with_likes": True,
                            "with_recasts": True,
                        },
                    )
                else:
                    # Use global trending feed - this may require using the general feed with sorting
                    response = await client.get(
                        f"{self.base_url}/farcaster/feed",
                        headers=headers,
                        params={
                            "feed_type": "filter",
                            "filter_type": "global_trending",
                            "limit": min(limit * 2, 50),  # Get more to filter by timeframe
                            "with_likes": True,
                            "with_recasts": True,
                        },
                    )
                
                # Update rate limit tracking
                self._update_rate_limits(response)
                
                if response.status_code != 200:
                    error_msg = f"Farcaster trending API error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    return {"success": False, "error": error_msg, "casts": []}
                
                data = response.json()
                casts_data = data.get("casts", [])
                
                # Filter by timeframe and sort by engagement
                filtered_casts = []
                for cast in casts_data:
                    cast_timestamp = self._parse_timestamp(cast.get("timestamp", ""))
                    if cast_timestamp >= cutoff_time:
                        # Add engagement score for sorting
                        reactions = cast.get("reactions", {})
                        likes_count = reactions.get("likes_count", 0)
                        recasts_count = reactions.get("recasts_count", 0)
                        replies_count = cast.get("replies", {}).get("count", 0)
                        
                        # Simple engagement score: likes + 2*recasts + replies
                        engagement_score = likes_count + (2 * recasts_count) + replies_count
                        cast["_engagement_score"] = engagement_score
                        filtered_casts.append(cast)
                
                # Sort by engagement score (descending) and take the limit
                filtered_casts.sort(key=lambda x: x.get("_engagement_score", 0), reverse=True)
                trending_casts = filtered_casts[:limit]
                
                # Convert to Message objects
                messages = []
                for cast in trending_casts:
                    try:
                        cast_hash = cast.get("hash", "")
                        author = cast.get("author", {})
                        content = cast.get("text", "")
                        
                        if not content:
                            continue
                        
                        username = author.get("username", "unknown")
                        display_name = author.get("display_name", username)
                        fid = author.get("fid")
                        cast_timestamp = self._parse_timestamp(cast.get("timestamp", ""))
                        
                        # Check for replies
                        reply_to = None
                        if cast.get("parent_hash"):
                            reply_to = cast.get("parent_hash")
                        
                        # Determine channel from cast data
                        cast_channel = "trending"
                        if cast.get("parent_url"):
                            cast_channel = cast.get("parent_url", "trending")
                        elif channel_id:
                            cast_channel = channel_id
                        
                        message = Message(
                            id=cast_hash,
                            channel_id=cast_channel,
                            channel_type="farcaster",
                            sender=username,
                            content=content,
                            timestamp=cast_timestamp,
                            reply_to=reply_to,
                            sender_username=username,
                            sender_display_name=display_name,
                            sender_fid=fid,
                            sender_pfp_url=author.get("pfp_url"),
                            sender_bio=author.get("profile", {}).get("bio", {}).get("text"),
                            sender_follower_count=author.get("follower_count"),
                            sender_following_count=author.get("following_count"),
                            metadata={
                                "cast_type": "trending",
                                "verified_addresses": author.get("verified_addresses", {}),
                                "power_badge": author.get("power_badge", False),
                                "engagement_score": cast.get("_engagement_score", 0),
                                "channel": cast_channel,
                            },
                        )
                        
                        messages.append(message)
                        
                    except Exception as e:
                        logger.error(f"Error processing trending cast: {e}")
                        continue
                
                logger.info(f"FarcasterObserver: Found {len(messages)} trending casts")
                return {
                    "success": True, 
                    "casts": messages,
                    "channel_id": channel_id,
                    "timeframe_hours": timeframe_hours,
                    "count": len(messages)
                }
                
        except Exception as e:
            error_msg = f"Exception while fetching trending casts: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": error_msg, "casts": []}

    async def get_cast_by_url(self, farcaster_url: str) -> Dict[str, Any]:
        """
        Fetch the details of a specific Farcaster cast given its URL.
        
        Args:
            farcaster_url: The full URL of the Farcaster cast (e.g., Warpcast URL)
            
        Returns:
            Dict with success status, cast details, and any error messages
        """
        logger.info(f"FarcasterObserver.get_cast_by_url: url={farcaster_url}")
        
        if not self.api_key:
            error_msg = "Farcaster API key not configured"
            logger.error(error_msg)
            return {"success": False, "error": error_msg, "cast": None}
        
        if not farcaster_url.strip():
            error_msg = "URL cannot be empty"
            logger.error(error_msg)
            return {"success": False, "error": error_msg, "cast": None}
        
        try:
            # Extract cast hash from URL
            cast_hash = self._extract_cast_hash_from_url(farcaster_url)
            if not cast_hash:
                error_msg = f"Could not extract cast hash from URL: {farcaster_url}"
                logger.error(error_msg)
                return {"success": False, "error": error_msg, "cast": None}
            
            # Get cast details using the hash
            return await self.get_cast_details(cast_hash)
            
        except Exception as e:
            error_msg = f"Exception while fetching cast by URL: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": error_msg, "cast": None}

    async def get_cast_details(self, cast_hash: str) -> Dict[str, Any]:
        """
        Fetch detailed information about a specific cast by its hash.
        
        Args:
            cast_hash: The hash identifier of the cast
            
        Returns:
            Dict with success status, cast details, and any error messages
        """
        logger.info(f"FarcasterObserver.get_cast_details: hash={cast_hash}")
        
        if not self.api_key:
            error_msg = "Farcaster API key not configured"
            logger.error(error_msg)
            return {"success": False, "error": error_msg, "cast": None}
        
        if not cast_hash.strip():
            error_msg = "Cast hash cannot be empty"
            logger.error(error_msg)
            return {"success": False, "error": error_msg, "cast": None}
        
        try:
            async with httpx.AsyncClient() as client:
                headers = {"accept": "application/json", "api_key": self.api_key}
                
                response = await client.get(
                    f"{self.base_url}/farcaster/cast",
                    headers=headers,
                    params={
                        "type": "hash",
                        "identifier": cast_hash.strip()
                    },
                )
                
                # Update rate limit tracking
                self._update_rate_limits(response)
                
                if response.status_code != 200:
                    error_msg = f"Farcaster cast API error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    return {"success": False, "error": error_msg, "cast": None}
                
                data = response.json()
                cast_data = data.get("cast", {})
                
                if not cast_data:
                    error_msg = f"Cast not found: {cast_hash}"
                    logger.error(error_msg)
                    return {"success": False, "error": error_msg, "cast": None}
                
                # Convert to Message object
                try:
                    author = cast_data.get("author", {})
                    content = cast_data.get("text", "")
                    
                    username = author.get("username", "unknown")
                    display_name = author.get("display_name", username)
                    fid = author.get("fid")
                    cast_timestamp = self._parse_timestamp(cast_data.get("timestamp", ""))
                    
                    # Check for replies
                    reply_to = None
                    if cast_data.get("parent_hash"):
                        reply_to = cast_data.get("parent_hash")
                    
                    # Determine channel from cast data
                    cast_channel = "direct_access"
                    if cast_data.get("parent_url"):
                        cast_channel = cast_data.get("parent_url", "direct_access")
                    
                    message = Message(
                        id=cast_hash,
                        channel_id=cast_channel,
                        channel_type="farcaster",
                        sender=username,
                        content=content,
                        timestamp=cast_timestamp,
                        reply_to=reply_to,
                        sender_username=username,
                        sender_display_name=display_name,
                        sender_fid=fid,
                        sender_pfp_url=author.get("pfp_url"),
                        sender_bio=author.get("profile", {}).get("bio", {}).get("text"),
                        sender_follower_count=author.get("follower_count"),
                        sender_following_count=author.get("following_count"),
                        metadata={
                            "cast_type": "direct_access",
                            "verified_addresses": author.get("verified_addresses", {}),
                            "power_badge": author.get("power_badge", False),
                            "cast_hash": cast_hash,
                            "channel": cast_channel,
                            "reactions": cast_data.get("reactions", {}),
                            "replies_count": cast_data.get("replies", {}).get("count", 0),
                        },
                    )
                    
                    logger.info(f"FarcasterObserver: Successfully retrieved cast {cast_hash}")
                    return {
                        "success": True, 
                        "cast": message,
                        "cast_hash": cast_hash
                    }
                    
                except Exception as e:
                    error_msg = f"Error processing cast details: {e}"
                    logger.error(error_msg)
                    return {"success": False, "error": error_msg, "cast": None}
                
        except Exception as e:
            error_msg = f"Exception while fetching cast details: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": error_msg, "cast": None}

    def _extract_cast_hash_from_url(self, url: str) -> Optional[str]:
        """
        Extract cast hash from various Farcaster URL formats.
        
        Supports URLs from:
        - Warpcast: https://warpcast.com/username/0xHASH...
        - Direct hash URLs: https://warpcast.com/~/conversations/0xHASH...
        - Other Farcaster clients with similar patterns
        
        Args:
            url: The Farcaster cast URL
            
        Returns:
            The extracted cast hash, or None if not found
        """
        import re
        
        # Common patterns for Farcaster cast URLs
        patterns = [
            r'/0x([a-fA-F0-9]+)',  # Standard hex hash pattern
            r'/conversations/0x([a-fA-F0-9]+)',  # Conversation URL pattern
            r'cast/0x([a-fA-F0-9]+)',  # Cast-specific pattern
            r'hash=0x([a-fA-F0-9]+)',  # Query parameter pattern
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                cast_hash = "0x" + match.group(1)
                logger.debug(f"Extracted cast hash {cast_hash} from URL {url}")
                return cast_hash
        
        logger.warning(f"Could not extract cast hash from URL: {url}")
        return None
