#!/usr/bin/env python3
"""
Farcaster Observer (Refactored)

Orchestrates Farcaster API, data conversion, and scheduling.
"""
import asyncio
import json
import logging
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core.world_state import Message
from ..base import Integration, IntegrationError, IntegrationConnectionError
from ..base_observer import BaseObserver, ObserverStatus
from .farcaster_data_converter import (
    convert_api_casts_to_messages,
    convert_api_notifications_to_messages,
    convert_single_api_cast_to_message,
    extract_cast_hash_from_url,
    parse_farcaster_timestamp,
)
from .farcaster_scheduler import FarcasterScheduler
from .neynar_api_client import NeynarAPIClient, NeynarNetworkError, NeynarAPIError, NeynarRateLimitError

logger = logging.getLogger(__name__)


class FarcasterObserver(Integration, BaseObserver):
    """
    Orchestrates Farcaster API, data conversion, and scheduling.
    """

    def __init__(
        self,
        integration_id: str = "farcaster",
        display_name: str = "Farcaster Integration",
        config: Dict[str, Any] = None,
        api_key: Optional[str] = None,
        signer_uuid: Optional[str] = None,
        bot_fid: Optional[str] = None,
        world_state_manager=None,
    ):
        Integration.__init__(self, integration_id, display_name, config or {})
        BaseObserver.__init__(self, integration_id, display_name)
        self.api_key = api_key
        self.signer_uuid = signer_uuid
        self.bot_fid = str(bot_fid) if bot_fid else None
        self.world_state_manager = world_state_manager
        self.api_client: Optional[NeynarAPIClient] = None
        self.scheduler: Optional[FarcasterScheduler] = None
        self.neynar_api_client: Optional[NeynarAPIClient] = None  # Legacy compatibility
        
        # File-based persistence setup
        self.persistence_dir = Path("data/farcaster_state")
        self.persistence_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.persistence_dir / "observer_state.json"
        
        # Initialize connection state
        self._set_status(ObserverStatus.DISCONNECTED)
        
        # Check if properly configured
        self._enabled = bool(self.api_key)
        
        if self.api_key:
            self._initialize_api_client()
        else:
            self._set_status(ObserverStatus.ERROR, "No Farcaster API key provided - observer will be largely inactive.")
            
        # Load persistent state
        self._load_persistent_state()
        
        self.observed_channels = set()
        self.last_seen_hashes = set()
        
        # World state collection settings
        self.world_state_collection_enabled = True
        self.world_state_collection_interval = 300.0  # 5 minutes
        self._world_state_task: Optional[Any] = None  # asyncio.Task
        
        # Ecosystem token service
        self.ecosystem_token_service: Optional[Any] = None  # EcosystemTokenService
        
        # State change callback for MainOrchestrator integration (legacy)
        self.on_state_change: Optional[callable] = None
        
        # Processing hub connection for trigger generation
        self.processing_hub = None
        
        logger.debug("Farcaster observer initialized (refactored)")

    def _initialize_api_client(self) -> None:
        """Initialize the API client with proper error handling"""
        try:
            # Load network configuration from settings
            from ...config import settings
            
            self.api_client = NeynarAPIClient(
                api_key=self.api_key,
                signer_uuid=self.signer_uuid,
                bot_fid=self.bot_fid,
                base_url="https://api.neynar.com",  # Default Neynar API URL
                max_retries=settings.farcaster.api_max_retries,
                base_delay=settings.farcaster.api_base_delay,
                max_delay=settings.farcaster.api_max_delay,
                timeout=settings.farcaster.api_timeout,
            )
            self.neynar_api_client = self.api_client  # Legacy compatibility
            
            if self.world_state_manager:
                self.scheduler = FarcasterScheduler(
                    api_client=self.api_client,
                    world_state_manager=self.world_state_manager,
                )
            else:
                logger.warning(
                    "WorldStateManager not provided to FarcasterObserver; scheduler actions will not be recorded in WSM."
                )
            
            logger.debug("Farcaster API client initialized successfully")
        except Exception as e:
            error_msg = f"Failed to initialize Farcaster API client: {e}"
            self._set_status(ObserverStatus.ERROR, error_msg)
            raise IntegrationError(error_msg) from e

    def _load_persistent_state(self) -> None:
        """Load persistent state from file"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    state_data = json.load(f)
                self.last_check_time = state_data.get('last_check_time', time.time())
                logger.debug(f"Loaded persistent state: last_check_time={self.last_check_time}")
            else:
                self.last_check_time = time.time()
                logger.debug("No persistent state found, starting fresh")
        except Exception as e:
            logger.error(f"Error loading persistent state: {e}", exc_info=True)
            self.last_check_time = time.time()

    def _save_persistent_state(self) -> None:
        """Save persistent state to file"""
        try:
            state_data = {
                'last_check_time': self.last_check_time,
                'saved_at': time.time()
            }
            with open(self.state_file, 'w') as f:
                json.dump(state_data, f, indent=2)
            logger.debug(f"Saved persistent state: last_check_time={self.last_check_time}")
        except Exception as e:
            logger.error(f"Error saving persistent state: {e}", exc_info=True)
        
    @property
    def enabled(self) -> bool:
        """Check if integration is enabled and properly configured."""
        return self._enabled

    @property
    def integration_type(self) -> str:
        """Return the integration type identifier."""
        return "farcaster"

    async def connect(self, credentials: Optional[Dict[str, Any]] = None) -> bool:
        """Connect to Farcaster API and start observing."""
        if not self.enabled:
            self._set_status(ObserverStatus.ERROR, "Farcaster observer is disabled due to missing API key")
            return False
            
        if not self.api_client:
            self._set_status(ObserverStatus.ERROR, "Cannot start Farcaster observer: API client not initialized")
            return False
        
        try:
            self._set_status(ObserverStatus.CONNECTING)
            self._increment_connection_attempts()
            
            if self.scheduler:
                await self.scheduler.start()
                logger.info("Farcaster observer and scheduler started.")
            else:
                logger.info("Farcaster observer started (scheduler not available).")
                
            # Initialize and start ecosystem token service if configured
            from ...config import settings
            if settings.ecosystem.token_contract_address and self.api_client and self.world_state_manager:
                from ...integrations.ecosystem_token_service import EcosystemTokenService
                self.ecosystem_token_service = EcosystemTokenService(self.api_client, self.world_state_manager)
                await self.ecosystem_token_service.start()
                logger.debug("Ecosystem Token Service started.")
                
            # Start world state collection loop if enabled
            if self.world_state_collection_enabled and self.world_state_manager:
                self._world_state_task = asyncio.create_task(self._world_state_collection_loop())
                logger.debug("World state collection loop started.")
                
            self.is_connected = True
            self._set_status(ObserverStatus.CONNECTED)
            self._reset_connection_attempts()
            return True
            
        except Exception as e:
            error_msg = f"Failed to connect Farcaster observer: {e}"
            self._set_status(ObserverStatus.ERROR, error_msg)
            logger.error(error_msg, exc_info=True)
            return False

    async def disconnect(self) -> None:
        """Disconnect from Farcaster API."""
        if not self.enabled:
            return
            
        logger.debug("FarcasterObserver: Disconnecting from Farcaster...")
        
        try:
            # Stop ecosystem token service
            if hasattr(self, 'ecosystem_token_service') and self.ecosystem_token_service:
                await self.ecosystem_token_service.stop()
                self.ecosystem_token_service = None
            
            # Stop world state collection task
            if hasattr(self, '_world_state_task') and self._world_state_task and not self._world_state_task.done():
                self._world_state_task.cancel()
                try:
                    await self._world_state_task
                except asyncio.CancelledError:
                    logger.debug("World state collection task cancelled successfully.")
                except Exception as e:
                    logger.error(f"Error during world state task cancellation: {e}")
                self._world_state_task = None
                
            # Stop scheduler
            if self.scheduler:
                await self.scheduler.stop()
                
            # Close API client
            if self.api_client:
                await self.api_client.close()
                
            self.is_connected = False
            self._set_status(ObserverStatus.DISCONNECTED)
            logger.info("FarcasterObserver: Disconnected from Farcaster")
            
        except Exception as e:
            error_msg = f"Error during Farcaster disconnect: {e}"
            self._set_status(ObserverStatus.ERROR, error_msg)
            logger.error(error_msg, exc_info=True)

    async def is_healthy(self) -> bool:
        """Check if the observer is healthy and operational."""
        if not self.enabled:
            return False
            
        if not self.api_client:
            return False
            
        if self.status != ObserverStatus.CONNECTED:
            return False
            
        try:
            # Test API connectivity with a simple call
            if self.bot_fid:
                result = await self.api_client.get_user_by_fid(int(self.bot_fid))
                return result is not None
            else:
                # If no bot_fid, just check if we have a valid API key
                return bool(self.api_client.api_key)
        except Exception as e:
            logger.warning(f"Farcaster health check failed: {e}")
            return False

    async def get_status(self) -> Dict[str, Any]:
        """Get current status of the Farcaster integration."""
        base_status = self.get_status_info()
        
        if not self.enabled:
            return {
                **base_status,
                "connected": False,
                "enabled": False,
                "error": "Missing API key"
            }
            
        return {
            **base_status,
            "connected": self.is_connected,
            "api_key_configured": bool(self.api_key),
            "signer_uuid": self.signer_uuid,
            "bot_fid": self.bot_fid,
            "scheduler_available": self.scheduler is not None,
            "world_state_collection_enabled": self.world_state_collection_enabled,
            "ecosystem_token_service_active": hasattr(self, 'ecosystem_token_service') and self.ecosystem_token_service is not None
        }

    async def test_connection(self) -> Dict[str, Any]:
        """Test if Farcaster API connection is working."""
        if not self.enabled or not self.api_client:
            return {"success": False, "error": "API client not initialized or disabled"}
            
        try:
            # Try a simple API call to test connection
            if self.bot_fid:
                result = await self.api_client.get_user_by_fid(int(self.bot_fid))
                if result:
                    return {"success": True, "message": "Connection test successful"}
                else:
                    return {"success": False, "error": "Invalid response from API"}
            else:
                # Basic connectivity test without specific user
                return {"success": True, "message": "API key configured (no bot_fid to test)"}
        except Exception as e:
            error_msg = f"Farcaster connection test failed: {e}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}

    async def set_credentials(self, credentials: Dict[str, str]) -> None:
        """Set Farcaster credentials."""
        required_keys = ["api_key"]
        missing_keys = [key for key in required_keys if key not in credentials]
        if missing_keys:
            error_msg = f"Missing required credentials: {missing_keys}"
            self._set_status(ObserverStatus.ERROR, error_msg)
            self._enabled = False
            return
            
        try:
            self.api_key = credentials["api_key"]
            self.signer_uuid = credentials.get("signer_uuid")
            self.bot_fid = credentials.get("bot_fid")
            
            # Recreate API client with new credentials
            if self.api_key:
                self._initialize_api_client()
                
            # Update enabled status
            self._enabled = bool(self.api_key)
            
            if self._enabled:
                self._clear_error()
                logger.debug(f"Farcaster credentials updated with API key and bot FID: {self.bot_fid}")
            
        except Exception as e:
            error_msg = f"Failed to set Farcaster credentials: {e}"
            self._set_status(ObserverStatus.ERROR, error_msg)
            self._enabled = False
            raise

    # Schedule management methods

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
        logger.debug(f"🎯 FarcasterObserver.schedule_post action_id={action_id}")
        if self.scheduler.schedule_post(content, channel, action_id, embeds):
            logger.debug("Farcaster post scheduled successfully via observer.")
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
        logger.debug(f"🎯 FarcasterObserver.schedule_reply action_id={action_id}")
        if self.scheduler.schedule_reply(content, reply_to_hash, action_id):
            logger.debug("Farcaster reply scheduled successfully via observer.")
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
        include_for_you_feed: bool = False,
        include_world_state_data: bool = False,
        world_state_trending_limit: int = 5,
        for_you_limit: int = 10,
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
            if include_for_you_feed:
                for_you_messages = await self._observe_for_you_feed(limit=for_you_limit)
                new_messages.extend(for_you_messages)
            if include_notifications and self.bot_fid:
                notification_messages = await self._observe_notifications()
                new_messages.extend(notification_messages)
                mention_messages = await self._observe_mentions()
                new_messages.extend(mention_messages)
                
            # Enhanced world state data collection
            if include_world_state_data:
                logger.debug("Collecting enhanced world state data...")
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
                        logger.debug(f"Storing {len(messages)} {data_type} messages in world state")
                        self._store_world_state_data(data_type, messages)
                        
            # Check for new casts from monitored token holders
            if self.ecosystem_token_service:
                holder_feed_messages = await self.ecosystem_token_service.observe_monitored_holder_feeds()
                new_messages.extend(holder_feed_messages)
            
            # *** ENHANCEMENT: Include bot's own recent casts for self-awareness ***
            if self.bot_fid and (include_home_feed or include_for_you_feed):
                try:
                    bot_recent_casts = await self.get_recent_own_posts(limit=5)
                    if bot_recent_casts:
                        # Convert dict format to Message objects if needed
                        for cast_data in bot_recent_casts:
                            if isinstance(cast_data, dict):
                                # Create a Message object from the cast data
                                bot_message = Message(
                                    id=cast_data.get('hash', ''),
                                    channel_id="farcaster:bot_own_posts",
                                    channel_type="farcaster",
                                    sender=cast_data.get('author', {}).get('username', self.bot_username or ''),
                                    content=cast_data.get('text', ''),
                                    timestamp=cast_data.get('timestamp', time.time()),
                                    sender_fid=str(self.bot_fid),
                                    sender_username=self.bot_username,
                                    cast_hash=cast_data.get('hash'),
                                )
                                new_messages.append(bot_message)
                        logger.debug(f"Added {len(bot_recent_casts)} bot's own recent casts to feed for self-awareness")
                except Exception as e:
                    logger.warning(f"Failed to fetch bot's own recent casts: {e}")
                        
            unique_messages_dict = {msg.id: msg for msg in new_messages}
            new_messages = list(unique_messages_dict.values())
            self.last_check_time = current_time
            
            # Save persistent state after successful observation
            self._save_persistent_state()
            
            # Sync rate limits after API calls
            self._sync_rate_limits_to_world_state()
            
            logger.debug(f"Observed {len(new_messages)} new Farcaster messages.")
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
        include_for_you_feed: bool = True,
        trending_limit: int = 10,
        for_you_limit: int = 10,
    ) -> Dict[str, List[Message]]:
        """
        Collect comprehensive world state data for AI context.

        Returns a dictionary with categorized message lists:
        - trending: Recent trending casts
        - home: Home timeline messages
        - notifications: Notifications and mentions
        - for_you: Personalized "For You" feed content
        """
        if not self.api_client:
            logger.warning("Cannot observe world state data: API client not initialized.")
            return {}

        world_state_data = {}

        try:
            if include_trending:
                trending_messages = await self._observe_trending_casts(limit=trending_limit)
                world_state_data["trending"] = trending_messages
                logger.debug(f"Collected {len(trending_messages)} trending casts for world state")

            if include_home_feed:
                home_messages = await self._observe_home_feed()
                world_state_data["home"] = home_messages
                logger.debug(f"Collected {len(home_messages)} home feed messages for world state")
                
            if include_for_you_feed and self.bot_fid:
                for_you_messages = await self._observe_for_you_feed(limit=for_you_limit)
                world_state_data["for_you"] = for_you_messages
                logger.debug(f"Collected {len(for_you_messages)} 'For You' feed messages for world state")

            if include_notifications and self.bot_fid:
                notification_messages = await self._observe_notifications()
                mention_messages = await self._observe_mentions()
                world_state_data["notifications"] = notification_messages + mention_messages
                logger.debug(f"Collected {len(notification_messages + mention_messages)} notifications for world state")

        except Exception as e:
            logger.error(f"Error collecting world state data: {e}", exc_info=True)

        return world_state_data

    def _sync_rate_limits_to_world_state(self):
        """Sync rate limit information from API client to WorldStateManager."""
        if not self.world_state_manager or not self.api_client:
            return

        client_rate_info = getattr(self.api_client, 'rate_limit_info', None)
        if client_rate_info and client_rate_info.get("last_updated_client", 0) > 0:
            # Check if client info is newer than WSM info
            wsm_farcaster_limits = self.world_state_manager.state.rate_limits.get('farcaster_api', {})
            wsm_last_updated = wsm_farcaster_limits.get('last_updated', 0)

            if client_rate_info["last_updated_client"] > wsm_last_updated:
                # Map Neynar rate limit data to WorldState format
                new_wsm_limits = {
                    "limit": client_rate_info.get("limit"),
                    "remaining": client_rate_info.get("remaining"),
                    "reset_time": client_rate_info.get("reset"), # Assuming 'reset' is a Unix timestamp
                    "last_updated": client_rate_info["last_updated_client"]
                }
                
                # Add retry_after if available (typically from 429 responses)
                if "retry_after" in client_rate_info:
                    new_wsm_limits["retry_after"] = client_rate_info["retry_after"]
                
                # Remove None values before updating WSM
                new_wsm_limits = {k: v for k, v in new_wsm_limits.items() if v is not None}

                self.world_state_manager.state.rate_limits['farcaster_api'] = new_wsm_limits
                logger.debug(f"FarcasterObserver: Synced Farcaster API rate limits to WorldState: {new_wsm_limits}")
                
                # Log warning if rate limits are low
                remaining = new_wsm_limits.get("remaining", 0)
                if remaining is not None and remaining < 10:
                    logger.warning(f"Farcaster API rate limit critical: {remaining} requests remaining!")
                elif remaining is not None and remaining < 50:
                    logger.debug(f"Farcaster API rate limit status: {remaining} requests remaining")

    # --- Direct Action Methods ---

    async def post_cast(
        self,
        content: str,
        channel: Optional[str] = None,
        embed_urls: Optional[List[str]] = None,
        reply_to: Optional[str] = None,
        action_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Post a cast directly (not scheduled) with rate limiting checks."""
        if not self.api_client:
            return {"success": False, "error": "API client not initialized"}
        
        # Check network availability first
        if not self.api_client.is_network_available():
            error_msg = "Farcaster API is currently unavailable due to network issues"
            logger.warning(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "network_unavailable": True
            }
        
        logger.debug(f"🎯 FarcasterObserver.post_cast action_id={action_id}, embeds: {embed_urls}")
        
        try:
            # Check timing constraints (only for new posts, not replies)
            if not reply_to:
                timing_check = await self.check_post_timing()
                if not timing_check["can_post"]:
                    # Use more precise timing message if available
                    time_msg = timing_check.get("time_remaining_formatted", 
                                              f"{timing_check['minutes_remaining']} minute(s)")
                    error_msg = f"Rate limited: must wait {time_msg}"
                    logger.warning(error_msg)
                    return {
                        "success": False,
                        "error": error_msg,
                        "rate_limited": True,
                        "time_remaining": timing_check["time_remaining_seconds"],
                        "next_post_available": time.time() + timing_check["time_remaining_seconds"]
                    }
                
                # Check for similar recent posts
                if await self.check_similar_recent_post(content):
                    error_msg = "Similar post was made recently - avoiding duplicate"
                    logger.warning(error_msg)
                    return {
                        "success": False,
                        "error": error_msg,
                        "duplicate_detected": True
                    }
            
            # Correctly form embeds list for Neynar API
            embeds_payload: Optional[List[Dict[str,str]]] = None
            if embed_urls:
                embeds_payload = [{"url": url_str} for url_str in embed_urls]

            result = await self.api_client.publish_cast(
                text=content, # Changed from content to text for Neynar API
                signer_uuid=self.signer_uuid,
                channel_id=channel, # Changed from channel to channel_id
                parent=reply_to,
                embeds=embeds_payload # Pass the correctly formatted embeds
            )
            
            # Sync rate limits after API call
            self._sync_rate_limits_to_world_state()
            
            return result
            
        except NeynarNetworkError as e:
            error_msg = f"Network error posting cast: {e}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "network_error": True
            }
        except NeynarRateLimitError as e:
            error_msg = f"Rate limit exceeded: {e}"
            logger.warning(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "rate_limited": True
            }
        except NeynarAPIError as e:
            error_msg = f"API error posting cast: {e}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "api_error": True
            }
        except Exception as e:
            error_msg = f"Unexpected error posting cast: {e}"
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "error": error_msg,
                "unexpected_error": True
            }

    async def reply_to_cast(
        self,
        content: str,
        reply_to_hash: str,
        action_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reply to a cast directly (not scheduled)."""
        logger.debug(f"🎯 FarcasterObserver.reply_to_cast action_id={action_id}")
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
        quoted_cast_author_fid: int,
        channel: Optional[str] = None,
        embed_urls: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Quote a cast."""
        if not self.api_client:
            return {"success": False, "error": "API client not initialized"}
        return await self.api_client.quote_cast(
            content, quoted_cast_hash, quoted_cast_author_fid, channel, embed_urls
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
            
            # Check if API client returned an error
            if data.get("error"):
                logger.error(f"API client returned error for search query '{query}': {data.get('error')}")
                return {"success": False, "casts": [], "error": data.get("error")}
            
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
                channel_id=channel_id, timeframe_hours=timeframe_hours, limit=limit
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
        """Get detailed information about a specific cast."""
        if not self.api_client:
            return {"success": False, "error": "API client not initialized"}
        return await self.api_client.get_cast_details(cast_hash)

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

        # Update user profile in world state if available
        if self.world_state_manager and context.get("fid"):
            try:
                self._update_farcaster_user_profile(message, context)
            except Exception as e:
                logger.error(f"Error updating user profile: {e}", exc_info=True)

        return context

    def _update_farcaster_user_profile(self, message: Message, context: Dict[str, Any]) -> None:
        """Update Farcaster user profile data in world state."""
        fid = str(context.get("fid"))
        if not fid:
            return
            
        try:
            # Get or create user details
            user_details = self.world_state_manager.get_or_create_farcaster_user(fid)
            
            # Update basic information if we have new data
            if context.get("username") and context["username"] != "unknown":
                user_details.username = context["username"]
            if context.get("display_name") and context["display_name"] != "Unknown":
                user_details.display_name = context["display_name"]
            if context.get("follower_count") is not None:
                user_details.follower_count = context["follower_count"]
            if context.get("following_count") is not None:
                user_details.following_count = context["following_count"]
            if context.get("power_badge") is not None:
                user_details.power_badge = context["power_badge"]
            if context.get("verified_addresses"):
                user_details.verified_addresses = context["verified_addresses"]
                
            # Update bio from message metadata if available
            metadata = getattr(message, "metadata", {})
            if isinstance(metadata, dict) and metadata.get("bio"):
                user_details.bio = metadata["bio"]
            if isinstance(metadata, dict) and metadata.get("pfp_url"):
                user_details.pfp_url = metadata["pfp_url"]
            
            logger.debug(f"Updated profile for Farcaster user {fid} ({user_details.username})")
            
        except Exception as e:
            logger.error(f"Error updating Farcaster user profile for FID {fid}: {e}", exc_info=True)

    def _store_world_state_data(self, data_type: str, messages: List[Message]) -> None:
        """Store categorized world state data in the world state manager."""
        if not self.world_state_manager:
            return
            
        try:
            # Map data types to persistent channel IDs
            channel_mapping = {
                'trending': 'farcaster:trending',
                'home': 'farcaster:home', 
                'notifications': 'farcaster:notifications',
                'for_you': 'farcaster:for_you'
            }
            
            # Use mapped channel ID or fallback to prefixed version
            channel_id = channel_mapping.get(data_type, f"farcaster:world_state_{data_type}")
            
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
                        
            logger.debug(f"Stored {len(messages)} {data_type} messages in world state channel {channel_id}")
            
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
        logger.debug(f"Starting world state collection loop (interval: {self.world_state_collection_interval}s)")
        
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
                    logger.debug(f"World state collection: stored {total_messages} messages across {len(world_state_data)} categories")
                    
                    # Generate specific triggers for processing hub if connected
                    if self.processing_hub:
                        from ...core.orchestration.processing_hub import Trigger
                        
                        # Check for high-priority data types
                        for data_type, messages in world_state_data.items():
                            if not messages:
                                continue
                                
                            if data_type == "notifications":
                                # High priority for notifications and mentions
                                trigger = Trigger(
                                    type='farcaster_notification',
                                    priority=8,
                                    data={'data_type': data_type, 'message_count': len(messages)}
                                )
                                self.processing_hub.add_trigger(trigger)
                            elif data_type in ["trending", "for_you"]:
                                # Medium priority for trending/discovery content
                                trigger = Trigger(
                                    type='farcaster_discovery',
                                    priority=6,
                                    data={'data_type': data_type, 'message_count': len(messages)}
                                )
                                self.processing_hub.add_trigger(trigger)
                            elif data_type == "home_feed":
                                # Lower priority for general home feed
                                trigger = Trigger(
                                    type='farcaster_feed',
                                    priority=4,
                                    data={'data_type': data_type, 'message_count': len(messages)}
                                )
                                self.processing_hub.add_trigger(trigger)
                    
                    # Fallback: Trigger legacy state change notification for backward compatibility
                    if hasattr(self, 'on_state_change') and self.on_state_change:
                        try:
                            self.on_state_change()
                            logger.debug("Triggered legacy state change notification after world state collection")
                        except Exception as e:
                            logger.error(f"Error triggering legacy state change: {e}", exc_info=True)
                else:
                    logger.debug("World state collection: no new messages found")
                    
            except asyncio.CancelledError:
                logger.debug("World state collection loop cancelled")
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
            logger.debug("Manual world state collection triggered")
            
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
            
            logger.debug(f"Manual world state collection complete: {total_messages} messages collected")
            return results
            
        except Exception as e:
            logger.error(f"Error in manual world state collection: {e}", exc_info=True)
            return {"error": str(e), "success": False}

    async def _observe_for_you_feed(self, limit: int = 10) -> List[Message]:
        """Observe personalized 'For You' feed for proactive content discovery."""
        if not self.api_client or not self.bot_fid:
            return []
        logger.debug("Observing 'For You' feed for proactive discovery.")
        try:
            data = await self.api_client.get_for_you_feed(fid=self.bot_fid, limit=limit)
            return await convert_api_casts_to_messages(
                data.get("casts", []),
                channel_id_prefix="farcaster:for_you",
                cast_type_metadata="for_you_feed",
                bot_fid=self.bot_fid,
                last_check_time_for_filtering=self.last_check_time,
                last_seen_hashes=self.last_seen_hashes,
            )
        except Exception as e:
            logger.error(f"Error observing 'For You' feed: {e}", exc_info=True)
            return []

    async def get_recent_own_posts(self, limit: int = 10) -> List[Dict]:
        """Get recent posts by the bot itself to avoid duplicate content"""
        if not self.api_client or not self.bot_fid:
            logger.warning("Cannot get recent posts: API client or bot_fid not configured")
            return []
            
        try:
            # Check if network is available
            if not self.api_client.is_network_available():
                logger.warning("Farcaster API not available, skipping recent posts check")
                return []
            
            # Get recent casts by our own FID
            data = await self.api_client.get_casts_by_fid(fid=self.bot_fid, limit=limit)
            casts = data.get("casts", [])
            
            # Convert to simplified format for rate limiting checks
            recent_posts = []
            for cast in casts:
                recent_posts.append({
                    "hash": cast.get("hash"),
                    "text": cast.get("text", ""),
                    "timestamp": cast.get("timestamp"),
                    "author": cast.get("author", {})
                })
            
            logger.debug(f"Retrieved {len(recent_posts)} recent own posts")
            return recent_posts
            
        except NeynarNetworkError as e:
            logger.warning(f"Network error fetching own recent posts: {e}")
            return []
        except NeynarAPIError as e:
            logger.error(f"API error fetching own recent posts: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching own recent posts: {e}")
            return []

    async def check_post_timing(self) -> Dict[str, Any]:
        """Check if enough time has passed since last post"""
        try:
            from ...config import settings
            min_interval_seconds = settings.farcaster.min_post_interval_minutes * 60
            
            recent_posts = await self.get_recent_own_posts(limit=1)
            if not recent_posts:
                # If we can't get recent posts due to network issues, allow posting
                # but log the situation
                if self.api_client and not self.api_client.is_network_available():
                    logger.warning("Network unavailable, allowing post but timing cannot be verified")
                return {"can_post": True}
            
            last_post = recent_posts[0]
            post_time_str = last_post.get("timestamp", "")
            
            if isinstance(post_time_str, str):
                try:
                    from datetime import datetime
                    post_datetime = datetime.fromisoformat(post_time_str.replace('Z', '+00:00'))
                    post_timestamp = int(post_datetime.timestamp())
                except:
                    return {"can_post": True}
            else:
                post_timestamp = int(post_time_str) if post_time_str else 0
            
            current_time = int(time.time())
            time_since_last = current_time - post_timestamp
            
            if time_since_last < min_interval_seconds:
                time_remaining = min_interval_seconds - time_since_last
                minutes_remaining = time_remaining / 60
                
                # Format more precise timing messages
                if time_remaining >= 60:
                    time_msg = f"{round(minutes_remaining, 1)} minute(s)"
                else:
                    time_msg = f"{int(time_remaining)} second(s)"
                
                return {
                    "can_post": False,
                    "time_remaining_seconds": time_remaining,
                    "minutes_remaining": round(minutes_remaining, 1),
                    "time_remaining_formatted": time_msg,
                    "last_post_time": post_time_str
                }
            
            return {"can_post": True}
            
        except Exception as e:
            logger.error(f"Error checking post timing: {e}")
            return {"can_post": True}  # Default to allowing post on error

    async def check_similar_recent_post(self, content: str) -> bool:
        """Check if we recently posted similar content"""
        try:
            from ...config import settings
            hours_back = settings.farcaster.duplicate_check_hours
            
            recent_posts = await self.get_recent_own_posts(limit=settings.farcaster.recent_posts_limit)
            
            # Check posts from the configured time period
            current_time = int(time.time())
            cutoff_time = current_time - (hours_back * 3600)
            
            for post in recent_posts:
                post_time_str = post.get("timestamp", "")
                if isinstance(post_time_str, str):
                    try:
                        from datetime import datetime
                        post_datetime = datetime.fromisoformat(post_time_str.replace('Z', '+00:00'))
                        post_timestamp = int(post_datetime.timestamp())
                    except:
                        continue
                else:
                    post_timestamp = int(post_time_str) if post_time_str else 0
                
                if post_timestamp > cutoff_time:
                    post_text = post.get("text", "")
                    if self._content_similarity(content, post_text) > 0.7:
                        logger.warning(f"Similar post found within {hours_back} hours: {post_text[:50]}...")
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking recent similar posts: {e}")
            return False

    def _content_similarity(self, content1: str, content2: str) -> float:
        """Calculate simple content similarity based on common words"""
        words1 = set(content1.lower().split())
        words2 = set(content2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
