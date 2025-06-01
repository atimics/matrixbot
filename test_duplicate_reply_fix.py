#!/usr/bin/env python3
"""
Test to verify the duplicate reply prevention fix.

This test ensures that immediate executions are properly recorded in the action history
to prevent duplicate replies to the same cast.
"""

import asyncio
import logging
from unittest.mock import AsyncMock
from chatbot.tools.farcaster_tools import SendFarcasterReplyTool
from chatbot.core.world_state import WorldStateManager
from chatbot.tools.base import ActionContext

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_duplicate_reply_prevention():
    """Test that duplicate replies are prevented after immediate execution."""
    
    print("🧪 Testing duplicate reply prevention after immediate execution...")
    
    # Create world state manager
    world_state = WorldStateManager()
    
    # Create mock farcaster observer
    mock_observer = AsyncMock()
    mock_observer.reply_queue = None  # Force immediate execution
    
    # Mock successful reply
    mock_observer.reply_to_cast.return_value = {
        "success": True,
        "cast": {
            "hash": "0x123abc456def",
            "author": {"fid": 12345},
            "text": "Test reply content"
        }
    }
    
    # Create action context
    context = ActionContext(
        farcaster_observer=mock_observer,
        world_state_manager=world_state
    )
    
    # Create tool
    reply_tool = SendFarcasterReplyTool()
    
    test_cast_hash = "0x789original123"
    reply_params = {
        "content": "This is a test reply",
        "reply_to_hash": test_cast_hash
    }
    
    # First reply should succeed
    print(f"🎯 Sending first reply to cast {test_cast_hash}...")
    result1 = await reply_tool.execute(reply_params, context)
    
    print(f"📊 First reply result: {result1}")
    assert result1["status"] == "success", f"First reply should succeed, got {result1['status']}"
    
    # Check that action was recorded
    print(f"📊 Action history count: {len(world_state.state.action_history)}")
    assert len(world_state.state.action_history) == 1, "One action should be recorded"
    
    action = world_state.state.action_history[0]
    print(f"📊 Recorded action: {action.action_type}, result: {action.result}, params: {action.parameters}")
    assert action.action_type == "send_farcaster_reply", "Action type should be send_farcaster_reply"
    assert action.result == "success", "Action result should be success"
    assert action.parameters["reply_to_hash"] == test_cast_hash, "Reply hash should match"
    
    # Check has_replied_to_cast
    has_replied = world_state.has_replied_to_cast(test_cast_hash)
    print(f"📊 has_replied_to_cast check: {has_replied}")
    assert has_replied, "has_replied_to_cast should return True after successful reply"
    
    # Second reply to same cast should be prevented
    print(f"🚫 Attempting second reply to same cast {test_cast_hash}...")
    result2 = await reply_tool.execute(reply_params, context)
    
    print(f"📊 Second reply result: {result2}")
    assert result2["status"] == "failure", f"Second reply should fail, got {result2['status']}"
    assert "Already replied to cast" in result2["error"], "Error message should indicate duplicate reply"
    
    # Action history should still be 1 (no new action added for the failed attempt)
    print(f"📊 Final action history count: {len(world_state.state.action_history)}")
    assert len(world_state.state.action_history) == 1, "Action history should still have only one entry"
    
    print("✅ SUCCESS: Duplicate reply prevention is working correctly!")
    return True

async def test_different_casts_allowed():
    """Test that replies to different casts are still allowed."""
    
    print("\n🧪 Testing replies to different casts...")
    
    # Create world state manager
    world_state = WorldStateManager()
    
    # Create mock farcaster observer
    mock_observer = AsyncMock()
    mock_observer.reply_queue = None  # Force immediate execution
    
    # Mock successful reply
    mock_observer.reply_to_cast.return_value = {
        "success": True,
        "cast": {
            "hash": "0x123abc456def",
            "author": {"fid": 12345},
            "text": "Test reply content"
        }
    }
    
    # Create action context
    context = ActionContext(
        farcaster_observer=mock_observer,
        world_state_manager=world_state
    )
    
    # Create tool
    reply_tool = SendFarcasterReplyTool()
    
    # Reply to first cast
    result1 = await reply_tool.execute({
        "content": "Reply to first cast",
        "reply_to_hash": "0x111first"
    }, context)
    
    assert result1["status"] == "success", "First reply should succeed"
    
    # Reply to second cast should also succeed
    result2 = await reply_tool.execute({
        "content": "Reply to second cast", 
        "reply_to_hash": "0x222second"
    }, context)
    
    assert result2["status"] == "success", "Second reply to different cast should succeed"
    
    # Should have two actions recorded
    assert len(world_state.state.action_history) == 2, "Two actions should be recorded"
    
    print("✅ SUCCESS: Replies to different casts are allowed!")
    return True

async def main():
    """Run all tests."""
    try:
        success1 = await test_duplicate_reply_prevention()
        success2 = await test_different_casts_allowed()
        
        if success1 and success2:
            print("\n🎉 All duplicate reply prevention tests passed!")
            return True
        else:
            print("\n❌ Some tests failed!")
            return False
    except Exception as e:
        print(f"\n💥 Test failed with exception: {e}")
        logger.exception("Test failure")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    if not success:
        exit(1)
