#!/usr/bin/env python3
"""
Test script to verify Farcaster notifications feed works correctly
"""

import asyncio
import logging
import os

from chatbot.config import AppConfig
from chatbot.integrations.farcaster.observer import FarcasterObserver

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_notifications():
    """Test Farcaster notifications and mentions observation"""
    settings = AppConfig()
    
    if not settings.NEYNAR_API_KEY:
        logger.error("NEYNAR_API_KEY not configured")
        return
        
    if not settings.FARCASTER_BOT_FID:
        logger.error("FARCASTER_BOT_FID not configured")
        return
    
    # Initialize observer
    observer = FarcasterObserver(
        api_key=settings.NEYNAR_API_KEY,
        signer_uuid=settings.FARCASTER_BOT_SIGNER_UUID,
        bot_fid=settings.FARCASTER_BOT_FID
    )
    
    logger.info(f"Observer status: {observer.get_status()}")
    logger.info(f"Can observe notifications: {observer.can_observe_notifications()}")
    
    # Test observation with notifications enabled
    logger.info("Testing Farcaster observation with notifications...")
    messages = await observer.observe_feeds(
        channels=["dev", "warpcast"],
        include_notifications=True
    )
    
    logger.info(f"Received {len(messages)} total messages")
    
    # Group messages by channel
    by_channel = {}
    for msg in messages:
        if msg.channel_id not in by_channel:
            by_channel[msg.channel_id] = []
        by_channel[msg.channel_id].append(msg)
    
    for channel_id, msgs in by_channel.items():
        logger.info(f"Channel '{channel_id}': {len(msgs)} messages")
        for msg in msgs[:3]:  # Show first 3 messages
            logger.info(f"  - {msg.sender}: {msg.content[:100]}{'...' if len(msg.content) > 100 else ''}")


if __name__ == "__main__":
    asyncio.run(test_notifications())
