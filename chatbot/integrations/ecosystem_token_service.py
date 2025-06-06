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
import aiohttp
import json
from typing import List, Dict, Optional, Any

from chatbot.config import settings
from chatbot.integrations.farcaster.neynar_api_client import NeynarAPIClient
from chatbot.core.world_state.manager import WorldStateManager
from chatbot.core.world_state.structures import MonitoredTokenHolder, Message, TokenMetadata, TokenHolderData

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
        self.token_network = settings.ECOSYSTEM_TOKEN_NETWORK
        self.num_top_holders = settings.NUM_TOP_HOLDERS_TO_TRACK
        self.cast_history_length = settings.HOLDER_CAST_HISTORY_LENGTH
        self.update_interval = settings.TOP_HOLDERS_UPDATE_INTERVAL_MINUTES * 60
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Token metadata update settings
        self.token_metadata_update_interval = 5 * 60  # 5 minutes for metadata updates
        self.last_metadata_update = 0

    async def _fetch_and_rank_holders(self) -> List[Dict]:
        """
        Fetches relevant Farcaster token holders using Neynar's fungible owner endpoint.
        This method uses the confirmed API endpoint for getting Farcaster users who own specific tokens.
        """
        if not self.token_contract or not self.token_network:
            logger.warning("Token contract address or network not configured")
            return []

        try:
            logger.info(f"Fetching relevant Farcaster token owners for {self.token_contract} on {self.token_network}")
            
            # Use the proper Neynar API endpoint for relevant fungible owners
            owners_response = await self.neynar_api_client.get_relevant_fungible_owners(
                contract_address=self.token_contract,
                network=self.token_network,
                viewer_fid=None  # Get global top holders rather than personalized
            )
            
            if owners_response and "top_relevant_fungible_owners_hydrated" in owners_response:
                # Extract user profiles from the hydrated owners
                owners_list = owners_response["top_relevant_fungible_owners_hydrated"]
                
                # Convert to the format expected by the rest of the service
                holders_data = []
                for owner_profile in owners_list:
                    holders_data.append({
                        "fid": owner_profile.get("fid"),
                        "username": owner_profile.get("username"),
                        "display_name": owner_profile.get("display_name"),
                        "pfp_url": owner_profile.get("pfp_url"),
                        "follower_count": owner_profile.get("follower_count"),
                        "following_count": owner_profile.get("following_count"),
                        "power_badge": owner_profile.get("power_badge", False),
                        "verified_addresses": owner_profile.get("verified_addresses", {}),
                        "custody_address": owner_profile.get("custody_address"),
                        # Note: Individual token balances are not provided by this endpoint
                        # The API returns relevant owners but not their specific holding amounts
                    })
                
                logger.info(f"Successfully fetched {len(holders_data)} relevant Farcaster token owners for {self.token_contract}")
                return holders_data[:self.num_top_holders]  # Limit to configured number
                
            elif owners_response and "all_relevant_fungible_owners_dehydrated" in owners_response:
                # Fallback to dehydrated owners if hydrated ones aren't available
                dehydrated_owners = owners_response["all_relevant_fungible_owners_dehydrated"]
                logger.info(f"Using dehydrated owner data, found {len(dehydrated_owners)} owners")
                
                holders_data = []
                for owner_profile in dehydrated_owners:
                    holders_data.append({
                        "fid": owner_profile.get("fid"),
                        "username": owner_profile.get("username"),
                        "display_name": owner_profile.get("display_name"),
                        # Dehydrated profiles have limited data
                    })
                
                return holders_data[:self.num_top_holders]
                
            else:
                # Check if this is a test contract for simulation
                if self.token_contract == "0xTESTCONTRACT":
                    logger.info("Using simulated holder data for 0xTESTCONTRACT")
                    simulated_fids = [i for i in range(1, 25)]  # Simulate some FIDs
                    return [
                        {"fid": fid, "username": f"holder{fid}", "display_name": f"Holder #{fid}"} 
                        for fid in simulated_fids[:self.num_top_holders]
                    ]
                else:
                    logger.warning(f"No relevant Farcaster owners found for token {self.token_contract} on {self.token_network}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error fetching relevant token owners for {self.token_contract} on {self.token_network}: {e}", exc_info=True)
            return []

    async def update_top_token_holders_in_world_state(self):
        """Update the world state with current top token holders and their activity."""
        logger.info("Updating top token holders...")
        if not self.token_contract or not self.token_network:
            logger.warning("ECOSYSTEM_TOKEN_CONTRACT_ADDRESS or ECOSYSTEM_TOKEN_NETWORK not set. Skipping holder update.")
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
                messages = await convert_api_casts_to_messages(
                    api_casts=casts_data.get("casts", []),
                    channel_id_prefix="farcaster:holders",  # Aggregated holders feed
                    cast_type_metadata="holder_cast",
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
        """Main loop for periodic token holder updates and metadata refresh."""
        self._running = True
        logger.info("Starting periodic token holder update loop with metadata tracking.")
        while self._running:
            try:
                # Update token metadata (has its own frequency control)
                await self.update_token_metadata()
                
                # Update top holders and their activity
                await self.update_top_token_holders_in_world_state()
                
                # Update social influence scores for all holders
                await self._update_holder_influence_scores()
                
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
                    potential_new_messages = await convert_api_casts_to_messages(
                        api_casts=casts_data["casts"],
                        channel_id_prefix="farcaster:holders", # Use aggregated feed
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

    async def _fetch_token_metadata_from_dexscreener(self, contract_address: str) -> Optional[TokenMetadata]:
        """
        Fetch token metadata from DexScreener API.
        
        Args:
            contract_address: The token contract address
            
        Returns:
            TokenMetadata object with comprehensive token information
        """
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{contract_address}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.warning(f"DexScreener API returned status {response.status} for token {contract_address}")
                        return None
                    
                    data = await response.json()
                    
                    if not data.get("pairs"):
                        logger.info(f"No trading pairs found for token {contract_address}")
                        return None
                    
                    # Get the most liquid pair (highest liquidity USD)
                    pairs = data["pairs"]
                    main_pair = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0)))
                    
                    token_info = None
                    # Find our token in the pair (baseToken or quoteToken)
                    if main_pair["baseToken"]["address"].lower() == contract_address.lower():
                        token_info = main_pair["baseToken"]
                        price_usd = float(main_pair.get("priceUsd", 0))
                    elif main_pair["quoteToken"]["address"].lower() == contract_address.lower():
                        token_info = main_pair["quoteToken"]
                        price_usd = 1 / float(main_pair.get("priceUsd", 1)) if main_pair.get("priceUsd") else 0
                    else:
                        logger.warning(f"Token {contract_address} not found in main trading pair")
                        return None
                    
                    # Calculate market cap if we have price and supply
                    market_cap = None
                    if price_usd and token_info.get("totalSupply"):
                        try:
                            total_supply = float(token_info["totalSupply"])
                            market_cap = price_usd * total_supply
                        except (ValueError, TypeError):
                            pass
                    
                    # Extract DEX information
                    dex_info = {
                        "main_pair_address": main_pair.get("pairAddress"),
                        "dex_id": main_pair.get("dexId"),
                        "liquidity_usd": float(main_pair.get("liquidity", {}).get("usd", 0)),
                        "volume_24h": float(main_pair.get("volume", {}).get("h24", 0)),
                        "price_change_24h": float(main_pair.get("priceChange", {}).get("h24", 0)),
                        "transactions_24h": main_pair.get("txns", {}).get("h24", {}),
                        "fdv": float(main_pair.get("fdv", 0)),
                    }
                    
                    metadata = TokenMetadata(
                        contract_address=contract_address,
                        ticker=token_info.get("symbol"),
                        name=token_info.get("name"),
                        price_usd=price_usd,
                        price_change_24h=dex_info["price_change_24h"],
                        volume_24h=dex_info["volume_24h"],
                        market_cap=market_cap,
                        total_supply=float(token_info.get("totalSupply", 0)) if token_info.get("totalSupply") else None,
                        last_updated=time.time(),
                        dex_info=dex_info
                    )
                    
                    logger.info(f"Successfully fetched metadata for token {contract_address}: {metadata.ticker} (${metadata.price_usd:.6f})")
                    return metadata
                    
        except Exception as e:
            logger.error(f"Error fetching token metadata from DexScreener for {contract_address}: {e}", exc_info=True)
            return None

    async def _fetch_token_social_metrics(self, contract_address: str, ticker: str) -> Dict[str, Any]:
        """
        Fetch social media metrics for the token.
        
        Args:
            contract_address: The token contract address
            ticker: Token ticker symbol
            
        Returns:
            Dictionary with social media metrics
        """
        try:
            # This is a placeholder for social metrics collection
            # In a real implementation, you would integrate with:
            # - Twitter API for mentions
            # - Telegram API for group activity
            # - Discord API for server activity
            # - Reddit API for subreddit activity
            # - Farcaster for ecosystem activity
            
            social_metrics = {
                "farcaster_mentions_24h": 0,
                "twitter_mentions_24h": 0,
                "telegram_activity_score": 0,
                "discord_activity_score": 0,
                "reddit_mentions_24h": 0,
                "social_sentiment_score": 0.0,  # -1 to 1
                "trending_score": 0.0,
                "last_updated": time.time()
            }
            
            # TODO: Implement actual social media tracking
            logger.info(f"Social metrics placeholder for {ticker} ({contract_address})")
            return social_metrics
            
        except Exception as e:
            logger.error(f"Error fetching social metrics for {contract_address}: {e}")
            return {}

    async def update_token_metadata(self):
        """
        Update comprehensive token metadata including market data and social metrics.
        """
        if not self.token_contract:
            logger.warning("No token contract configured for metadata updates")
            return
        
        current_time = time.time()
        if current_time - self.last_metadata_update < self.token_metadata_update_interval:
            return  # Skip if updated recently
        
        logger.info(f"Updating token metadata for contract {self.token_contract}")
        
        try:
            # Fetch market data
            token_metadata = await self._fetch_token_metadata_from_dexscreener(self.token_contract)
            
            if token_metadata:
                # Fetch social metrics
                social_metrics = await self._fetch_token_social_metrics(
                    self.token_contract, 
                    token_metadata.ticker or "UNKNOWN"
                )
                token_metadata.social_metrics = social_metrics
                
                # Calculate additional metrics
                await self._enhance_token_metadata(token_metadata)
                
                # Update world state
                self.world_state_manager.state.token_metadata = token_metadata
                self.last_metadata_update = current_time
                
                logger.info(f"Updated token metadata: {token_metadata.ticker} - "
                           f"Price: ${token_metadata.price_usd:.6f}, "
                           f"Market Cap: ${token_metadata.market_cap:,.2f}" if token_metadata.market_cap else "Market Cap: N/A")
            else:
                logger.warning(f"Failed to fetch token metadata for {self.token_contract}")
                
        except Exception as e:
            logger.error(f"Error updating token metadata: {e}", exc_info=True)

    async def _enhance_token_metadata(self, metadata: TokenMetadata):
        """
        Enhance token metadata with calculated metrics and holder information.
        
        Args:
            metadata: TokenMetadata object to enhance
        """
        try:
            # Calculate holder count from monitored holders
            if self.world_state_manager.state.monitored_token_holders:
                metadata.holder_count = len(self.world_state_manager.state.monitored_token_holders)
                
                # Calculate top holder percentage if we have holder data
                top_holders = list(self.world_state_manager.state.monitored_token_holders.values())
                if top_holders and hasattr(top_holders[0], 'token_holder_data') and top_holders[0].token_holder_data:
                    max_percentage = max(
                        holder.token_holder_data.percentage_of_supply 
                        for holder in top_holders 
                        if holder.token_holder_data and holder.token_holder_data.percentage_of_supply
                    )
                    metadata.top_holder_percentage = max_percentage
            
            # Add description based on available data
            if not metadata.description and metadata.ticker:
                metadata.description = f"Ecosystem token {metadata.ticker} tracked for holder activity analysis"
                
        except Exception as e:
            logger.error(f"Error enhancing token metadata: {e}")

    async def _calculate_social_influence_score(self, holder: MonitoredTokenHolder) -> float:
        """
        Calculate a social influence score for a token holder based on their activity and holdings.
        
        Args:
            holder: MonitoredTokenHolder object
            
        Returns:
            Influence score between 0.0 and 1.0
        """
        try:
            score = 0.0
            
            # Base score from token holdings (30% weight)
            if holder.token_holder_data and holder.token_holder_data.percentage_of_supply:
                holding_score = min(holder.token_holder_data.percentage_of_supply * 10, 1.0)  # Cap at 1.0
                score += holding_score * 0.3
            
            # Social activity score (40% weight)
            if holder.recent_casts:
                activity_score = min(len(holder.recent_casts) / 10, 1.0)  # Normalize to max 10 casts
                score += activity_score * 0.4
            
            # Recency score (30% weight)
            if holder.last_activity_timestamp:
                hours_since_activity = (time.time() - holder.last_activity_timestamp) / 3600
                recency_score = max(0, 1 - (hours_since_activity / 168))  # Decay over 1 week
                score += recency_score * 0.3
            
            return min(score, 1.0)  # Cap at 1.0
            
        except Exception as e:
            logger.error(f"Error calculating social influence score for holder {holder.fid}: {e}")
            return 0.0

    async def _update_holder_influence_scores(self):
        """
        Update social influence scores for all monitored token holders.
        """
        try:
            if not self.world_state_manager.state.monitored_token_holders:
                return
            
            for fid, holder in self.world_state_manager.state.monitored_token_holders.items():
                try:
                    # Calculate and update influence score
                    influence_score = await self._calculate_social_influence_score(holder)
                    holder.social_influence_score = influence_score
                    
                    # Update last activity timestamp if we have recent casts
                    if holder.recent_casts:
                        latest_cast_time = max(cast.timestamp for cast in holder.recent_casts)
                        if not holder.last_activity_timestamp or latest_cast_time > holder.last_activity_timestamp:
                            holder.last_activity_timestamp = latest_cast_time
                            
                except Exception as e:
                    logger.error(f"Error updating influence score for holder {fid}: {e}")
                    
            logger.debug(f"Updated influence scores for {len(self.world_state_manager.state.monitored_token_holders)} holders")
            
        except Exception as e:
            logger.error(f"Error updating holder influence scores: {e}", exc_info=True)
