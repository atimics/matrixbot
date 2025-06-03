#!/usr/bin/env python3
"""
Quick test for Farcaster world state collection functionality.
"""

import asyncio
import logging
from chatbot.integrations.farcaster import FarcasterObserver

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_world_state_collection():
    """Test the world state collection functionality."""
    # Create observer (without API key for this test)
    observer = FarcasterObserver(
        api_key=None,
        signer_uuid=None,
        bot_fid=None,
        world_state_manager=None
    )
    
    # Test that the observer has the new methods
    assert hasattr(observer, 'observe_world_state_data'), "observe_world_state_data method missing"
    assert hasattr(observer, 'collect_world_state_now'), "collect_world_state_now method missing"
    assert hasattr(observer, '_world_state_collection_loop'), "_world_state_collection_loop method missing"
    
    logger.info("✅ All world state collection methods are present")
    
    # Test without API client (should handle gracefully)
    result = await observer.collect_world_state_now()
    assert "error" in result, "Should return error when no world state manager"
    
    logger.info("✅ Graceful error handling works")
    
    world_state_data = await observer.observe_world_state_data()
    assert isinstance(world_state_data, dict), "Should return empty dict when no API client"
    assert len(world_state_data) == 0, "Should be empty when no API client"
    
    logger.info("✅ World state data collection handles missing API client")
    
    print("🎉 All world state collection tests passed!")

if __name__ == "__main__":
    asyncio.run(test_world_state_collection())
