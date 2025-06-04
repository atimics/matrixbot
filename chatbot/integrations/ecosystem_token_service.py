#!/usr/bin/env python3
"""
Ecosystem Token Service

This service manages the tracking of top token holders and their Farcaster activity.
It periodically fetches and updates the list of top holders for a specified token,
monitors their recent casts, and integrates this information into the world state.
"""

import asyncio
import logging
import time
from typing import List, Dict, Optional

from chatbot.config import settings
from chatbot.integrations.farcaster.neynar_api_client import NeynarAPIClient
from chatbot.core.world_state.manager import WorldStateManager
from chatbot.core.world_state.structures import MonitoredTokenHolder, Message

logger = logging.getLogger(__name__)


class EcosystemTokenService:
    """
    Service for tracking ecosystem token holders and their Farcaster activity.
    
    This service:
    1. Periodically fetches the top holders of a specified token
    2. Monitors their recent Farcaster casts
    3. Updates the world state with this information
    4. Provides this data to the AI for decision-making
    """
    
    def __init__(self, neynar_api_client: NeynarAPIClient, world_state_manager: WorldStateManager):
        self.neynar_api_client = neynar_api_client
        self.world_state_manager = world_state_manager
        self.token_contract = settings.ECOSYSTEM_TOKEN_CONTRACT_ADDRESS
        self.num_top_holders = settings.NUM_TOP_HOLDERS_TO_TRACK
        self.cast_history_length = settings.HOLDER_CAST_HISTORY_LENGTH
        self.update_interval = settings.TOP_HOLDERS_UPDATE_INTERVAL_MINUTES * 60
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def _fetch_and_rank_holders(self) -> List[Dict]:
        """
        Fetches token holders and ranks them.
        This method attempts to fetch real token holders but falls back to simulation for testing.
        """
        if not self.token_contract:
            return []

        try:
            # Attempt to fetch real holder data
            holders_response = await self.neynar_api_client.get_token_holders(
                self.token_contract, limit=self.num_top_holders * 2  # Fetch extra in case some don't have FIDs
            )
            
            if holders_response.get("holders"):
                logger.info(f"Fetched {len(holders_response['holders'])} holders for token {self.token_contract}")
                return holders_response["holders"][:self.num_top_holders]
            else:
                # Check if this is a test contract or if the API returned guidance
                if self.token_contract == "0xTESTCONTRACT":  # Example for simulation
                    logger.info("Using simulated holder data for 0xTESTCONTRACT")
                    simulated_fids = [i for i in range(1, 25)]  # Simulate some FIDs
                    return [
                        {"fid": fid, "username": f"holder{fid}", "display_name": f"Holder #{fid}"} 
                        for fid in simulated_fids[:self.num_top_holders]
                    ]
                else:
                    logger.warning(f"No holder data returned for token {self.token_contract}. "
                                  f"Response: {holders_response.get('note', 'Unknown error')}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error fetching token holders for {self.token_contract}: {e}", exc_info=True)
            return []

    async def update_top_token_holders_in_world_state(self):
        """Update the world state with current top token holders and their activity."""
        logger.info("Updating top token holders...")
        if not self.token_contract:
            logger.warning("ECOSYSTEM_TOKEN_CONTRACT_ADDRESS not set. Skipping holder update.")
            self.world_state_manager.state.monitored_token_holders.clear()  # Clear if contract removed
            return

        self.world_state_manager.state.ecosystem_token_contract = self.token_contract
        top_holder_data = await self._fetch_and_rank_holders()  # This needs to return a list of dicts with at least 'fid'

        if not top_holder_data:
            logger.info("No top holder data fetched.")
            # Consider whether to clear existing monitored_token_holders or keep them
            # For now, let's keep them but log that they might be stale if fetch fails
            if not self.world_state_manager.state.monitored_token_holders:
                logger.info("No existing holders to maintain, monitored list is empty.")
            else:
                logger.warning("Failed to fetch new holder data, existing monitored holders might be stale.")
            return

        # Fetch details for these FIDs in bulk
        fids_to_fetch_details = [int(h['fid']) for h in top_holder_data if 'fid' in h]
        user_details_response = await self.neynar_api_client.get_user_details_for_fids(fids_to_fetch_details)
        users_map = {str(u['fid']): u for u in user_details_response.get('users', [])}

        current_monitored_fids = set(self.world_state_manager.state.monitored_token_holders.keys())
        new_holder_fids = set()

        for holder_info in top_holder_data:
            fid_str = str(holder_info['fid'])
            new_holder_fids.add(fid_str)
            user_detail = users_map.get(fid_str, {})

            if fid_str not in self.world_state_manager.state.monitored_token_holders:
                self.world_state_manager.state.monitored_token_holders[fid_str] = MonitoredTokenHolder(
                    fid=fid_str,
                    username=user_detail.get('username', holder_info.get('username')),
                    display_name=user_detail.get('display_name', holder_info.get('display_name'))
                )
                logger.info(f"Added new top token holder to monitor: FID {fid_str}")
            else:  # Update existing details if necessary
                self.world_state_manager.state.monitored_token_holders[fid_str].username = user_detail.get('username', holder_info.get('username'))
                self.world_state_manager.state.monitored_token_holders[fid_str].display_name = user_detail.get('display_name', holder_info.get('display_name'))

            # Fetch initial recent casts for new holders or update existing
            await self._update_holder_recent_casts(fid_str)

        # Remove holders no longer in the top list
        fids_to_remove = current_monitored_fids - new_holder_fids
        for fid_to_remove in fids_to_remove:
            del self.world_state_manager.state.monitored_token_holders[fid_to_remove]
            logger.info(f"Removed token holder from monitoring (no longer in top list): FID {fid_to_remove}")

        logger.info(f"Finished updating top token holders. Monitoring {len(self.world_state_manager.state.monitored_token_holders)} holders.")

    async def _update_holder_recent_casts(self, fid: str):
        """Update recent casts for a specific holder."""
        holder_state = self.world_state_manager.state.monitored_token_holders.get(fid)
        if not holder_state:
            return

        try:
            logger.debug(f"Fetching recent casts for holder FID {fid}...")
            casts_data = await self.neynar_api_client.get_casts_by_fid(int(fid), limit=self.cast_history_length)
            new_casts = []
            if casts_data and "casts" in casts_data:
                # The converter needs to be available or its logic inlined here
                from chatbot.integrations.farcaster.farcaster_data_converter import convert_api_casts_to_messages
                messages = convert_api_casts_to_messages(
                    api_casts=casts_data["casts"],
                    channel_id_prefix=f"farcaster:holder_{fid}",  # Special channel prefix
                    cast_type_metadata="holder_cast"
                )
                messages.sort(key=lambda m: m.timestamp, reverse=True)  # Newest first
                holder_state.recent_casts = messages[:self.cast_history_length]
                if messages:
                    holder_state.last_cast_seen_timestamp = messages[0].timestamp
                    # Also add these messages to the general world state for AI awareness
                    for msg in messages:  # Add all new casts to general pool
                        self.world_state_manager.add_message(msg.channel_id, msg)  # Use the special channel_id
                        new_casts.append(msg)
            logger.info(f"Updated {len(holder_state.recent_casts)} recent casts for holder FID {fid}. {len(new_casts)} added to general pool.")
        except Exception as e:
            logger.error(f"Error updating casts for holder FID {fid}: {e}", exc_info=True)
            # Don't fail the entire update process for one holder

    async def periodic_holder_update_loop(self):
        """Main loop for periodic token holder updates."""
        self._running = True
        logger.info("Starting periodic token holder update loop.")
        while self._running:
            try:
                await self.update_top_token_holders_in_world_state()
                await asyncio.sleep(self.update_interval)
            except asyncio.CancelledError:
                logger.info("Token holder update loop cancelled.")
                break
            except Exception as e:
                logger.error(f"Error in token holder update loop: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait a bit longer on error

    async def start(self):
        """Start the ecosystem token service."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.periodic_holder_update_loop())
            logger.info("EcosystemTokenService started.")

    async def stop(self):
        """Stop the ecosystem token service."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("EcosystemTokenService stopped.")

    async def observe_monitored_holder_feeds(self) -> List[Message]:
        """
        Check for new casts from monitored holders.
        This method is called by the FarcasterObserver to get new holder activity.
        """
        if not self.world_state_manager:
            return []

        all_new_holder_casts: List[Message] = []
        monitored_holders = list(self.world_state_manager.state.monitored_token_holders.values())  # Get a copy

        for holder in monitored_holders:
            try:
                logger.debug(f"Checking for new casts from monitored holder FID {holder.fid}, last seen: {holder.last_cast_seen_timestamp}")
                # Fetch casts newer than last_cast_seen_timestamp
                # Neynar API might not have a direct "since_timestamp" filter for get_casts_by_fid.
                # If not, fetch recent casts (e.g., limit 10-20) and filter locally.
                casts_data = await self.neynar_api_client.get_casts_by_fid(int(holder.fid), limit=20)  # Fetch more to ensure we get new ones
                
                if casts_data and "casts" in casts_data:
                    from chatbot.integrations.farcaster.farcaster_data_converter import convert_api_casts_to_messages
                    potential_new_messages = convert_api_casts_to_messages(
                        api_casts=casts_data["casts"],
                        channel_id_prefix=f"farcaster:holder_{holder.fid}",
                        cast_type_metadata="holder_cast_update"
                    )

                    newly_seen_casts_for_this_holder = []
                    latest_timestamp_this_fetch = holder.last_cast_seen_timestamp or 0

                    for msg in sorted(potential_new_messages, key=lambda m: m.timestamp):  # Process oldest first
                        if (holder.last_cast_seen_timestamp is None or msg.timestamp > holder.last_cast_seen_timestamp) and \
                           msg.id not in {c.id for c in holder.recent_casts}:  # Avoid duplicates if already in recent_casts
                            newly_seen_casts_for_this_holder.append(msg)
                            self.world_state_manager.add_message(msg.channel_id, msg)  # Add to general pool
                            all_new_holder_casts.append(msg)
                            if msg.timestamp > latest_timestamp_this_fetch:
                                latest_timestamp_this_fetch = msg.timestamp
                    
                    if newly_seen_casts_for_this_holder:
                        # Update holder's recent_casts list (prepend new, keep fixed length)
                        holder.recent_casts = sorted(
                            list(set(newly_seen_casts_for_this_holder + holder.recent_casts)),  # Use set to remove exact duplicates by Message object if any
                            key=lambda m: m.timestamp,
                            reverse=True
                        )[:self.cast_history_length]
                        logger.info(f"Found {len(newly_seen_casts_for_this_holder)} new casts for holder FID {holder.fid}. Total recent: {len(holder.recent_casts)}")

                    if latest_timestamp_this_fetch > (holder.last_cast_seen_timestamp or 0):  # Update only if there are actually newer casts or first time
                        holder.last_cast_seen_timestamp = latest_timestamp_this_fetch
                        
            except Exception as e:
                logger.error(f"Error checking casts for holder FID {holder.fid}: {e}", exc_info=True)
                # Continue with other holders even if one fails

        if all_new_holder_casts:
            logger.info(f"Collected {len(all_new_holder_casts)} new casts from monitored token holders.")
        return all_new_holder_casts
