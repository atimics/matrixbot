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
                            # Track that we've replied to this cast to prevent duplicate replies
                            self.replied_to_hashes.add(reply_to_hash)
                            logger.info(f"✅ Added {reply_to_hash} to replied_to_hashes set")
                            
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
        if reply_to_hash in self.last_seen_hashes:
            logger.warning(f"Skipping duplicate reply to cast {reply_to_hash}")
            return {"success": False, "error": "duplicate reply", "cast_hash": None}
        # Use post_cast with parent reply_to parameter
        result = await self.post_cast(
            content=content, channel=channel, reply_to=reply_to_hash
        )
        # Record that we've replied to this cast to prevent future duplicates
        if result.get("success"):
            self.last_seen_hashes.add(reply_to_hash)
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

    async def follow_user(self, fid: int) -> Dict[str, Any]:
        """
        Follow a Farcaster user by FID

        Args:
            fid: Farcaster user ID to follow

        Returns:
            Result dict with success status
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

        Args:
            fid: Farcaster user ID to unfollow

        Returns:
            Result dict with success status
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

        Args:
            fid: Recipient Farcaster user ID
            content: Text content of the DM

        Returns:
            Result dict with success status and message id
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

    def _update_rate_limits(self, response: httpx.Response) -> None:
        """
        Update rate limit tracking from API response headers

        Args:
            response: HTTP response object containing rate limit headers
        """
        try:
            # Common rate limit headers from Farcaster/Neynar API
            rate_limit_headers = {
                "x-ratelimit-limit": "limit",
                "x-ratelimit-remaining": "remaining",
                "x-ratelimit-reset": "reset_time",
                "x-ratelimit-retry-after": "retry_after",
                "ratelimit-limit": "limit",
                "ratelimit-remaining": "remaining",
                "ratelimit-reset": "reset_time",
            }

            rate_limit_info = {}
            for header_name, info_key in rate_limit_headers.items():
                header_value = response.headers.get(header_name)
                if header_value:
                    if info_key in ["limit", "remaining"]:
                        rate_limit_info[info_key] = int(header_value)
                    elif info_key == "reset_time":
                        # Could be Unix timestamp or seconds until reset
                        rate_limit_info[info_key] = int(header_value)
                    elif info_key == "retry_after":
                        rate_limit_info[info_key] = int(header_value)

            if rate_limit_info:
                # Store in world state for AI system awareness
                if hasattr(self, "world_state_manager") and self.world_state_manager:
                    current_time = time.time()
                    rate_limit_info["last_updated"] = current_time

                    # Update world state with rate limit info
                    world_state = self.world_state_manager.state
                    world_state.rate_limits = getattr(world_state, "rate_limits", {})
                    world_state.rate_limits["farcaster_api"] = rate_limit_info

                    # Propagate to system_status for AI visibility
                    try:
                        self.world_state_manager.update_system_status(
                            {"rate_limits": world_state.rate_limits}
                        )
                    except Exception as e:
                        logger.debug(
                            f"Error updating system_status with rate limits: {e}"
                        )

                    # Log if we're approaching limits
                    remaining = rate_limit_info.get("remaining", float("inf"))
                    limit = rate_limit_info.get("limit", 0)

                    if limit > 0:
                        usage_percent = ((limit - remaining) / limit) * 100
                        if usage_percent > 80:
                            logger.warning(
                                f"Farcaster API rate limit usage high: {usage_percent:.1f}% ({remaining}/{limit} remaining)"
                            )
                        elif usage_percent > 50:
                            logger.info(
                                f"Farcaster API rate limit usage: {usage_percent:.1f}% ({remaining}/{limit} remaining)"
                            )

        except Exception as e:
            logger.debug(f"Error parsing rate limit headers: {e}")

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """
        Get current rate limit status

        Returns:
            Dictionary with rate limit information
        """
        if not hasattr(self, "world_state_manager") or not self.world_state_manager:
            return {"available": False, "reason": "No world state manager"}

        world_state = self.world_state_manager.state
        if (
            not hasattr(world_state, "rate_limits")
            or "farcaster_api" not in world_state.rate_limits
        ):
            return {"available": False, "reason": "No rate limit data"}

        rate_limit_info = world_state.rate_limits["farcaster_api"]
        current_time = time.time()

        # Check if data is stale (older than 5 minutes)
        last_updated = rate_limit_info.get("last_updated", 0)
        if current_time - last_updated > 300:
            return {"available": False, "reason": "Rate limit data is stale"}

        return {
            "available": True,
            "limit": rate_limit_info.get("limit"),
            "remaining": rate_limit_info.get("remaining"),
            "reset_time": rate_limit_info.get("reset_time"),
            "retry_after": rate_limit_info.get("retry_after"),
            "last_updated": last_updated,
            "age_seconds": current_time - last_updated,
        }

    def is_connected(self) -> bool:
        """Check if the Farcaster observer is connected and ready"""
        return self.api_key is not None and self.signer_uuid is not None

    def can_observe_notifications(self) -> bool:
        """Check if the observer can fetch notifications (requires bot FID)"""
        return self.api_key is not None and self.bot_fid is not None

    def get_status(self) -> Dict[str, Any]:
        """Get current observer status"""
        status = {
            "connected": self.is_connected(),
            "can_observe_notifications": self.can_observe_notifications(),
            "last_check_time": self.last_check_time,
            "observed_channels": list(self.observed_channels),
            "seen_hashes_count": len(self.last_seen_hashes),
            "bot_fid": self.bot_fid,
        }

        # Add rate limit status
        rate_limit_status = self.get_rate_limit_status()
        status["rate_limits"] = rate_limit_status

        return status

    def format_user_mention(self, message: Message) -> str:
        """
        Format a user mention for Farcaster replies

        Args:
            message: Message object containing user information

        Returns:
            Properly formatted mention string (e.g., "@username")
        """
        if message.channel_type != "farcaster":
            return message.sender

        username = message.sender_username or message.sender
        if username and not username.startswith("@"):
            return f"@{username}"
        return username or message.sender

    def get_user_context(self, message: Message) -> Dict[str, Any]:
        """
        Get comprehensive user context for AI decision making

        Args:
            message: Message object containing user information

        Returns:
            Dictionary with user context including engagement levels, verification status, etc.
        """
        if message.channel_type != "farcaster":
            return {"platform": "matrix", "username": message.sender}

        context = {
            "platform": "farcaster",
            "username": message.sender_username or message.sender,
            "display_name": message.sender_display_name,
            "fid": message.sender_fid,
            "follower_count": message.sender_follower_count or 0,
            "following_count": message.sender_following_count or 0,
            "verified": bool(message.metadata.get("verified_addresses", {})),
            "power_badge": message.metadata.get("power_badge", False),
            "engagement_level": self._calculate_engagement_level(message),
            "taggable_mention": self.format_user_mention(message),
        }

        return context

    def _calculate_engagement_level(self, message: Message) -> str:
        """
        Calculate user engagement level based on follower count and other metrics

        Args:
            message: Message object with user information

        Returns:
            Engagement level: "low", "medium", "high", "influencer"
        """
        follower_count = message.sender_follower_count or 0
        power_badge = message.metadata.get("power_badge", False)

        if power_badge or follower_count > 10000:
            return "influencer"
        elif follower_count > 1000:
            return "high"
        elif follower_count > 100:
            return "medium"
        else:
            return "low"

    def get_thread_context(self, message: Message) -> Dict[str, Any]:
        """
        Get thread context for a message to understand conversation flow

        Args:
            message: Message object

        Returns:
            Dictionary with thread context information
        """
        if not self.world_state_manager:
            return {"thread_available": False}

        world_state = self.world_state_manager.state

        # For replies, get the thread context
        if message.reply_to:
            thread_messages = world_state.threads.get(message.reply_to, [])
            thread_root = world_state.thread_roots.get(message.reply_to)

            return {
                "thread_available": True,
                "is_reply": True,
                "thread_length": len(thread_messages),
                "thread_root": {
                    "sender": thread_root.sender_username if thread_root else None,
                    "content_preview": thread_root.content[:100] + "..."
                    if thread_root and len(thread_root.content) > 100
                    else thread_root.content
                    if thread_root
                    else None,
                }
                if thread_root
                else None,
                "recent_participants": list(
                    set(
                        [
                            msg.sender_username
                            for msg in thread_messages[-5:]
                            if msg.sender_username
                        ]
                    )
                ),
            }
        else:
            # This is a root message, check if it has replies
            thread_messages = world_state.threads.get(message.id, [])
            return {
                "thread_available": True,
                "is_reply": False,
                "has_replies": len(thread_messages)
                > 1,  # > 1 because root message is included
                "reply_count": max(0, len(thread_messages) - 1),
                "participants": list(
                    set(
                        [
                            msg.sender_username
                            for msg in thread_messages
                            if msg.sender_username
                        ]
                    )
                ),
            }
