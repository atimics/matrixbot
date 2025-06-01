#!/usr/bin/env python3
"""
Farcaster Observer (Refactored)

Orchestrates Farcaster API, data conversion, and scheduling.
"""
import logging
import time
from typing import Any, Dict, List, Optional

from ...core.world_state import Message
from .neynar_api_client import NeynarAPIClient
from .farcaster_data_converter import (
    parse_farcaster_timestamp,
    extract_cast_hash_from_url,
    convert_api_casts_to_messages,
    convert_api_notifications_to_messages,
    convert_single_api_cast_to_message,
)
from .farcaster_scheduler import FarcasterScheduler

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
            self.api_client = NeynarAPIClient(api_key=self.api_key, signer_uuid=self.signer_uuid, bot_fid=self.bot_fid)
            if self.world_state_manager:
                self.scheduler = FarcasterScheduler(api_client=self.api_client, world_state_manager=self.world_state_manager)
            else:
                logger.warning("WorldStateManager not provided to FarcasterObserver; scheduler actions will not be recorded in WSM.")
        else:
            logger.warning("No Farcaster API key provided - observer will be largely inactive.")
        self.last_check_time = time.time()
        self.observed_channels = set()
        self.last_seen_hashes = set()
        logger.info("Farcaster observer initialized (refactored)")

    async def start(self):
        if not self.api_client:
            logger.warning("Cannot start Farcaster observer: API client not initialized (missing API key).")
            return
        if self.scheduler:
            await self.scheduler.start()
            logger.info("Farcaster observer and scheduler started.")
        else:
            logger.info("Farcaster observer started (scheduler not available).")

    async def stop(self):
        logger.info("Stopping Farcaster observer...")
        if self.scheduler:
            await self.scheduler.stop()
        if self.api_client:
            await self.api_client.close()
        logger.info("Farcaster observer stopped.")

    def schedule_post(self, content: str, channel: Optional[str] = None, action_id: Optional[str] = None) -> None:
        if not self.scheduler:
            logger.error("Cannot schedule post: Scheduler not initialized.")
            return
        logger.info(f"🎯 FarcasterObserver.schedule_post action_id={action_id}")
        if self.scheduler.schedule_post(content, channel, action_id):
            logger.info("Farcaster post scheduled successfully via observer.")
        else:
            logger.warning("Farcaster post not scheduled (e.g. duplicate or other issue).")

    def schedule_reply(self, content: str, reply_to_hash: str, action_id: Optional[str] = None) -> None:
        if not self.scheduler:
            logger.error("Cannot schedule reply: Scheduler not initialized.")
            return
        logger.info(f"🎯 FarcasterObserver.schedule_reply action_id={action_id}")
        if self.scheduler.schedule_reply(content, reply_to_hash, action_id):
            logger.info("Farcaster reply scheduled successfully via observer.")
        else:
            logger.warning("Farcaster reply not scheduled (e.g. duplicate or other issue).")

    async def observe_feeds(
        self,
        fids: Optional[List[int]] = None,
        channels: Optional[List[str]] = None,
        include_notifications: bool = False,
        include_home_feed: bool = False,
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
            unique_messages_dict = {msg.id: msg for msg in new_messages}
            new_messages = list(unique_messages_dict.values())
            self.last_check_time = current_time
            logger.info(f"Observed {len(new_messages)} new Farcaster messages.")
            return new_messages
        except Exception as e:
            logger.error(f"Error observing Farcaster feeds: {e}", exc_info=True)
            return []

    async def _observe_user_feed(self, fid: int) -> List[Message]:
        if not self.api_client: return []
        logger.debug(f"Observing user feed for FID: {fid}")
        try:
            data = await self.api_client.get_casts_by_fid(fid)
            return convert_api_casts_to_messages(
                data.get("casts", []),
                channel_id_prefix=f"farcaster:user_{fid}",
                cast_type_metadata="user_feed",
                bot_fid=self.bot_fid,
                last_check_time_for_filtering=self.last_check_time,
                last_seen_hashes=self.last_seen_hashes
            )
        except Exception as e:
            logger.error(f"Error observing user feed {fid}: {e}", exc_info=True)
            return []

    async def _observe_channel_feed(self, channel_name: str) -> List[Message]:
        if not self.api_client: return []
        logger.debug(f"Observing channel feed for: {channel_name}")
        try:
            data = await self.api_client.get_feed_by_channel_ids(channel_ids=channel_name)
            return convert_api_casts_to_messages(
                data.get("casts", []),
                channel_id_prefix=f"farcaster:channel_{channel_name}",
                cast_type_metadata="channel_feed",
                bot_fid=self.bot_fid,
                last_check_time_for_filtering=self.last_check_time,
                last_seen_hashes=self.last_seen_hashes
            )
        except Exception as e:
            logger.error(f"Error observing channel feed {channel_name}: {e}", exc_info=True)
            return []

    async def _observe_home_feed(self) -> List[Message]:
        if not self.api_client or not self.bot_fid:
            logger.warning("Home feed observation skipped: API client or bot_fid not configured.")
            return []
        logger.debug("Observing home feed.")
        try:
            data = await self.api_client.get_home_feed(fid=self.bot_fid)
            return convert_api_casts_to_messages(
                data.get("casts", []),
                channel_id_prefix="farcaster:home",
                cast_type_metadata="home_feed",
                bot_fid=self.bot_fid,
                last_check_time_for_filtering=self.last_check_time,
                last_seen_hashes=self.last_seen_hashes
            )
        except Exception as e:
            logger.error(f"Error observing home feed: {e}", exc_info=True)
            return []

    async def _observe_notifications(self) -> List[Message]:
        if not self.api_client or not self.bot_fid:
            logger.warning("Notifications observation skipped: API client or bot_fid not configured.")
            return []
        logger.debug("Observing notifications.")
        try:
            data = await self.api_client.get_notifications(fid=self.bot_fid)
            return convert_api_notifications_to_messages(
                data.get("notifications", []),
                bot_fid=self.bot_fid,
                last_check_time_for_filtering=self.last_check_time,
                last_seen_hashes=self.last_seen_hashes
            )
        except Exception as e:
            logger.error(f"Error observing notifications: {e}", exc_info=True)
            return []

    async def _observe_mentions(self) -> List[Message]:
        if not self.api_client or not self.bot_fid:
            logger.warning("Mentions observation skipped: API client or bot_fid not configured.")
            return []
        logger.debug("Observing mentions/replies to bot.")
        try:
            data = await self.api_client.get_replies_and_recasts_for_user(fid=self.bot_fid, filter_type="replies")
            return convert_api_casts_to_messages(
                data.get("casts", []),
                channel_id_prefix="farcaster:mentions_and_replies",
                cast_type_metadata="mention_or_reply",
                bot_fid=self.bot_fid,
                last_check_time_for_filtering=self.last_check_time,
                last_seen_hashes=self.last_seen_hashes
            )
        except Exception as e:
            logger.error(f"Error observing mentions/replies: {e}", exc_info=True)
            return []

    # --- Direct Action Methods ---
    
    async def post_cast(
        self,
        content: str,
        channel: Optional[str] = None,
        embed_urls: Optional[List[str]] = None,
        action_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Post a cast directly (not scheduled)."""
        if not self.api_client:
            return {"success": False, "error": "API client not initialized"}
        logger.info(f"🎯 FarcasterObserver.post_cast action_id={action_id}")
        embeds = [{"url": url} for url in embed_urls] if embed_urls else None
        return await self.api_client.publish_cast(content, self.signer_uuid, channel, embeds=embeds)

    async def reply_to_cast(
        self,
        content: str,
        reply_to_hash: str,
        action_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reply to a cast directly (not scheduled)."""
        if not self.api_client:
            return {"success": False, "error": "API client not initialized"}
        logger.info(f"🎯 FarcasterObserver.reply_to_cast action_id={action_id}")
        return await self.api_client.reply_to_cast(content, reply_to_hash)

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
        return await self.api_client.quote_cast(content, quoted_cast_hash, channel, embed_urls)

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

    async def send_dm(self, fid: int, content: str) -> Dict[str, Any]:
        """Send a direct message."""
        if not self.api_client:
            return {"success": False, "error": "API client not initialized"}
        return await self.api_client.send_dm(fid, content, self.signer_uuid)

    async def get_user_casts(self, user_identifier: str, limit: int = 10) -> Dict[str, Any]:
        """Get casts by a user."""
        if not self.api_client:
            return {"success": False, "casts": [], "error": "API client not initialized"}
        try:
            try:
                fid = int(user_identifier)
            except ValueError:
                # Try to resolve username to FID
                user_data = await self.api_client.get_user_by_username(user_identifier)
                if not user_data.get("users"):
                    return {"success": False, "casts": [], "error": f"User '{user_identifier}' not found"}
                fid = user_data["users"][0]["fid"]
            
            data = await self.api_client.get_casts_by_fid(fid, limit=limit)
            messages = convert_api_casts_to_messages(
                data.get("casts", []),
                channel_id_prefix=f"farcaster:user_{fid}",
                cast_type_metadata="user_feed",
                bot_fid=self.bot_fid
            )
            return {"success": True, "casts": [msg.model_dump() for msg in messages], "error": None}
        except Exception as e:
            logger.error(f"Error getting user casts for {user_identifier}: {e}", exc_info=True)
            return {"success": False, "casts": [], "error": str(e)}

    async def search_casts(self, query: str, channel_id: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        """Search for casts."""
        if not self.api_client:
            return {"success": False, "casts": [], "error": "API client not initialized"}
        
        try:
            data = await self.api_client.search_casts(query, channel_id, limit)
            messages = convert_api_casts_to_messages(
                data.get("casts", []),
                channel_id_prefix=f"farcaster:search_{query}",
                cast_type_metadata="search_result",
                bot_fid=self.bot_fid
            )
            return {"success": True, "casts": [msg.model_dump() for msg in messages], "error": None}
        except Exception as e:
            logger.error(f"Error searching casts for query '{query}': {e}", exc_info=True)
            return {"success": False, "casts": [], "error": str(e)}

    async def get_trending_casts(self, channel_id: Optional[str] = None, timeframe_hours: int = 24, limit: int = 10) -> Dict[str, Any]:
        """Get trending casts."""
        if not self.api_client:
            return {"success": False, "casts": [], "error": "API client not initialized"}
        
        try:
            data = await self.api_client.get_trending_casts(channel_id, timeframe_hours, limit)
            messages = convert_api_casts_to_messages(
                data.get("casts", []),
                channel_id_prefix=f"farcaster:trending_{channel_id or 'all'}",
                cast_type_metadata="trending",
                bot_fid=self.bot_fid
            )
            return {"success": True, "casts": [msg.model_dump() for msg in messages], "error": None}
        except Exception as e:
            logger.error(f"Error getting trending casts: {e}", exc_info=True)
            return {"success": False, "casts": [], "error": str(e)}

    async def get_cast_by_url(self, farcaster_url: str) -> Dict[str, Any]:
        """Get cast details by Farcaster URL."""
        if not self.api_client:
            return {"success": False, "cast": None, "error": "API client not initialized"}
        
        try:
            cast_hash = extract_cast_hash_from_url(farcaster_url)
            if not cast_hash:
                return {"success": False, "cast": None, "error": "Invalid Farcaster URL - could not extract cast hash"}
            
            result = await self.get_cast_details(cast_hash)
            return {
                "success": result.get("cast") is not None,
                "cast": result.get("cast"),
                "error": result.get("error")
            }
        except Exception as e:
            logger.error(f"Error getting cast by URL '{farcaster_url}': {e}", exc_info=True)
            return {"success": False, "cast": None, "error": str(e)}

    async def get_cast_details(self, cast_hash: str) -> Dict[str, Any]:
        """Get cast details by hash."""
        if not self.api_client:
            return {"success": False, "cast": None, "error": "API client not initialized"}
        
        try:
            data = await self.api_client.get_cast_by_hash(cast_hash)
            if not data.get("cast"):
                return {"success": False, "cast": None, "error": "Cast not found"}
            
            message = convert_single_api_cast_to_message(
                data["cast"],
                channel_id_prefix="farcaster:cast_details",
                cast_type_metadata="cast_detail",
                bot_fid=self.bot_fid
            )
            return {"success": True, "cast": message.model_dump() if message else None, "error": None}
        except Exception as e:
            logger.error(f"Error getting cast details for hash '{cast_hash}': {e}", exc_info=True)
            return {"success": False, "cast": None, "error": str(e)}
