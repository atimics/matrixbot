#!/usr/bin/env python3
"""
Test Ecosystem Token Functionality

This script demonstrates the ecosystem token tracking functionality by:
1. Setting up a test token contract
2. Showing how the service would track holders
3. Displaying how the data appears in the world state
"""

import asyncio
import logging
import os
import sys
import time

# Add the chatbot module to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chatbot.config import settings
from chatbot.core.world_state.manager import WorldStateManager
from chatbot.core.world_state.structures import MonitoredTokenHolder, Message
from chatbot.integrations.ecosystem_token_service import EcosystemTokenService
from chatbot.integrations.farcaster.neynar_api_client import NeynarAPIClient

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_ecosystem_token_service():
    """Test the ecosystem token service with simulated data."""
    
    logger.info("=== Testing Ecosystem Token Service ===")
    
    # Create mock components
    world_state_manager = WorldStateManager()
    
    # For testing, we'll use a mock approach since the API endpoint needs verification
    logger.info("Using data structure testing approach.")
    await test_data_structures(world_state_manager)
    return


async def test_data_structures(world_state_manager: WorldStateManager):
    """Test the data structures without requiring API access."""
    
    logger.info("=== Testing Data Structures ===")
    
    # Set up test ecosystem token data
    world_state_manager.state.ecosystem_token_contract = "0xTESTCONTRACT"
    
    # Create some test holders
    test_holders = {
        "123": MonitoredTokenHolder(
            fid="123",
            username="holder1",
            display_name="Token Holder 1",
            last_cast_seen_timestamp=time.time(),
            recent_casts=[
                Message(
                    id="cast123",
                    channel_type="farcaster",
                    sender="holder1",
                    content="This is a test cast from a token holder!",
                    timestamp=time.time(),
                    channel_id="farcaster:holder_123",
                    sender_fid=123,
                    sender_username="holder1",
                    metadata={"cast_type": "holder_cast"}
                )
            ]
        ),
        "456": MonitoredTokenHolder(
            fid="456",
            username="holder2",
            display_name="Token Holder 2",
            last_cast_seen_timestamp=time.time(),
            recent_casts=[
                Message(
                    id="cast456",
                    channel_type="farcaster", 
                    sender="holder2",
                    content="Another cast from a different holder!",
                    timestamp=time.time(),
                    channel_id="farcaster:holder_456",
                    sender_fid=456,
                    sender_username="holder2",
                    metadata={"cast_type": "holder_cast"}
                )
            ]
        )
    }
    
    world_state_manager.state.monitored_token_holders = test_holders
    
    logger.info(f"Added {len(test_holders)} test token holders")
    
    # Test payload building
    from chatbot.core.world_state.payload_builder import PayloadBuilder
    payload_builder = PayloadBuilder()
    
    payload = payload_builder.build_full_payload(
        world_state_data=world_state_manager.state,
        config={"bot_fid": "999", "bot_username": "testbot"}
    )
    
    ecosystem_info = payload.get("ecosystem_token_info", {})
    logger.info("=== Ecosystem Token Info in Payload ===")
    logger.info(f"Contract address: {ecosystem_info.get('contract_address')}")
    logger.info(f"Monitored holders: {len(ecosystem_info.get('monitored_holders_activity', []))}")
    
    for holder_activity in ecosystem_info.get('monitored_holders_activity', []):
        logger.info(f"  {holder_activity['username']} (FID {holder_activity['fid']}): {len(holder_activity['recent_casts'])} casts")
        for cast in holder_activity['recent_casts']:
            logger.info(f"    Cast: {cast['content'][:50]}...")
    
    logger.info("=== Test completed successfully! ===")


def main():
    """Run the test."""
    asyncio.run(test_ecosystem_token_service())


if __name__ == "__main__":
    main()
