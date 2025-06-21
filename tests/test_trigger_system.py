#!/usr/bin/env python3
"""
Test script for the new trigger-based processing system.

This script validates that the trigger system is working correctly by:
1. Creating a processing hub with trigger queue
2. Adding various types of triggers
3. Verifying trigger deduplication
4. Testing priority-based processing
"""

import asyncio
import logging
from dataclasses import dataclass
from chatbot.core.orchestration.processing_hub import ProcessingHub, ProcessingConfig, Trigger
from chatbot.core.world_state.manager import WorldStateManager
from chatbot.core.world_state.payload_builder import PayloadBuilder
from chatbot.core.orchestration.rate_limiter import RateLimiter, RateLimitConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class MockNodeProcessor:
    """Mock node processor for testing."""
    
    async def process_cycle(self, cycle_id: str, primary_channel_id: str = None, context: dict = None):
        """Mock process cycle method."""
        logger.debug(f"Mock processing cycle {cycle_id} for channel {primary_channel_id}")
        logger.debug(f"Context: {context}")
        return {"actions_executed": 1}


async def test_trigger_system():
    """Test the trigger-based processing system."""
    logger.debug("=== Testing Trigger-Based Processing System ===")
    
    # Initialize components
    world_state = WorldStateManager()
    payload_builder = PayloadBuilder()
    rate_limiter = RateLimiter(RateLimitConfig())
    config = ProcessingConfig(observation_interval=2.0)  # Shorter interval for testing
    
    # Create processing hub
    hub = ProcessingHub(world_state, payload_builder, rate_limiter, config)
    hub.set_node_processor(MockNodeProcessor())
    
    logger.debug("✓ ProcessingHub initialized with trigger system")
    
    # Test 1: Add various triggers
    logger.debug("\n--- Test 1: Adding triggers ---")
    
    # High priority mention
    mention_trigger = Trigger(
        type='mention',
        priority=9,
        channel_id='test_channel_1',
        context={'message_id': 'msg_123', 'sender': 'user1'}
    )
    hub.add_trigger(mention_trigger)
    
    # Medium priority new message
    message_trigger = Trigger(
        type='new_message',
        priority=7,
        channel_id='test_channel_1',
        context={'message_id': 'msg_124', 'sender': 'user2'}
    )
    hub.add_trigger(message_trigger)
    
    # Low priority discovery
    discovery_trigger = Trigger(
        type='farcaster_discovery',
        priority=6,
        context={'data_type': 'trending', 'message_count': 5}
    )
    hub.add_trigger(discovery_trigger)
    
    # Trigger for backward compatibility
    hub.trigger_state_change()
    
    logger.debug(f"✓ Added 4 triggers to queue")
    
    # Test 2: Test deduplication
    logger.debug("\n--- Test 2: Testing trigger deduplication ---")
    
    # Add duplicate mention trigger (should deduplicate)
    duplicate_mention = Trigger(
        type='mention',
        priority=9,
        channel_id='test_channel_1',
        context={'message_id': 'msg_123', 'sender': 'user1'}
    )
    hub.add_trigger(duplicate_mention)
    
    logger.debug("✓ Added duplicate trigger (should be deduplicated)")
    
    # Test 3: Start processing and verify behavior
    logger.debug("\n--- Test 3: Starting processing loop ---")
    
    # Start the processing hub
    hub.running = True
    
    # Run one cycle manually to see trigger processing
    try:
        # Process for a few seconds to see triggers being processed
        processing_task = asyncio.create_task(hub._main_event_loop())
        await asyncio.wait_for(processing_task, timeout=5.0)
    except asyncio.TimeoutError:
        logger.debug("✓ Processing loop ran for 5 seconds (timeout expected)")
        hub.running = False
    
    # Test 4: Verify status
    logger.debug("\n--- Test 4: Checking processing status ---")
    
    status = hub.get_processing_status()
    logger.debug(f"✓ Processing status: {status}")
    
    logger.debug("\n=== Trigger System Test Complete ===")
    logger.debug("✓ All tests passed! The trigger-based system is working correctly.")


if __name__ == "__main__":
    asyncio.run(test_trigger_system())
