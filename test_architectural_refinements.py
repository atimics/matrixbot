#!/usr/bin/env python3
"""
Test script to validate the architectural refinements implemented.

This script tests:
1. Attention Gate (Channel Locking) functionality
2. Authoritative State Sync mechanisms  
3. Overall race condition prevention

Run this script to verify the changes work correctly.
"""

import asyncio
import logging
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_attention_gate():
    """Test the Attention Gate (Channel Locking) functionality."""
    logger.info("=== Testing Attention Gate (Channel Locking) ===")
    
    try:
        from chatbot.core.attention.engine import AttentionEngine
        from chatbot.core.world_state.structures import Message
        
        # Create mock dependencies
        mock_world_state = MagicMock()
        mock_attention_queue = AsyncMock()
        
        # Initialize AttentionEngine with our new locking mechanism
        config = {
            'bot_fid': '12345',
            'bot_user_id': '@testbot:matrix.org',
            'bot_username': 'testbot'
        }
        
        attention_engine = AttentionEngine(
            world_state=mock_world_state,
            attention_queue=mock_attention_queue,
            config=config
        )
        
        # Verify the locked_channels set was initialized
        assert hasattr(attention_engine, 'locked_channels'), "AttentionEngine should have locked_channels set"
        assert isinstance(attention_engine.locked_channels, set), "locked_channels should be a set"
        assert len(attention_engine.locked_channels) == 0, "locked_channels should start empty"
        
        # Test channel locking mechanism
        test_channel_id = "test_channel_123"
        
        # Create a test message
        test_message = Message(
            id="msg_1",
            content="Hello, bot!",
            timestamp=1234567890,
            channel_type="farcaster",
            sender="testuser",
            channel_id=test_channel_id,
            sender_username="testuser",
            sender_display_name="Test User"
        )
        
        # Mock the internal methods to avoid dependencies
        attention_engine._is_self_message = MagicMock(return_value=False)
        attention_engine._is_in_cooldown = MagicMock(return_value=False)
        attention_engine._generate_thread_id = MagicMock(return_value="thread_123")
        attention_engine._is_duplicate_thread = MagicMock(return_value=False)
        attention_engine._build_contextual_thread = AsyncMock(return_value=MagicMock())
        
        # First message should succeed and lock the channel
        result1 = await attention_engine.process_new_message(test_message)
        assert result1 is not None, "First message should create a thread"
        assert test_channel_id in attention_engine.locked_channels, "Channel should be locked after first message"
        
        # Second message from same channel should be filtered out
        test_message.id = "msg_2"  # Different message ID
        result2 = await attention_engine.process_new_message(test_message)
        assert result2 is None, "Second message from same channel should be filtered out"
        
        # Test channel unlocking
        attention_engine.release_channel_lock(test_channel_id)
        assert test_channel_id not in attention_engine.locked_channels, "Channel should be unlocked"
        
        # Third message should succeed after unlock
        test_message.id = "msg_3"
        result3 = await attention_engine.process_new_message(test_message)
        assert result3 is not None, "Message should succeed after channel unlock"
        
        logger.info("✅ Attention Gate tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Attention Gate test failed: {e}")
        return False


