#!/usr/bin/env python3
"""
Debug test to identify why FarcasterObserver queue processing is failing.
This test will mock the API calls and trace the complete flow.
"""

import asyncio
import time
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from chatbot.integrations.farcaster.observer import FarcasterObserver
from chatbot.core.world_state import WorldStateManager

# Set up detailed logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class MockResponse:
    """Mock httpx response for Neynar API"""
    def __init__(self, status_code=200, json_data=None, headers=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.headers = headers or {}
    
    def json(self):
        return self._json_data

async def test_queue_processing_end_to_end():
    """
    Test the complete flow:
    1. Create FarcasterObserver with real queues
    2. Start background tasks
    3. Schedule posts and replies
    4. Mock the API calls to simulate Neynar responses
    5. Verify queue processing, API calls, and world state updates
    """
    print("🔍 Starting comprehensive FarcasterObserver queue processing test...")
    
    # Create observer with real world state manager
    world_state_manager = WorldStateManager()
    observer = FarcasterObserver(
        api_key="test_key",
        signer_uuid="test_signer", 
        bot_fid="12345",
        world_state_manager=world_state_manager
    )
    
    # Mock the post_cast and reply_to_cast methods to avoid real API calls
    successful_post_response = {
        "success": True,
        "cast": {
            "hash": "0xabc123",
            "author": {"fid": 12345},
            "text": "Test post"
        }
    }
    
    successful_reply_response = {
        "success": True,
        "cast": {
            "hash": "0xdef456", 
            "author": {"fid": 12345},
            "text": "Test reply",
            "parent_hash": "0x789"
        }
    }
    
    observer.post_cast = AsyncMock(return_value=successful_post_response)
    observer.reply_to_cast = AsyncMock(return_value=successful_reply_response)
    
    # Reduce scheduler interval for faster testing
    observer.scheduler_interval = 0.1  # 100ms instead of 60s
    
    print("✅ Observer created with mocked API methods")
    
    try:
        # Start the observer (this should start background tasks)
        print("🚀 Starting FarcasterObserver background tasks...")
        await observer.start()
        
        # Verify tasks were created
        assert observer._post_task is not None, "Post task should be created"
        assert observer._reply_task is not None, "Reply task should be created"
        assert not observer._post_task.done(), "Post task should be running"
        assert not observer._reply_task.done(), "Reply task should be running"
        print("✅ Background tasks started successfully")
        
        # Check initial world state
        initial_actions = len(world_state_manager.state.action_history)
        print(f"📊 Initial action history count: {initial_actions}")
        
        # Schedule a post
        test_post_content = "Test scheduled post content"
        test_channel = "test"
        print(f"📝 Scheduling post: '{test_post_content}' to channel '{test_channel}'")
        observer.schedule_post(test_post_content, test_channel)
        
        # Schedule a reply  
        test_reply_content = "Test scheduled reply content"
        test_reply_hash = "0x789original"
        print(f"💬 Scheduling reply: '{test_reply_content}' to cast '{test_reply_hash}'")
        observer.schedule_reply(test_reply_content, test_reply_hash)
        
        # Check queue sizes
        post_queue_size = observer.post_queue.qsize()
        reply_queue_size = observer.reply_queue.qsize()
        print(f"📋 Queue sizes - Posts: {post_queue_size}, Replies: {reply_queue_size}")
        assert post_queue_size == 1, f"Post queue should have 1 item, has {post_queue_size}"
        assert reply_queue_size == 1, f"Reply queue should have 1 item, has {reply_queue_size}"
        
        # Wait for background tasks to process the queues
        print("⏱️ Waiting for background tasks to process queues...")
        await asyncio.sleep(0.5)  # Wait 500ms for processing
        
        # Check if API methods were called
        print("🔍 Checking if API methods were called...")
        observer.post_cast.assert_called_once_with(test_post_content, test_channel)
        observer.reply_to_cast.assert_called_once_with(test_reply_content, test_reply_hash)
        print("✅ API methods called correctly")
        
        # Check queue sizes after processing
        post_queue_size_after = observer.post_queue.qsize()
        reply_queue_size_after = observer.reply_queue.qsize()
        print(f"📋 Queue sizes after processing - Posts: {post_queue_size_after}, Replies: {reply_queue_size_after}")
        assert post_queue_size_after == 0, f"Post queue should be empty, has {post_queue_size_after} items"
        assert reply_queue_size_after == 0, f"Reply queue should be empty, has {reply_queue_size_after} items"
        
        # Check world state updates
        final_actions = len(world_state_manager.state.action_history)
        new_actions = final_actions - initial_actions
        print(f"📊 Final action history count: {final_actions} (added {new_actions} new actions)")
        
        # Look for successful action results
        recent_actions = world_state_manager.state.action_history[-new_actions:] if new_actions > 0 else []
        success_actions = [a for a in recent_actions if a.result == "success"]
        print(f"✅ Successful actions: {len(success_actions)}")
        
        for action in recent_actions:
            print(f"   - {action.action_type}: {action.result} (params: {action.parameters})")
        
        # Verify we have the expected successful actions
        expected_actions = 2  # One post, one reply
        assert len(success_actions) == expected_actions, f"Expected {expected_actions} successful actions, got {len(success_actions)}"
        
        print("🎉 All checks passed! Queue processing is working correctly.")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        # Clean up - stop the observer
        print("🧹 Cleaning up...")
        await observer.stop()
        print("✅ Observer stopped")

async def test_api_failure_handling():
    """Test how the observer handles API failures"""
    print("🔍 Testing API failure handling...")
    
    world_state_manager = WorldStateManager()
    observer = FarcasterObserver(
        api_key="test_key",
        signer_uuid="test_signer",
        bot_fid="12345", 
        world_state_manager=world_state_manager
    )
    
    # Mock API methods to simulate failures
    observer.post_cast = AsyncMock(return_value={"success": False, "error": "Rate limit exceeded"})
    observer.reply_to_cast = AsyncMock(return_value={"success": False, "error": "Invalid cast hash"})
    observer.scheduler_interval = 0.1
    
    try:
        await observer.start()
        
        # Schedule actions
        observer.schedule_post("Test post", None)
        observer.schedule_reply("Test reply", "0x123")
        
        # Wait for processing
        await asyncio.sleep(0.5)
        
        # Check that API methods were called
        observer.post_cast.assert_called_once()
        observer.reply_to_cast.assert_called_once()
        
        # Check that failure results were recorded
        failure_actions = [a for a in world_state_manager.state.action_history if "failure" in a.result]
        print(f"❌ Failure actions recorded: {len(failure_actions)}")
        
        for action in failure_actions:
            print(f"   - {action.action_type}: {action.result}")
        
        assert len(failure_actions) >= 2, "Should have recorded failure actions"
        print("✅ API failure handling works correctly")
        
    finally:
        await observer.stop()

async def test_task_lifecycle():
    """Test that background tasks start and stop correctly"""
    print("🔍 Testing task lifecycle...")
    
    observer = FarcasterObserver(
        api_key="test_key",
        signer_uuid="test_signer",
        bot_fid="12345"
    )
    
    # Initially no tasks
    assert observer._post_task is None
    assert observer._reply_task is None
    
    # Start observer
    await observer.start()
    
    # Tasks should be created and running
    assert observer._post_task is not None
    assert observer._reply_task is not None
    assert not observer._post_task.done()
    assert not observer._reply_task.done()
    print("✅ Tasks started correctly")
    
    # Stop observer
    await observer.stop()
    
    # Tasks should be cancelled/done
    assert observer._post_task.done()
    assert observer._reply_task.done()
    print("✅ Tasks stopped correctly")

if __name__ == "__main__":
    async def run_all_tests():
        print("=" * 80)
        print("🧪 FARCASTER OBSERVER QUEUE PROCESSING DEBUG TESTS")
        print("=" * 80)
        
        try:
            await test_task_lifecycle()
            print("\n" + "=" * 80)
            
            await test_queue_processing_end_to_end()
            print("\n" + "=" * 80)
            
            await test_api_failure_handling()
            print("\n" + "=" * 80)
            
            print("🎉 ALL TESTS PASSED!")
            
        except Exception as e:
            print(f"💥 TEST SUITE FAILED: {e}")
            import traceback
            traceback.print_exc()
            exit(1)
    
    asyncio.run(run_all_tests())
