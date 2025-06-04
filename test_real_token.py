#!/usr/bin/env python3
"""
Test script for Ecosystem Token Service with real token contract
Tests the complete ecosystem token tracking functionality with the provided token address.
"""

import asyncio
import logging
import os
import sys

# Add the project root to Python path
sys.path.insert(0, '/workspaces/python3-poetry-pyenv')

from chatbot.config import settings
from chatbot.integrations.farcaster.neynar_api_client import NeynarAPIClient
from chatbot.integrations.ecosystem_token_service import EcosystemTokenService
from chatbot.core.world_state.manager import WorldStateManager
from chatbot.core.world_state.payload_builder import PayloadBuilder

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_real_token_tracking():
    """Test ecosystem token tracking with the real token contract."""
    logger.info("=== Testing Ecosystem Token Service with Real Token ===")
    
    # Check if we have API key
    neynar_api_key = os.getenv('NEYNAR_API_KEY')
    if not neynar_api_key:
        logger.warning("NEYNAR_API_KEY not found in environment. Using mock data.")
        await test_with_mock_data()
        return
    
    logger.info(f"Token contract: {settings.ECOSYSTEM_TOKEN_CONTRACT_ADDRESS}")
    logger.info(f"Tracking {settings.NUM_TOP_HOLDERS_TO_TRACK} top holders")
    
    # Initialize components
    world_state_manager = WorldStateManager()
    neynar_client = NeynarAPIClient(api_key=neynar_api_key)
    ecosystem_service = EcosystemTokenService(neynar_client, world_state_manager)
    
    try:
        # Test 1: Check API endpoint for token holders
        logger.info("\n=== Test 1: API Token Holder Endpoint ===")
        holders_response = await neynar_client.get_token_holders(
            settings.ECOSYSTEM_TOKEN_CONTRACT_ADDRESS, 
            limit=5
        )
        logger.info(f"Token holders response: {holders_response}")
        
        # Test 2: Attempt to get user balance (if we have test FIDs)
        logger.info("\n=== Test 2: User Token Balance ===")
        test_fid = 1  # Vitalik's FID for testing
        balance_response = await neynar_client.get_user_token_balance(
            test_fid, 
            settings.ECOSYSTEM_TOKEN_CONTRACT_ADDRESS
        )
        logger.info(f"User {test_fid} balance response: {balance_response}")
        
        # Test 3: Get user details for bulk FIDs
        logger.info("\n=== Test 3: Bulk User Details ===")
        test_fids = [1, 2, 3]  # Test with some well-known FIDs
        users_response = await neynar_client.get_user_details_for_fids(test_fids)
        logger.info(f"Bulk users response: {users_response}")
        
        # Test 4: Get casts for a user
        logger.info("\n=== Test 4: User Casts ===")
        casts_response = await neynar_client.get_casts_by_fid(1, limit=3)
        logger.info(f"User casts response keys: {list(casts_response.keys()) if casts_response else 'None'}")
        if casts_response and "casts" in casts_response:
            logger.info(f"Found {len(casts_response['casts'])} casts")
        
        # Test 5: Update token holders in world state
        logger.info("\n=== Test 5: World State Update ===")
        await ecosystem_service.update_top_token_holders_in_world_state()
        
        # Check world state
        token_info = world_state_manager.state
        logger.info(f"World state ecosystem token contract: {token_info.ecosystem_token_contract}")
        logger.info(f"Monitored token holders: {len(token_info.monitored_token_holders)}")
        for fid, holder in token_info.monitored_token_holders.items():
            logger.info(f"  {holder.username or 'unknown'} (FID {fid}): {len(holder.recent_casts)} recent casts")
        
        # Test 6: Generate payload with ecosystem token info
        logger.info("\n=== Test 6: Payload Generation ===")
        payload_builder = PayloadBuilder()
        payload = payload_builder.build_optimized_payload(world_state_manager.state)
        
        if "ecosystem_token_info" in payload:
            token_payload = payload["ecosystem_token_info"]
            logger.info(f"Ecosystem token in payload:")
            logger.info(f"  Contract: {token_payload.get('contract_address')}")
            logger.info(f"  Holders: {len(token_payload.get('monitored_holders', {}))}")
            for fid, holder_info in token_payload.get('monitored_holders', {}).items():
                logger.info(f"    {holder_info.get('username', 'unknown')} (FID {fid}): {len(holder_info.get('recent_casts', []))} casts")
        else:
            logger.warning("No ecosystem_token_info in payload")
        
        logger.info("\n=== Real Token Test Completed ===")
        
    except Exception as e:
        logger.error(f"Error during real token testing: {e}", exc_info=True)
    finally:
        await neynar_client.close()

async def test_with_mock_data():
    """Test with mock data when API key is not available."""
    logger.info("=== Testing with Mock Data ===")
    
    # Initialize components
    world_state_manager = WorldStateManager()
    
    # Simulate token holder data
    from chatbot.core.world_state.structures import MonitoredTokenHolder, Message
    import time
    
    # Add mock holders
    mock_holders = {
        "123": MonitoredTokenHolder(
            fid="123",
            username="holder1",
            display_name="Token Holder 1",
            recent_casts=[
                Message(
                    id="cast1",
                    author_fid="123",
                    author_username="holder1",
                    content="This is a test cast from token holder 1!",
                    timestamp=int(time.time()),
                    channel_id="farcaster:holder_123",
                    message_type="holder_cast"
                )
            ]
        ),
        "456": MonitoredTokenHolder(
            fid="456", 
            username="holder2",
            display_name="Token Holder 2",
            recent_casts=[
                Message(
                    id="cast2",
                    author_fid="456",
                    author_username="holder2",
                    content="Another cast from token holder 2!",
                    timestamp=int(time.time()),
                    channel_id="farcaster:holder_456",
                    message_type="holder_cast"
                )
            ]
        )
    }
    
    world_state_manager.state.ecosystem_token_contract = settings.ECOSYSTEM_TOKEN_CONTRACT_ADDRESS
    world_state_manager.state.monitored_token_holders = mock_holders
    
    # Test payload generation
    payload_builder = PayloadBuilder()
    payload = payload_builder.build_optimized_payload(world_state_manager.state)
    
    logger.info(f"Mock test - Token contract: {world_state_manager.state.ecosystem_token_contract}")
    logger.info(f"Mock test - Monitored holders: {len(world_state_manager.state.monitored_token_holders)}")
    
    if "ecosystem_token_info" in payload:
        token_payload = payload["ecosystem_token_info"]
        logger.info(f"Ecosystem token in payload:")
        logger.info(f"  Contract: {token_payload.get('contract_address')}")
        logger.info(f"  Holders: {len(token_payload.get('monitored_holders', {}))}")
        for fid, holder_info in token_payload.get('monitored_holders', {}).items():
            logger.info(f"    {holder_info.get('username', 'unknown')} (FID {fid}): {len(holder_info.get('recent_casts', []))} casts")
    
    logger.info("=== Mock Test Completed ===")

if __name__ == "__main__":
    asyncio.run(test_real_token_tracking())
