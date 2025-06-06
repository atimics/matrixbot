#!/usr/bin/env python3
"""
User Eligibility Service

This service performs cross-chain eligibility checks for NFT airdrops by monitoring
both Solana token balances and Base NFT holdings for Farcaster users.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any

import aiohttp
from solders.pubkey import Pubkey

from chatbot.config import settings
from chatbot.integrations.farcaster.neynar_api_client import NeynarAPIClient
from chatbot.integrations.base_nft_service import BaseNFTService
from chatbot.core.world_state.manager import WorldStateManager
from chatbot.core.world_state.structures import FarcasterUserDetails

logger = logging.getLogger(__name__)


class UserEligibilityService:
    """
    Service for checking cross-chain eligibility criteria for NFT airdrops.
    
    This service:
    1. Periodically checks Solana token balances for ecosystem token holders
    2. Checks Base NFT holdings from the collection
    3. Updates user eligibility status in the world state
    4. Provides eligibility verification for Frame interactions
    """
    
    def __init__(self, neynar_api_client: NeynarAPIClient, 
                 base_nft_service: BaseNFTService,
                 world_state_manager: WorldStateManager):
        self.neynar_api_client = neynar_api_client
        self.base_nft_service = base_nft_service
        self.world_state_manager = world_state_manager
        
        # Configuration
        self.min_token_balance = settings.AIRDROP_MIN_ECOSYSTEM_TOKEN_BALANCE_SOL
        self.min_nft_count = settings.AIRDROP_MIN_ECOSYSTEM_NFT_COUNT_BASE
        self.check_interval = settings.AIRDROP_ELIGIBILITY_CHECK_INTERVAL_HOURS * 3600
        self.token_contract = settings.ECOSYSTEM_TOKEN_CONTRACT_ADDRESS
        
        # Service state
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Start the eligibility checking service."""
        if self._running:
            logger.warning("UserEligibilityService is already running")
            return
            
        if not self.base_nft_service.is_configured():
            logger.warning("Base NFT service not configured, eligibility service will be disabled")
            return
            
        if not self.token_contract:
            logger.warning("Ecosystem token contract not configured, eligibility service will be disabled")
            return
            
        self._running = True
        self._task = asyncio.create_task(self._eligibility_check_loop())
        logger.info("UserEligibilityService started")
        
    async def stop(self):
        """Stop the eligibility checking service."""
        if not self._running:
            return
            
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            
        logger.info("UserEligibilityService stopped")
        
    async def _eligibility_check_loop(self):
        """Main loop for checking user eligibility."""
        while self._running:
            try:
                await self._check_all_users_eligibility()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in eligibility check loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
                
    async def _check_all_users_eligibility(self):
        """Check eligibility for all known Farcaster users."""
        try:
            world_state = self.world_state_manager.get_state()
            farcaster_users = world_state.farcaster_users
            
            logger.info(f"Checking eligibility for {len(farcaster_users)} Farcaster users")
            
            # Process users in batches to avoid overwhelming APIs
            batch_size = 10
            user_items = list(farcaster_users.items())
            
            for i in range(0, len(user_items), batch_size):
                batch = user_items[i:i + batch_size]
                await asyncio.gather(*[
                    self._check_user_eligibility(fid, user_details)
                    for fid, user_details in batch
                ], return_exceptions=True)
                
                # Small delay between batches
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Error checking all users eligibility: {e}")
            
    async def _check_user_eligibility(self, fid: str, user_details: FarcasterUserDetails):
        """Check eligibility for a specific user."""
        try:
            # Skip if checked recently (within 1 hour)
            current_time = time.time()
            if (user_details.last_eligibility_check and 
                current_time - user_details.last_eligibility_check < 3600):
                return
                
            # Get user's verified addresses from Neynar
            verified_addresses = await self._get_user_verified_addresses(fid)
            if not verified_addresses:
                logger.debug(f"No verified addresses found for user {fid}")
                user_details.is_eligible_for_airdrop = False
                user_details.last_eligibility_check = current_time
                return
                
            # Update verified addresses in user details
            user_details.verified_addresses = verified_addresses
            
            # Check Solana token balance
            solana_addresses = verified_addresses.get('solana', [])
            token_balance = 0.0
            
            for address in solana_addresses:
                balance = await self._get_solana_token_balance(address)
                token_balance += balance
                
            user_details.ecosystem_token_balance_sol = token_balance
            
            # Check Base NFT holdings
            evm_addresses = verified_addresses.get('evm', [])
            nft_count = 0
            
            for address in evm_addresses:
                count = await self.base_nft_service.get_nft_balance(address)
                nft_count += count
                
            user_details.ecosystem_nft_count_base = nft_count
            
            # Determine eligibility
            is_eligible = (
                token_balance >= self.min_token_balance or
                nft_count >= self.min_nft_count
            )
            
            user_details.is_eligible_for_airdrop = is_eligible
            user_details.last_eligibility_check = current_time
            
            if is_eligible:
                logger.info(f"User {fid} is eligible (Token: {token_balance}, NFTs: {nft_count})")
            else:
                logger.debug(f"User {fid} not eligible (Token: {token_balance}, NFTs: {nft_count})")
                
        except Exception as e:
            logger.error(f"Error checking eligibility for user {fid}: {e}")
            
    async def _get_user_verified_addresses(self, fid: str) -> Dict[str, List[str]]:
        """Get verified blockchain addresses for a Farcaster user."""
        try:
            # Use Neynar API to get user's verified addresses
            user_data = await self.neynar_api_client.get_user_by_fid(int(fid))
            
            if not user_data:
                return {}
                
            verified_addresses = {'solana': [], 'evm': []}
            
            # Extract verified addresses from user data
            if hasattr(user_data, 'verified_addresses'):
                for address_info in user_data.verified_addresses:
                    address = address_info.get('address', '')
                    if not address:
                        continue
                        
                    # Determine blockchain type by address format
                    if self._is_solana_address(address):
                        verified_addresses['solana'].append(address)
                    elif self._is_evm_address(address):
                        verified_addresses['evm'].append(address)
                        
            return verified_addresses
            
        except Exception as e:
            logger.error(f"Error getting verified addresses for user {fid}: {e}")
            return {}
            
    def _is_solana_address(self, address: str) -> bool:
        """Check if an address is a valid Solana address."""
        try:
            Pubkey.from_string(address)
            return True
        except Exception:
            return False
            
    def _is_evm_address(self, address: str) -> bool:
        """Check if an address is a valid EVM address."""
        return (
            address.startswith('0x') and 
            len(address) == 42 and 
            all(c in '0123456789abcdefABCDEF' for c in address[2:])
        )
        
    async def _get_solana_token_balance(self, wallet_address: str) -> float:
        """Get token balance for a Solana wallet address."""
        try:
            # Use a Solana RPC endpoint (you might want to use Helius or similar for better reliability)
            rpc_url = "https://api.mainnet-beta.solana.com"
            
            # Get token accounts for the wallet
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    wallet_address,
                    {"mint": self.token_contract},
                    {"encoding": "jsonParsed"}
                ]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(rpc_url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        result = data.get('result', {})
                        value = result.get('value', [])
                        
                        total_balance = 0.0
                        for account in value:
                            account_info = account.get('account', {})
                            parsed_info = account_info.get('data', {}).get('parsed', {})
                            token_amount = parsed_info.get('info', {}).get('tokenAmount', {})
                            ui_amount = token_amount.get('uiAmount', 0.0)
                            
                            if ui_amount:
                                total_balance += float(ui_amount)
                                
                        return total_balance
                        
        except Exception as e:
            logger.error(f"Error getting Solana token balance for {wallet_address}: {e}")
            
        return 0.0
        
    async def check_user_eligibility_now(self, fid: str) -> bool:
        """
        Immediately check a user's eligibility (for Frame interactions).
        
        Args:
            fid: Farcaster ID to check
            
        Returns:
            True if user is eligible, False otherwise
        """
        try:
            world_state = self.world_state_manager.get_state()
            user_details = world_state.farcaster_users.get(fid)
            
            if not user_details:
                # User not known, assume not eligible
                return False
                
            # If we have recent eligibility data, use it
            current_time = time.time()
            if (user_details.last_eligibility_check and
                current_time - user_details.last_eligibility_check < 300):  # 5 minutes
                return user_details.is_eligible_for_airdrop
                
            # Otherwise, check now
            await self._check_user_eligibility(fid, user_details)
            return user_details.is_eligible_for_airdrop
            
        except Exception as e:
            logger.error(f"Error checking immediate eligibility for user {fid}: {e}")
            return False
            
    def get_eligibility_summary(self) -> Dict[str, Any]:
        """Get a summary of current eligibility statistics."""
        try:
            world_state = self.world_state_manager.get_state()
            farcaster_users = world_state.farcaster_users
            
            total_users = len(farcaster_users)
            eligible_users = sum(1 for user in farcaster_users.values() 
                               if user.is_eligible_for_airdrop)
            checked_users = sum(1 for user in farcaster_users.values() 
                              if user.last_eligibility_check)
            
            return {
                "total_users": total_users,
                "eligible_users": eligible_users,
                "checked_users": checked_users,
                "eligibility_rate": eligible_users / max(checked_users, 1),
                "min_token_balance": self.min_token_balance,
                "min_nft_count": self.min_nft_count
            }
            
        except Exception as e:
            logger.error(f"Error getting eligibility summary: {e}")
            return {}
