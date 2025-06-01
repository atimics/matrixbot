#!/usr/bin/env python3
"""
Updated test to verify the fixed Farcaster action status tracking.
This test verifies that "scheduled" actions are properly updated to "success"/"failure".
"""

import asyncio
import time
import logging
from unittest.mock import AsyncMock, MagicMock
from chatbot.integrations.farcaster.observer import FarcasterObserver
from chatbot.core.world_state import WorldStateManager
from chatbot.tools.farcaster_tools import SendFarcasterPostTool, SendFarcasterReplyTool
from chatbot.tools.base import ActionContext

# Set up detailed logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test_scheduled_action_status_updates():
    """
    Test the complete flow of scheduled action status updates:
    1. Tool schedules action with "scheduled" status
    2. Observer processes queue and updates status to "success"/"failure"
    3. Verify that the same action entry is updated, not duplicated
    """
    print("🔍 Testing scheduled action status updates...")
    
    # Create observer with real world state manager
    world_state_manager = WorldStateManager()
    observer = FarcasterObserver(
        api_key="test_key",
        signer_uuid="test_signer", 
        bot_fid="12345",
        world_state_manager=world_state_manager
    )
    
    # Mock the API methods 
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
    observer.scheduler_interval = 0.1  # Fast processing for testing
    
    # Create action context
    context = ActionContext(
        matrix_observer=None,
        farcaster_observer=observer,
        world_state_manager=world_state_manager,
        context_manager=None
    )
    
    print("✅ Setup complete")
    
    try:
        # Start the observer background tasks
        await observer.start()
        
        # Test 1: Post Tool Scheduling and Processing
        print("\n📝 Testing post tool...")
        post_tool = SendFarcasterPostTool()
        
        # Check initial state
        initial_count = len(world_state_manager.state.action_history)
        
        # Execute tool to schedule post
        post_params = {"content": "Test scheduled post", "channel": "test"}
        post_result = await post_tool.execute(post_params, context)
        
        # Verify tool returned "scheduled" status
        assert post_result["status"] == "scheduled", f"Expected 'scheduled', got {post_result['status']}"
        post_action_id = post_result.get("action_id")
        assert post_action_id is not None, "Tool should return action_id"
        
        # Check that one "scheduled" action was added
        scheduled_count = len(world_state_manager.state.action_history)
        assert scheduled_count == initial_count + 1, f"Expected 1 new action, got {scheduled_count - initial_count}"
        
        scheduled_action = world_state_manager.state.action_history[-1]
        assert scheduled_action.result == "scheduled", f"Action should be 'scheduled', got {scheduled_action.result}"
        assert scheduled_action.action_id == post_action_id, "Action ID should match"
        
        print(f"✅ Post scheduled with action_id: {post_action_id}")
        
        # Wait for background processing
        await asyncio.sleep(0.5)
        
        # Verify that the same action was updated (not a new one added)
        final_count = len(world_state_manager.state.action_history)
        assert final_count == scheduled_count, f"No new actions should be added, but count changed from {scheduled_count} to {final_count}"
        
        # Find the action and verify it was updated
        updated_action = None
        for action in world_state_manager.state.action_history:
            if action.action_id == post_action_id:
                updated_action = action
                break
        
        assert updated_action is not None, f"Could not find action with ID {post_action_id}"
        assert updated_action.result == "success", f"Action should be 'success', got {updated_action.result}"
        assert updated_action.parameters.get("cast_hash") == "0xabc123", "Cast hash should be added to parameters"
        
        print("✅ Post action successfully updated from 'scheduled' to 'success'")
        
        # Test 2: Reply Tool Scheduling and Processing  
        print("\n💬 Testing reply tool...")
        reply_tool = SendFarcasterReplyTool()
        
        # Execute tool to schedule reply
        reply_params = {"content": "Test scheduled reply", "reply_to_hash": "0x789original"}
        reply_result = await reply_tool.execute(reply_params, context)
        
        # Verify tool returned "scheduled" status
        assert reply_result["status"] == "scheduled", f"Expected 'scheduled', got {reply_result['status']}"
        reply_action_id = reply_result.get("action_id")
        assert reply_action_id is not None, "Tool should return action_id"
        
        # Check that one more "scheduled" action was added
        before_processing_count = len(world_state_manager.state.action_history)
        assert before_processing_count == final_count + 1, "One new scheduled action should be added"
        
        scheduled_reply_action = world_state_manager.state.action_history[-1]
        assert scheduled_reply_action.result == "scheduled", f"Action should be 'scheduled', got {scheduled_reply_action.result}"
        assert scheduled_reply_action.action_id == reply_action_id, "Action ID should match"
        
        print(f"✅ Reply scheduled with action_id: {reply_action_id}")
        
        # Wait for background processing
        await asyncio.sleep(0.5)
        
        # Verify that the same action was updated (not a new one added)
        final_reply_count = len(world_state_manager.state.action_history)
        assert final_reply_count == before_processing_count, f"No new actions should be added, but count changed from {before_processing_count} to {final_reply_count}"
        
        # Find the reply action and verify it was updated
        updated_reply_action = None
        for action in world_state_manager.state.action_history:
            if action.action_id == reply_action_id:
                updated_reply_action = action
                break
        
        assert updated_reply_action is not None, f"Could not find action with ID {reply_action_id}"
        assert updated_reply_action.result == "success", f"Action should be 'success', got {updated_reply_action.result}"
        assert updated_reply_action.parameters.get("cast_hash") == "0xdef456", "Cast hash should be added to parameters"
        
        print("✅ Reply action successfully updated from 'scheduled' to 'success'")
        
        # Test 3: Verify API calls were made correctly
        observer.post_cast.assert_called_once_with("Test scheduled post", "test")
        observer.reply_to_cast.assert_called_once_with("Test scheduled reply", "0x789original")
        print("✅ API calls made correctly")
        
        # Test 4: Summary of final state
        print(f"\n📊 Final action history summary:")
        for i, action in enumerate(world_state_manager.state.action_history):
            print(f"   {i+1}. {action.action_type}: {action.result} (ID: {action.action_id})")
            if action.parameters.get("cast_hash"):
                print(f"      Cast hash: {action.parameters['cast_hash']}")
        
        print("🎉 All scheduled action status update tests passed!")
        
    finally:
        await observer.stop()