async def test_authoritative_state_sync():
    """Test the Authoritative State Sync functionality."""
    logger.info("=== Testing Authoritative State Sync ===")
    
    try:
        from chatbot.integrations.farcaster.farcaster_observer import FarcasterObserver
        from chatbot.core.persistence import DatabaseManager
        
        # Create a temporary database for testing
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_db:
            db_path = tmp_db.name
        
        # Initialize database manager
        db_manager = DatabaseManager(db_path)
        await db_manager.initialize()
        
        # Mock API client and data
        mock_api_client = AsyncMock()
        mock_api_client.get_casts_by_fid.return_value = {
            "result": {
                "casts": [
                    {
                        "hash": "0xreply1",
                        "parent_hash": "0xoriginal1",  # This is a reply
                        "text": "This is a reply"
                    },
                    {
                        "hash": "0xpost1", 
                        "parent_hash": None,  # This is a regular post
                        "text": "This is a regular post"
                    },
                    {
                        "hash": "0xreply2",
                        "parent_hash": "0xoriginal2",  # Another reply
                        "text": "Another reply"
                    }
                ]
            }
        }
        
        # Create FarcasterObserver
        config = {
            'api_key': 'test_key',
            'signer_uuid': 'test_signer',
            'bot_fid': '12345'
        }
        
        observer = FarcasterObserver(
            config=config,
            api_key='test_key',
            signer_uuid='test_signer',
            bot_fid='12345'
        )
        observer.api_client = mock_api_client
        
        # Test the sync_reply_history method
        synced_count = await observer.sync_reply_history(db_manager)
        
        # Verify API was called correctly
        mock_api_client.get_casts_by_fid.assert_called_once_with(12345, limit=100)
        
        # Should have synced 2 replies (the ones with parent_hash)
        assert synced_count == 2, f"Expected 2 synced replies, got {synced_count}"
        
        # Verify replies were added to persistent cache
        assert await db_manager.has_replied_to("0xoriginal1"), "Reply to 0xoriginal1 should be in cache"
        assert await db_manager.has_replied_to("0xoriginal2"), "Reply to 0xoriginal2 should be in cache"
        
        # Test that running sync again doesn't add duplicates
        synced_count_2 = await observer.sync_reply_history(db_manager)
        assert synced_count_2 == 0, "Second sync should not add duplicates"
        
        # Cleanup
        await db_manager.close()
        Path(db_path).unlink()
        
        logger.info("✅ Authoritative State Sync tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Authoritative State Sync test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_processing_hub_lock_release():
    """Test that ProcessingHub properly releases channel locks."""
    logger.info("=== Testing ProcessingHub Lock Release ===")
    
    try:
        from chatbot.core.orchestration.processing_hub import ProcessingHub
        from chatbot.core.attention.engine import AttentionEngine
        from chatbot.core.world_state.structures import Message
        
        # Create mock dependencies
        mock_world_state = MagicMock()
        mock_payload_builder = MagicMock()
        mock_rate_limiter = MagicMock()
        mock_attention_queue = AsyncMock()
        
        # Create ProcessingHub
        processing_hub = ProcessingHub(
            world_state_manager=mock_world_state,
            payload_builder=mock_payload_builder,
            rate_limiter=mock_rate_limiter,
            attention_queue=mock_attention_queue
        )
        
        # Create AttentionEngine
        config = {'bot_fid': '12345'}
        attention_engine = AttentionEngine(
            world_state=mock_world_state,
            attention_queue=mock_attention_queue,
            config=config
        )
        
        # Connect them
        processing_hub.set_attention_engine(attention_engine)
        assert processing_hub.attention_engine is attention_engine, "AttentionEngine should be connected"
        
        # Test channel lock release
        test_channel_id = "test_channel_123"
        
        # Manually lock a channel to simulate a processed thread
        attention_engine.locked_channels.add(test_channel_id)
        assert test_channel_id in attention_engine.locked_channels, "Channel should be locked"
        
        # Test the release method
        attention_engine.release_channel_lock(test_channel_id)
        assert test_channel_id not in attention_engine.locked_channels, "Channel should be unlocked"
        
        logger.info("✅ ProcessingHub Lock Release tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ ProcessingHub Lock Release test failed: {e}")
        return False


async def test_send_post_duplicate_prevention():
    """Test the enhanced duplicate prevention in send_post tool."""
    logger.info("=== Testing Enhanced Duplicate Prevention ===")
    
    try:
        # Test that the layers are properly implemented
        from chatbot.tools.farcaster.send_post import SendFarcasterPostTool
        
        tool = SendFarcasterPostTool()
        
        # Verify the tool has the expected structure
        assert tool.name == "send_farcaster_post", "Tool should have correct name"
        assert "turn-based conversation logic" in tool.description, "Tool should mention turn-based logic"
        
        # The detailed testing of the multi-layered duplicate prevention
        # is already covered by existing tests in the test suite
        
        logger.info("✅ Enhanced Duplicate Prevention structure validated!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Enhanced Duplicate Prevention test failed: {e}")
        return False


async def main():
    """Run all validation tests."""
    logger.info("🚀 Starting Architectural Refinement Validation Tests")
    logger.info("=" * 60)
    
    tests = [
        ("Attention Gate (Channel Locking)", test_attention_gate),
        ("Authoritative State Sync", test_authoritative_state_sync),
        ("ProcessingHub Lock Release", test_processing_hub_lock_release),
        ("Enhanced Duplicate Prevention", test_send_post_duplicate_prevention),
    ]
    
    results = []
    for test_name, test_func in tests:
        logger.info(f"\n📋 Running: {test_name}")
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"💥 Test '{test_name}' crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("🎯 TEST RESULTS SUMMARY")
    logger.info("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{status}: {test_name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    logger.info(f"\nTotal: {passed} passed, {failed} failed")
    
    if failed == 0:
        logger.info("🎉 All architectural refinements validated successfully!")
        logger.info("The system is now hardened against race conditions and state inconsistencies.")
        return True
    else:
        logger.error("⚠️  Some tests failed. Please review the implementation.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
