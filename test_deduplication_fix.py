#!/usr/bin/env python3
"""
Test to verify the deduplication bug fix.

This test demonstrates that previously, replies would be silently dropped
if the target cast hash was in last_seen_hashes from feed monitoring.
"""

import asyncio
import logging
from chatbot.integrations.farcaster.farcaster_observer import FarcasterObserver
from chatbot.core.world_state import WorldStateManager

# Configure logging to see what's happening
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_deduplication_bug_fix():
    """Test that replies work even when cast hash is in last_seen_hashes."""
    
    print("🧪 Testing deduplication bug fix...")
    
    # Create observer and world state manager
    world_state = WorldStateManager()
    observer = FarcasterObserver(
        api_key="test_key",
        signer_uuid="test_signer",
        bot_fid="12345",
        world_state_manager=world_state
    )
    
    # Simulate the bug scenario: cast hash in last_seen_hashes from feed monitoring
    test_cast_hash = "0x123abc456def"
    observer.last_seen_hashes.add(test_cast_hash)
    print(f"✅ Added {test_cast_hash} to last_seen_hashes (simulating feed monitoring)")
    print(f"📊 last_seen_hashes: {observer.last_seen_hashes}")
    print(f"📊 replied_to_hashes: {observer.replied_to_hashes}")
    
    # Try to schedule a reply to that cast
    print(f"\n🎯 Attempting to schedule reply to cast {test_cast_hash}...")
    initial_queue_size = observer.reply_queue.qsize()
    print(f"📊 Initial queue size: {initial_queue_size}")
    
    observer.schedule_reply(
        content="This is a test reply",
        reply_to_hash=test_cast_hash,
        action_id="test_action_123"
    )
    
    final_queue_size = observer.reply_queue.qsize()
    print(f"📊 Final queue size: {final_queue_size}")
    
    if final_queue_size > initial_queue_size:
        print("✅ SUCCESS: Reply was scheduled despite cast being in last_seen_hashes!")
        print("🐛 Bug fix confirmed: Using separate replied_to_hashes set works correctly")
    else:
        print("❌ FAILURE: Reply was not scheduled - bug still exists!")
        return False
    
    # Test that duplicate reply prevention still works
    print(f"\n🔄 Testing duplicate reply prevention...")
    observer.schedule_reply(
        content="This is a duplicate reply attempt",
        reply_to_hash=test_cast_hash,
        action_id="test_action_456"
    )
    
    duplicate_queue_size = observer.reply_queue.qsize()
    print(f"📊 Queue size after duplicate attempt: {duplicate_queue_size}")
    
    if duplicate_queue_size == final_queue_size:
        print("✅ SUCCESS: Duplicate reply was correctly prevented!")
    else:
        print("❌ FAILURE: Duplicate reply was not prevented!")
        return False
    
    print("\n🎉 All deduplication tests passed!")
    return True

if __name__ == "__main__":
    success = asyncio.run(test_deduplication_bug_fix())
    if not success:
        exit(1)