async def test_failure_case():
    """Test that failed actions are properly updated"""
    print("\n🔍 Testing failure case...")
    
    world_state_manager = WorldStateManager()
    observer = FarcasterObserver(
        api_key="test_key",
        signer_uuid="test_signer",
        bot_fid="12345", 
        world_state_manager=world_state_manager
    )
    
    # Mock API to return failure
    failure_response = {"success": False, "error": "Rate limit exceeded"}
    observer.post_cast = AsyncMock(return_value=failure_response)
    observer.scheduler_interval = 0.1
    
    context = ActionContext(
        matrix_observer=None,
        farcaster_observer=observer,
        world_state_manager=world_state_manager,
        context_manager=None
    )
    
    try:
        await observer.start()
        
        # Schedule and process a post that will fail
        post_tool = SendFarcasterPostTool()
        post_result = await post_tool.execute({"content": "Test post", "channel": None}, context)
        
        action_id = post_result.get("action_id")
        assert action_id is not None
        
        # Wait for processing
        await asyncio.sleep(0.5)
        
        # Find the action and verify it was updated to failure
        updated_action = None
        for action in world_state_manager.state.action_history:
            if action.action_id == action_id:
                updated_action = action
                break
        
        assert updated_action is not None
        assert "failure" in updated_action.result, f"Expected failure, got {updated_action.result}"
        assert "Rate limit exceeded" in updated_action.result, "Should include error message"
        
        print("✅ Failure case handled correctly")
        
    finally:
        await observer.stop()

if __name__ == "__main__":
    async def run_all_tests():
        print("=" * 80)
        print("🧪 FARCASTER SCHEDULED ACTION STATUS UPDATE TESTS")
        print("=" * 80)
        
        try:
            await test_scheduled_action_status_updates()
            await test_failure_case()
            
            print("\n" + "=" * 80)
            print("🎉 ALL TESTS PASSED! Farcaster scheduled action fix is working!")
            print("=" * 80)
            
        except Exception as e:
            print(f"💥 TEST SUITE FAILED: {e}")
            import traceback
            traceback.print_exc()
            exit(1)
    
    asyncio.run(run_all_tests())
