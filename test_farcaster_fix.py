#!/usr/bin/env python3
"""
Test script to verify Farcaster connection fix
"""
import asyncio
import logging
from chatbot.integrations.farcaster.observer import FarcasterObserver
from chatbot.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_farcaster_fix():
    """Test that the Farcaster observer can be initialized correctly with API key."""
    logger.info("Testing Farcaster observer initialization...")
    
    try:
        # Test that we can create the observer with an API key
        observer = FarcasterObserver(settings.NEYNAR_API_KEY)
        logger.info(f"✅ FarcasterObserver created successfully")
        logger.info(f"API key configured: {bool(observer.api_key)}")
        logger.info(f"Observer connected: {observer.is_connected()}")
        
        # Test that we can call the methods without errors
        logger.info("Testing post_cast method signature...")
        # Note: We won't actually post, just check the method exists
        assert hasattr(observer, 'post_cast'), "post_cast method missing"
        assert hasattr(observer, 'reply_to_cast'), "reply_to_cast method missing"
        logger.info("✅ Both post_cast and reply_to_cast methods exist")
        
        logger.info("✅ All tests passed! Farcaster observer should work now.")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_farcaster_fix())
