#!/usr/bin/env python3
"""
Integration test to verify the complete duplicate reply prevention flow.

This test simulates the real orchestrator flow to ensure that duplicate replies
are prevented even when the AI system tries to reply to the same cast multiple times.
"""

import asyncio
import logging
import time
from unittest.mock import AsyncMock, MagicMock
from chatbot.tools.farcaster_tools import SendFarcasterReplyTool
from chatbot.core.world_state import WorldStateManager
from chatbot.tools.base import ActionContext

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_orchestrator_integration():
    """Test the complete flow from AI decision to tool execution with duplicate prevention."""
    
    print("🎭 Testing orchestrator-style integration with duplicate prevention...")
    
    # Create world state manager
    world_state = WorldStateManager()
    
    # Create mock farcaster observer with NO queue (immediate execution)
    mock_observer = AsyncMock()
    mock_observer.reply_queue = None  # Force immediate execution
    
    # Mock successful reply responses
    mock_observer.reply_to_cast.return_value = {
        "success": True,
        "cast": {
            "hash": "0x999newreply",
            "author": {"fid": 12345, "username": "testuser"},
            "text": "Thanks for the taco recommendation!"
        }
    }
    
    # Create action context
    context = ActionContext(
        farcaster_observer=mock_observer,
        world_state_manager=world_state
    )
    
    # Create tool
    reply_tool = SendFarcasterReplyTool()
    
    # Simulate the cast hash from logs (tacos conversation)
    target_cast_hash = "0x1735e7caa74a07b076c3e8a9a4b8284e1dc33cde"
    
    # Simulate first AI decision cycle - replies to tacos cast
    print(f"🤖 AI Cycle 1: Deciding to reply to taco cast {target_cast_hash}")
    
    reply_params_1 = {
        "content": "🌮 That new spot sounds fire! What's your go-to order? I'm always looking for good birria recommendations if they have it!",
        "reply_to_hash": target_cast_hash
    }
    
    result1 = await reply_tool.execute(reply_params_1, context)
    print(f"📊 Cycle 1 result: {result1['status']} - {result1.get('message', result1.get('error', 'No message'))}")
    
    # Verify first reply succeeded
    assert result1["status"] == "success", f"First reply should succeed, got {result1['status']}"
    assert len(world_state.state.action_history) == 1, "One action should be recorded"
    
    # Simulate second AI decision cycle - tries to reply to SAME cast again
    print(f"\n🤖 AI Cycle 2: Deciding to reply to SAME taco cast {target_cast_hash}")
    
    reply_params_2 = {
        "content": "🌮 That's some spicy intel! What's the must-try item? Al pastor? Carnitas? Need to taco-log this for my next food adventure!",
        "reply_to_hash": target_cast_hash  # SAME HASH as before
    }
    
    result2 = await reply_tool.execute(reply_params_2, context)
    print(f"📊 Cycle 2 result: {result2['status']} - {result2.get('message', result2.get('error', 'No message'))}")
    
    # Verify second reply was prevented
    assert result2["status"] == "failure", f"Second reply should fail, got {result2['status']}"
    assert "Already replied to cast" in result2["error"], "Error should indicate duplicate"
    assert len(world_state.state.action_history) == 1, "Action history should still have only one entry"
    
    # Verify API was only called once
    assert mock_observer.reply_to_cast.call_count == 1, f"API should be called only once, was called {mock_observer.reply_to_cast.call_count} times"
    
    print("✅ SUCCESS: Orchestrator integration test passed!")
    print("✅ The bot will no longer send duplicate replies to the same cast!")
    
    return True

async def test_scheduled_vs_immediate_consistency():
    """Test that both scheduled and immediate executions record actions consistently."""
    
    print("\n🎭 Testing scheduled vs immediate execution consistency...")
    
    # Test immediate execution (already tested above)
    world_state_immediate = WorldStateManager()
    mock_observer_immediate = AsyncMock()
    mock_observer_immediate.reply_queue = None  # Force immediate
    mock_observer_immediate.reply_to_cast.return_value = {"success": True, "cast": {"hash": "0xabc123"}}
    
    context_immediate = ActionContext(
        farcaster_observer=mock_observer_immediate,
        world_state_manager=world_state_immediate
    )
    
    reply_tool = SendFarcasterReplyTool()
    result_immediate = await reply_tool.execute({
        "content": "Immediate test",
        "reply_to_hash": "0ximmediate"
    }, context_immediate)
    
    assert result_immediate["status"] == "success", "Immediate execution should succeed"
    assert len(world_state_immediate.state.action_history) == 1, "Immediate should record action"
    
    # Test scheduled execution
    world_state_scheduled = WorldStateManager()
    
    # Create a proper queue mock to trigger scheduled path
    mock_queue = AsyncMock()
    mock_queue.__class__ = asyncio.Queue  # Make isinstance check pass
    
    mock_observer_scheduled = AsyncMock()
    mock_observer_scheduled.reply_queue = mock_queue  # Has queue (scheduled)
    mock_observer_scheduled.schedule_reply = MagicMock()
    
    context_scheduled = ActionContext(
        farcaster_observer=mock_observer_scheduled,
        world_state_manager=world_state_scheduled
    )
    
    result_scheduled = await reply_tool.execute({
        "content": "Scheduled test",
        "reply_to_hash": "0xscheduled"
    }, context_scheduled)
    
    assert result_scheduled["status"] == "scheduled", f"Scheduled execution should return scheduled, got {result_scheduled['status']}"
    assert len(world_state_scheduled.state.action_history) == 1, "Scheduled should record action"
    
    # Both should have actions recorded
    immediate_action = world_state_immediate.state.action_history[0]
    scheduled_action = world_state_scheduled.state.action_history[0]
    
    assert immediate_action.action_type == "send_farcaster_reply", "Immediate action type correct"
    assert scheduled_action.action_type == "send_farcaster_reply", "Scheduled action type correct"
    assert immediate_action.result == "success", "Immediate result correct"
    assert scheduled_action.result == "scheduled", "Scheduled result correct"
    
    print("✅ SUCCESS: Both scheduled and immediate executions record actions consistently!")
    
    return True

async def main():
    """Run all integration tests."""
    try:
        success1 = await test_orchestrator_integration()
        success2 = await test_scheduled_vs_immediate_consistency()
        
        if success1 and success2:
            print("\n🎉 All integration tests passed!")
            print("🚀 The duplicate reply bug has been fixed!")
            print("📝 Summary of changes:")
            print("   • Immediate tool executions now record actions in world state")
            print("   • has_replied_to_cast() now sees both scheduled and immediate executions") 
            print("   • Duplicate replies are prevented regardless of execution path")
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
