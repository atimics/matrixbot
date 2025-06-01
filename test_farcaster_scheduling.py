#!/usr/bin/env python3
"""
Debug script to test Farcaster scheduled reply functionality
"""

import asyncio
import logging
import sys
import os

# Add the chatbot module to the Python path
sys.path.insert(0, '/workspaces/python3-poetry-pyenv')

from chatbot.integrations.farcaster.observer import FarcasterObserver
from chatbot.core.world_state import WorldStateManager

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_farcaster_scheduling():
    """Test the Farcaster scheduling mechanism"""
    logger.info("Starting Farcaster scheduling test...")
    
    # Create a mock world state manager
    world_state_manager = WorldStateManager()
    
    # Create observer with dummy credentials (won't actually send, but will test scheduling)
    observer = FarcasterObserver(
        api_key="dummy_key",
        signer_uuid="dummy_signer",
        bot_fid="dummy_fid",
        world_state_manager=world_state_manager
    )
    
    # Set very short interval for testing
    observer.scheduler_interval = 2.0  # 2 seconds for quick testing
    
    try:
        # Start the observer (this will start the background tasks)
        await observer.start()
        logger.info("Observer started, background tasks should be running")
        
        # Schedule a couple of test replies
        observer.schedule_reply("Test reply 1", "0x123abc")
        observer.schedule_reply("Test reply 2", "0x456def")
        
        logger.info(f"Scheduled 2 replies. Queue sizes: post_queue={observer.post_queue.qsize()}, reply_queue={observer.reply_queue.qsize()}")
        
        # Wait for a bit to see if the background tasks process the queue
        logger.info("Waiting 10 seconds to observe scheduling behavior...")
        await asyncio.sleep(10)
        
        logger.info(f"After 10 seconds - Queue sizes: post_queue={observer.post_queue.qsize()}, reply_queue={observer.reply_queue.qsize()}")
        
    except Exception as e:
        logger.error(f"Error during test: {e}", exc_info=True)
    finally:
        # Stop the observer
        await observer.stop()
        logger.info("Observer stopped")

if __name__ == "__main__":
    asyncio.run(test_farcaster_scheduling())
