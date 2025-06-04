#!/usr/bin/env python3
"""
Farcaster Observer (Refactored)

Orchestrates Farcaster API, data conversion, and scheduling.
"""
import asyncio
import logging
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from ...core.world_state import Message
from .farcaster_data_converter import (
    convert_api_casts_to_messages,
    convert_api_notifications_to_messages,
    convert_single_api_cast_to_message,
    extract_cast_hash_from_url,
    parse_farcaster_timestamp,
)
from .farcaster_scheduler import FarcasterScheduler
from .neynar_api_client import NeynarAPIClient

logger = logging.getLogger(__name__)


class FarcasterObserver:
    """
    Orchestrates Farcaster API, data conversion, and scheduling.
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
        self.bot_fid = str(bot_fid) if bot_fid else None
        self.world_state_manager = world_state_manager
        self.api_client: Optional[NeynarAPIClient] = None
        self.scheduler: Optional[FarcasterScheduler] = None
        if self.api_key:
            self.api_client = NeynarAPIClient(
                api_key=self.api_key, signer_uuid=self.signer_uuid, bot_fid=self.bot_fid
            )
            if self.world_state_manager:
                self.scheduler = FarcasterScheduler(
                    api_client=self.api_client,
                    world_state_manager=self.world_state_manager,
                )
            else:
                logger.warning(
                    "WorldStateManager not provided to FarcasterObserver; scheduler actions will not be recorded in WSM."
                )
        else:
            logger.warning(
                "No Farcaster API key provided - observer will be largely inactive."
            )
        self.last_check_time = time.time()
        self.observed_channels = set()
        self.last_seen_hashes = set()
        
        # World state collection settings
        self.world_state_collection_enabled = True
        self.world_state_collection_interval = 300.0  # 5 minutes
        self._world_state_task: Optional[Any] = None  # asyncio.Task
        
        # Ecosystem token service
        self.ecosystem_token_service: Optional[Any] = None  # EcosystemTokenService
        
        logger.info("Farcaster observer initialized (refactored)")

    async def start(self):
        if not self.api_client:
            logger.warning(
                "Cannot start Farcaster observer: API client not initialized (missing API key)."
            )
            return
        if self.scheduler:
            await self.scheduler.start()
            logger.info("Farcaster observer and scheduler started.")
        else:
            logger.info("Farcaster observer started (scheduler not available).")
            
        # Initialize and start ecosystem token service if configured
        from ...config import settings
        if settings.ECOSYSTEM_TOKEN_CONTRACT_ADDRESS and self.api_client and self.world_state_manager:
            from ...integrations.ecosystem_token_service import EcosystemTokenService
            self.ecosystem_token_service = EcosystemTokenService(self.api_client, self.world_state_manager)
            await self.ecosystem_token_service.start()
            logger.info("Ecosystem Token Service started.")
            
        # Start world state collection loop if enabled
        if self.world_state_collection_enabled and self.world_state_manager:
            self._world_state_task = asyncio.create_task(self._world_state_collection_loop())
            logger.info("World state collection loop started.")

    async def stop(self):
        logger.info("Stopping Farcaster observer...")
        
        # Stop ecosystem token service
        if self.ecosystem_token_service:
            await self.ecosystem_token_service.stop()
        
        # Stop world state collection task
        if self._world_state_task and not self._world_state_task.done():
            self._world_state_task.cancel()
            try:
                await self._world_state_task
            except asyncio.CancelledError:
                logger.info("World state collection task cancelled successfully.")
            except Exception as e:
                logger.error(f"Error during world state task cancellation: {e}")
        
        if self.scheduler:
            await self.scheduler.stop()
        if self.api_client:
            await self.api_client.close()
        logger.info("Farcaster observer stopped.")

    def schedule_post(
        self,
        content: str,
        channel: Optional[str] = None,
        action_id: Optional[str] = None,
        embeds: Optional[list] = None,
    ) -> None:
        if not self.scheduler:
            logger.error("Cannot schedule post: Scheduler not initialized.")
            return
        logger.info(f"🎯 FarcasterObserver.schedule_post action_id={action_id}")
        if self.scheduler.schedule_post(content, channel, action_id, embeds):
            logger.info("Farcaster post scheduled successfully via observer.")
        else:
            logger.warning(
                "Farcaster post not scheduled (e.g. duplicate or other issue)."
            )

    def schedule_reply(
        self, content: str, reply_to_hash: str, action_id: Optional[str] = None
    ) -> None:
        if not self.scheduler:
            logger.error("Cannot schedule reply: Scheduler not initialized.")
            return
        logger.info(f"🎯 FarcasterObserver.schedule_reply action_id={action_id}")
        if self.scheduler.schedule_reply(content, reply_to_hash, action_id):
            logger.info("Farcaster reply scheduled successfully via observer.")
        else:
            logger.warning(
                "Farcaster reply not scheduled (e.g. duplicate or other issue)."
            )

    async def observe_feeds(
        self,
        fids: Optional[List[int]] = None,
        channels: Optional[List[str]] = None,
        include_notifications: bool = False,
        include_home_feed: bool = False,
        include_world_state_data: bool = False,
        world_state_trending_limit: int = 5,
    ) -> List[Message]:
        if not self.api_client:
            logger.warning("Cannot observe feeds: API client not initialized.")
            return []
        new_messages: List[Message] = []
        current_time = time.time()
        try:
            if fids:
                for fid_val in fids:
                    user_messages = await self._observe_user_feed(fid_val)
                    new_messages.extend(user_messages)
            if channels:
                for channel_name in channels:
                    channel_messages = await self._observe_channel_feed(channel_name)
                    new_messages.extend(channel_messages)
            if include_home_feed:
                home_messages = await self._observe_home_feed()
                new_messages.extend(home_messages)
            if include_notifications and self.bot_fid:
                notification_messages = await self._observe_notifications()
                new_messages.extend(notification_messages)
                mention_messages = await self._observe_mentions()
                new_messages.extend(mention_messages)
                
            # Enhanced world state data collection
            if include_world_state_data:
                logger.info("Collecting enhanced world state data...")
                world_state_data = await self.observe_world_state_data(
                    include_trending=True,
                    include_home_feed=False,  # Already collected above if requested
                    include_notifications=False,  # Already collected above if requested
                    trending_limit=world_state_trending_limit,
                )
                
                # Add world state data to messages and store in world state manager
                for data_type, messages in world_state_data.items():
                    new_messages.extend(messages)
                    if self.world_state_manager and messages:
                        logger.info(f"Storing {len(messages)} {data_type} messages in world state")
                        self._store_world_state_data(data_type, messages)
                        
            # Check for new casts from monitored token holders
            if self.ecosystem_token_service:
                holder_feed_messages = await self.ecosystem_token_service.observe_monitored_holder_feeds()
                new_messages.extend(holder_feed_messages)
                        
            unique_messages_dict = {msg.id: msg for msg in new_messages}
            new_messages = list(unique_messages_dict.values())
            self.last_check_time = current_time
            logger.info(f"Observed {len(new_messages)} new Farcaster messages.")
            return new_messages
        except Exception as e:
            logger.error(f"Error observing Farcaster feeds: {e}", exc_info=True)
            return []

    async def _observe_user_feed(self, fid: int) -> List[Message]:
        if not self.api_client:
            return []
        logger.debug(f"Observing user feed for FID: {fid}")
        try:
            data = await self.api_client.get_casts_by_fid(fid)
            return await convert_api_casts_to_messages(
                data.get("casts", []),
                channel_id_prefix=f"farcaster:user_{fid}",
                cast_type_metadata="user_feed",
                bot_fid=self.bot_fid,
                last_check_time_for_filtering=self.last_check_time,
                last_seen_hashes=self.last_seen_hashes,
            )
        except Exception as e:
            logger.error(f"Error observing user feed {fid}: {e}", exc_info=True)
            return []

    async def _observe_channel_feed(self, channel_name: str) -> List[Message]:
        if not self.api_client:
            return []
        logger.debug(f"Observing channel feed for: {channel_name}")
        try:
            data = await self.api_client.get_feed_by_channel_ids(
                channel_ids=channel_name
            )
            return await convert_api_casts_to_messages(
                data.get("casts", []),
                channel_id_prefix=f"farcaster:channel_{channel_name}",
                cast_type_metadata="channel_feed",
                bot_fid=self.bot_fid,
                last_check_time_for_filtering=self.last_check_time,
                last_seen_hashes=self.last_seen_hashes,
            )
        except Exception as e:
            logger.error(
                f"Error observing channel feed {channel_name}: {e}", exc_info=True
            )
            return []

    async def _observe_home_feed(self) -> List[Message]:
        if not self.api_client or not self.bot_fid:
            logger.warning(
                "Home feed observation skipped: API client or bot_fid not configured."
            )
            return []
        logger.debug("Observing home feed.")
        try:
            data = await self.api_client.get_home_feed(fid=self.bot_fid)
            return await convert_api_casts_to_messages(
                data.get("casts", []),
                channel_id_prefix="farcaster:home",
                cast_type_metadata="home_feed",
                bot_fid=self.bot_fid,
                last_check_time_for_filtering=self.last_check_time,
                last_seen_hashes=self.last_seen_hashes,
            )
        except Exception as e:
            logger.error(f"Error observing home feed: {e}", exc_info=True)
            return []

    async def _observe_notifications(self) -> List[Message]:
        if not self.api_client or not self.bot_fid:
            logger.warning(
                "Notifications observation skipped: API client or bot_fid not configured."
            )
            return []
        logger.debug("Observing notifications.")
        try:
            data = await self.api_client.get_notifications(fid=self.bot_fid)
            return await convert_api_notifications_to_messages(
                data.get("notifications", []),
                bot_fid=self.bot_fid,
                last_check_time_for_filtering=self.last_check_time,
                last_seen_hashes=self.last_seen_hashes,
            )
        except Exception as e:
            logger.error(f"Error observing notifications: {e}", exc_info=True)
            return []

    async def _observe_mentions(self) -> List[Message]:
        if not self.api_client or not self.bot_fid:
            logger.warning(
                "Mentions observation skipped: API client or bot_fid not configured."
            )
            return []
        logger.debug("Observing mentions/replies to bot.")
        try:
            data = await self.api_client.get_replies_and_recasts_for_user(
                fid=self.bot_fid, filter_type="replies"
            )
            return await convert_api_casts_to_messages(
                data.get("casts", []),
                channel_id_prefix="farcaster:mentions_and_replies",
                cast_type_metadata="mention_or_reply",
                bot_fid=self.bot_fid,
                last_check_time_for_filtering=self.last_check_time,
                last_seen_hashes=self.last_seen_hashes,
            )
        except Exception as e:
            logger.error(f"Error observing mentions/replies: {e}", exc_info=True)
            return []

    async def _observe_trending_casts(self, limit: int = 10) -> List[Message]:
        """Observe trending casts for world state context."""
        if not self.api_client:
            return []
        logger.debug("Observing trending casts for world state.")
        try:
            data = await self.api_client.get_trending_casts(limit=limit)
            return await convert_api_casts_to_messages(
                data.get("casts", []),
                channel_id_prefix="farcaster:trending",
                cast_type_metadata="trending_cast",
                bot_fid=self.bot_fid,
                last_check_time_for_filtering=self.last_check_time,
                last_seen_hashes=self.last_seen_hashes,
            )
        except Exception as e:
            logger.error(f"Error observing trending casts: {e}", exc_info=True)
            return []

    async def observe_world_state_data(
        self,
        include_trending: bool = True,
        include_home_feed: bool = True,
        include_notifications: bool = True,
        trending_limit: int = 10,
    ) -> Dict[str, List[Message]]:
        """
        Collect comprehensive world state data for AI context.

        Returns a dictionary with categorized message lists:
        - trending: Recent trending casts
        - home: Home timeline messages
        - notifications: Notifications and mentions
        """
        if not self.api_client:
            logger.warning("Cannot observe world state data: API client not initialized.")
            return {}

        world_state_data = {}

        try:
            if include_trending:
                trending_messages = await self._observe_trending_casts(limit=trending_limit)
                world_state_data["trending"] = trending_messages
                logger.info(f"Collected {len(trending_messages)} trending casts for world state")

            if include_home_feed:
                home_messages = await self._observe_home_feed()
                world_state_data["home"] = home_messages
                logger.info(f"Collected {len(home_messages)} home feed messages for world state")

            if include_notifications and self.bot_fid:
                notification_messages = await self._observe_notifications()
                mention_messages = await self._observe_mentions()
                world_state_data["notifications"] = notification_messages + mention_messages
                logger.info(f"Collected {len(notification_messages + mention_messages)} notifications for world state")

        except Exception as e:
            logger.error(f"Error collecting world state data: {e}", exc_info=True)

        return world_state_data

    # --- Direct Action Methods ---

    async def post_cast(
        self,
        content: str,
        channel: Optional[str] = None,
        embed_urls: Optional[List[str]] = None,
        reply_to: Optional[str] = None,
        action_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Post a cast directly (not scheduled)."""
        if not self.api_client:
            return {"success": False, "error": "API client not initialized"}
        logger.info(f"🎯 FarcasterObserver.post_cast action_id={action_id}")
        embeds = [{"url": url} for url in embed_urls] if embed_urls else None
        return await self.api_client.publish_cast(
            content, self.signer_uuid, channel, parent=reply_to, embeds=embeds
        )

    async def reply_to_cast(
        self,
        content: str,
        reply_to_hash: str,
        action_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reply to a cast directly (not scheduled)."""
        logger.info(f"🎯 FarcasterObserver.reply_to_cast action_id={action_id}")
        return await self.post_cast(
            content=content, channel=None, reply_to=reply_to_hash
        )

    async def like_cast(self, cast_hash: str) -> Dict[str, Any]:
        """Like a cast."""
        if not self.api_client:
            return {"success": False, "error": "API client not initialized"}
        return await self.api_client.react_to_cast(self.signer_uuid, "like", cast_hash)

    async def quote_cast(
        self,
        content: str,
        quoted_cast_hash: str,
        channel: Optional[str] = None,
        embed_urls: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Quote a cast."""
        if not self.api_client:
            return {"success": False, "error": "API client not initialized"}
        return await self.api_client.quote_cast(
            content, quoted_cast_hash, channel, embed_urls
        )

    async def follow_user(self, fid: int) -> Dict[str, Any]:
        """Follow a user."""
        if not self.api_client:
            return {"success": False, "error": "API client not initialized"}
        return await self.api_client.follow_user(fid, self.signer_uuid)

    async def unfollow_user(self, fid: int) -> Dict[str, Any]:
        """Unfollow a user."""
        if not self.api_client:
            return {"success": False, "error": "API client not initialized"}
        return await self.api_client.unfollow_user(fid, self.signer_uuid)

    async def delete_cast(self, cast_hash: str) -> Dict[str, Any]:
        """Delete a cast by hash."""
        if not self.api_client:
            return {"success": False, "error": "API client not initialized"}
        return await self.api_client.delete_cast(cast_hash, self.signer_uuid)

    async def delete_reaction(self, cast_hash: str) -> Dict[str, Any]:
        """Delete a reaction (like/recast) from a cast."""
        if not self.api_client:
            return {"success": False, "error": "API client not initialized"}
        return await self.api_client.delete_reaction(cast_hash, self.signer_uuid)

    async def send_dm(self, fid: int, content: str) -> Dict[str, Any]:
        """Send a direct message - DEPRECATED: Farcaster DM API not supported."""
        return {"success": False, "error": "Farcaster DM functionality is not supported by the API"}

    async def get_user_casts(
        self, user_identifier: str, limit: int = 10
    ) -> Dict[str, Any]:
        """Get casts by a user."""
        if not self.api_client:
            return {
                "success": False,
                "casts": [],
                "error": "API client not initialized",
            }
        try:
            try:
                fid = int(user_identifier)
            except ValueError:
                # Try to resolve username to FID
                user_data = await self.api_client.get_user_by_username(user_identifier)
                if not user_data.get("users"):
                    return {
                        "success": False,
                        "casts": [],
                        "error": f"User '{user_identifier}' not found",
                    }
                fid = user_data["users"][0]["fid"]

            data = await self.api_client.get_casts_by_fid(fid, limit=limit)
            messages = await convert_api_casts_to_messages(
                data.get("casts", []),
                channel_id_prefix=f"farcaster:user_{fid}",
                cast_type_metadata="user_feed",
                bot_fid=self.bot_fid,
            )
            return {
                "success": True,
                "casts": [asdict(msg) for msg in messages],
                "error": None,
            }
        except Exception as e:
            logger.error(
                f"Error getting user casts for {user_identifier}: {e}", exc_info=True
            )
            return {"success": False, "casts": [], "error": str(e)}

    async def search_casts(
        self, query: str, channel_id: Optional[str] = None, limit: int = 10
    ) -> Dict[str, Any]:
        """Search for casts."""
        if not self.api_client:
            return {
                "success": False,
                "casts": [],
                "error": "API client not initialized",
            }

        try:
            data = await self.api_client.search_casts(query, channel_id, limit)
            messages = await convert_api_casts_to_messages(
                data.get("casts", []),
                channel_id_prefix=f"farcaster:search_{query}",
                cast_type_metadata="search_result",
                bot_fid=self.bot_fid,
            )
            return {
                "success": True,
                "casts": [asdict(msg) for msg in messages],
                "error": None,
            }
        except Exception as e:
            logger.error(
                f"Error searching casts for query '{query}': {e}", exc_info=True
            )
            return {"success": False, "casts": [], "error": str(e)}

    async def get_trending_casts(
        self,
        channel_id: Optional[str] = None,
        timeframe_hours: int = 24,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Get trending casts."""
        if not self.api_client:
            return {
                "success": False,
                "casts": [],
                "error": "API client not initialized",
            }

        try:
            data = await self.api_client.get_trending_casts(
                channel_id, timeframe_hours, limit
            )
            messages = await convert_api_casts_to_messages(
                data.get("casts", []),
                channel_id_prefix=f"farcaster:trending_{channel_id or 'all'}",
                cast_type_metadata="trending",
                bot_fid=self.bot_fid,
            )
            return {
                "success": True,
                "casts": [asdict(msg) for msg in messages],
                "error": None,
            }
        except Exception as e:
            logger.error(f"Error getting trending casts: {e}", exc_info=True)
            return {"success": False, "casts": [], "error": str(e)}

    async def get_cast_by_url(self, farcaster_url: str) -> Dict[str, Any]:
        """Get cast details by Farcaster URL."""
        if not self.api_client:
            return {
                "success": False,
                "cast": None,
                "error": "API client not initialized",
            }

        try:
            cast_hash = extract_cast_hash_from_url(farcaster_url)
            if not cast_hash:
                return {
                    "success": False,
                    "cast": None,
                    "error": "Invalid Farcaster URL - could not extract cast hash",
                }

            result = await self.get_cast_details(cast_hash)
            return {
                "success": result.get("cast") is not None,
                "cast": result.get("cast"),
                "error": result.get("error"),
            }
        except Exception as e:
            logger.error(
                f"Error getting cast by URL '{farcaster_url}': {e}", exc_info=True
            )
            return {"success": False, "cast": None, "error": str(e)}

    async def get_cast_details(self, cast_hash: str) -> Dict[str, Any]:
        """Get cast details by hash."""
        if not self.api_client:
            return {
                "success": False,
                "cast": None,
                "error": "API client not initialized",
            }

        try:
            data = await self.api_client.get_cast_by_hash(cast_hash)
            if not data.get("cast"):
                return {"success": False, "cast": None, "error": "Cast not found"}

            message = await convert_single_api_cast_to_message(
                data["cast"],
                channel_id_if_unknown="farcaster:cast_details",
                cast_type_metadata="cast_detail",
            )
            return {
                "success": True,
                "cast": asdict(message) if message else None,
                "error": None,
            }
        except Exception as e:
            logger.error(
                f"Error getting cast details for hash '{cast_hash}': {e}", exc_info=True
            )
            return {"success": False, "cast": None, "error": str(e)}

    def _update_rate_limits(self, response) -> None:
        """Update rate limit information from API response headers."""
        if not self.world_state_manager:
            return

        headers = getattr(response, "headers", {})
        if not headers:
            return

        # Extract rate limit info from headers
        rate_limit_info = {}

        if "x-ratelimit-limit" in headers:
            rate_limit_info["limit"] = int(headers["x-ratelimit-limit"])
        if "x-ratelimit-remaining" in headers:
            rate_limit_info["remaining"] = int(headers["x-ratelimit-remaining"])
        if "x-ratelimit-reset" in headers:
            rate_limit_info["reset_time"] = int(headers["x-ratelimit-reset"])
        if "x-ratelimit-retry-after" in headers:
            rate_limit_info["retry_after"] = int(headers["x-ratelimit-retry-after"])

        if rate_limit_info:
            rate_limit_info["last_updated"] = time.time()
            self.world_state_manager.state.rate_limits[
                "farcaster_api"
            ] = rate_limit_info
            logger.debug(f"Updated Farcaster API rate limits: {rate_limit_info}")

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get current rate limit status."""
        if not self.world_state_manager:
            return {"available": False, "reason": "No world state manager"}

        rate_limits = self.world_state_manager.state.rate_limits.get(
            "farcaster_api", {}
        )

        if not rate_limits:
            return {"available": False, "reason": "No rate limit information"}

        # Check if information is stale (older than 5 minutes)
        last_updated = rate_limits.get("last_updated", 0)
        if time.time() - last_updated > 300:  # 5 minutes
            return {"available": False, "reason": "Rate limit information is stale"}

        remaining = rate_limits.get("remaining", 0)
        limit = rate_limits.get("limit", 0)
        retry_after = rate_limits.get("retry_after", 0)

        return {
            "available": remaining > 0,
            "limit": limit,
            "remaining": remaining,
            "retry_after": retry_after,
            "last_updated": last_updated,
        }

    def format_user_mention(self, message: Message) -> str:
        """Format a user mention from a message."""
        if hasattr(message, "sender_username") and message.sender_username:
            return f"@{message.sender_username}"
        elif hasattr(message, "sender") and message.sender:
            return f"@{message.sender}"
        else:
            return "@unknown"

    def get_user_context(self, message: Message) -> Dict[str, Any]:
        """Get user context information from a message."""
        context = {
            "username": getattr(message, "sender_username", "unknown"),
            "display_name": getattr(message, "sender_display_name", "Unknown"),
            "fid": getattr(message, "sender_fid", None),
            "follower_count": getattr(message, "sender_follower_count", 0),
            "following_count": getattr(message, "sender_following_count", 0),
            "power_badge": False,
            "verified_addresses": [],
        }

        # Extract metadata if available
        metadata = getattr(message, "metadata", {})
        if isinstance(metadata, dict):
            context["power_badge"] = metadata.get("power_badge", False)
            context["verified_addresses"] = metadata.get("verified_addresses", {})

        # Determine engagement level based on follower count
        follower_count = context.get("follower_count", 0)
        if follower_count > 1000:
            context["engagement_level"] = "high"
        elif follower_count > 100:
            context["engagement_level"] = "medium"
        else:
            context["engagement_level"] = "low"

        return context

    def _store_world_state_data(self, data_type: str, messages: List[Message]) -> None:
        """Store categorized world state data in the world state manager."""
        if not self.world_state_manager:
            return
            
        try:
            # Create a special channel for each data type
            channel_id = f"farcaster:world_state_{data_type}"
            
            # Add messages to world state manager
            for msg in messages:
                # Update the channel_id to reflect the world state category
                msg.channel_id = channel_id
                
            # Store messages in world state manager
            for msg in messages:
                try:
                    # Ensure proper signature: channel_id and message
                    self.world_state_manager.add_message(msg.channel_id, msg)
                except Exception:
                    # Log and continue on error
                    logger.error(f"WorldStateManager: Failed to add message {getattr(msg, 'id', None)}", exc_info=True)
                        
            logger.debug(f"Stored {len(messages)} {data_type} messages in world state")
            
        except Exception as e:
            logger.error(f"Error storing {data_type} world state data: {e}", exc_info=True)

    async def _world_state_collection_loop(self) -> None:
        """
        Periodic collection of world state data for AI context.
        
        This loop runs in the background and regularly collects:
        - Trending casts
        - Home timeline updates  
        - Direct messages
        - Notifications and mentions
        """
        logger.info(f"Starting world state collection loop (interval: {self.world_state_collection_interval}s)")
        
        while True:
            try:
                await asyncio.sleep(self.world_state_collection_interval)
                
                if not self.world_state_manager:
                    logger.warning("World state manager not available, skipping collection")
                    continue
                    
                logger.debug("Collecting world state data...")
                
                # Collect comprehensive world state data
                world_state_data = await self.observe_world_state_data(
                    include_trending=True,
                    include_home_feed=True,
                    include_notifications=True,
                    trending_limit=5,  # Keep smaller for regular collection
                )
                
                # Store the collected data
                total_messages = 0
                for data_type, messages in world_state_data.items():
                    if messages:
                        self._store_world_state_data(data_type, messages)
                        total_messages += len(messages)
                        
                if total_messages > 0:
                    logger.info(f"World state collection: stored {total_messages} messages across {len(world_state_data)} categories")
                else:
                    logger.debug("World state collection: no new messages found")
                    
            except asyncio.CancelledError:
                logger.info("World state collection loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in world state collection loop: {e}", exc_info=True)
                # Continue the loop despite errors
                continue

    async def collect_world_state_now(self) -> Dict[str, Any]:
        """
        Manually trigger immediate world state collection.
        
        Returns:
            Dictionary with collection results and statistics
        """
        if not self.world_state_manager:
            return {"error": "World state manager not available"}
            
        try:
            logger.info("Manual world state collection triggered")
            
            world_state_data = await self.observe_world_state_data(
                include_trending=True,
                include_home_feed=True,
                include_notifications=True,
                trending_limit=10,  # Larger limit for manual collection
            )
            
            results = {}
            total_messages = 0
            
            for data_type, messages in world_state_data.items():
                if messages:
                    self._store_world_state_data(data_type, messages)
                    results[data_type] = len(messages)
                    total_messages += len(messages)
                else:
                    results[data_type] = 0
                    
            results["total_messages"] = total_messages
            results["success"] = True
            
            logger.info(f"Manual world state collection complete: {total_messages} messages collected")
            return results
            
        except Exception as e:
            logger.error(f"Error in manual world state collection: {e}", exc_info=True)
            return {"error": str(e), "success": False}
