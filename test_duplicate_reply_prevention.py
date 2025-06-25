#!/usr/bin/env python3
"""
Test script to verify the duplicate reply prevention improvements.

This script demonstrates the enhanced duplicate reply prevention logic
that was implemented based on the engineering report recommendations.
"""

import asyncio
import logging
import time
from unittest.mock import Mock, AsyncMock

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_duplicate_reply_prevention():
    """
    Test the enhanced duplicate reply prevention logic.
    """
    print("🧪 Testing Enhanced Duplicate Reply Prevention Logic")
    print("=" * 60)
    
    # Import the tool
    from chatbot.tools.farcaster.send_post import SendFarcasterPostTool
    from chatbot.tools.base import ActionContext
    
    # Create a mock world state manager
    mock_world_state_manager = Mock()
    
    # Create a mock context
    mock_context = Mock(spec=ActionContext)
    mock_context.world_state_manager = mock_world_state_manager
    
    # Mock the service registry to return a farcaster observer
    mock_farcaster_observer = AsyncMock()
    mock_context.service_registry = Mock()
    mock_context.service_registry.get = Mock(return_value=mock_farcaster_observer)
    
    # Create the tool instance
    tool = SendFarcasterPostTool()
    
    # Test Case 1: Action history indicates duplicate (primary check)
    print("\n📋 Test Case 1: Action History Duplicate Detection")
    print("-" * 50)
    
    mock_world_state_manager.has_replied_to_cast.return_value = True
    mock_world_state_manager.is_bot_turn_in_thread.return_value = True
    
    params = {
        "content": "Test reply content",
        "reply_to_hash": "0x123abc"
    }
    
    async def run_test_case_1():
        result = await tool.execute(params, mock_context)
        print(f"Result: {result}")
        
        if result.get("status") == "error" and "DUPLICATE ACTION BLOCKED" in result.get("message", ""):
            print("✅ SUCCESS: Action history duplicate detection worked correctly")
            return True
        else:
            print("❌ FAILED: Action history duplicate detection failed")
            return False
    
    # Test Case 2: No duplicate in history, but thread validation fails
    print("\n📋 Test Case 2: Thread Turn Validation")
    print("-" * 50)
    
    mock_world_state_manager.has_replied_to_cast.return_value = False
    mock_world_state_manager.is_bot_turn_in_thread.return_value = False
    
    async def run_test_case_2():
        result = await tool.execute(params, mock_context)
        print(f"Result: {result}")
        
        if result.get("status") == "blocked" and result.get("reason") == "not_bot_turn":
            print("✅ SUCCESS: Thread turn validation worked correctly")
            return True
        else:
            print("❌ FAILED: Thread turn validation failed")
            return False
    
    # Test Case 3: Both checks pass, should proceed normally
    print("\n📋 Test Case 3: Normal Flow (Both Checks Pass)")
    print("-" * 50)
    
    mock_world_state_manager.has_replied_to_cast.return_value = False
    mock_world_state_manager.is_bot_turn_in_thread.return_value = True
    mock_world_state_manager.add_action_result.return_value = "test_action_id"
    
    # Mock the queue for scheduling
    mock_queue = AsyncMock()
    mock_farcaster_observer.reply_queue = mock_queue
    mock_farcaster_observer.schedule_reply = Mock()
    
    async def run_test_case_3():
        result = await tool.execute(params, mock_context)
        print(f"Result: {result}")
        
        if result.get("status") == "scheduled":
            print("✅ SUCCESS: Normal flow worked correctly")
            return True
        else:
            print("❌ FAILED: Normal flow failed")
            return False
    
    # Test Case 4: Exception handling during validation
    print("\n📋 Test Case 4: Exception Handling")
    print("-" * 50)
    
    mock_world_state_manager.has_replied_to_cast.side_effect = Exception("Test exception")
    
    async def run_test_case_4():
        result = await tool.execute(params, mock_context)
        print(f"Result: {result}")
        
        if result.get("status") == "error" and "Internal error during reply validation" in result.get("message", ""):
            print("✅ SUCCESS: Exception handling worked correctly")
            return True
        else:
            print("❌ FAILED: Exception handling failed")
            return False
    
    # Run all test cases
    async def run_all_tests():
        print("\n🚀 Running All Test Cases...")
        print("=" * 60)
        
        results = []
        results.append(await run_test_case_1())
        results.append(await run_test_case_2())
        
        # Reset the side effect for case 3
        mock_world_state_manager.has_replied_to_cast.side_effect = None
        results.append(await run_test_case_3())
        
        results.append(await run_test_case_4())
        
        print("\n📊 Test Results Summary")
        print("=" * 60)
        passed = sum(results)
        total = len(results)
        print(f"Passed: {passed}/{total}")
        
        if passed == total:
            print("🎉 All tests passed! The duplicate reply prevention is working correctly.")
        else:
            print("⚠️  Some tests failed. Please review the implementation.")
        
        return passed == total
    
    return asyncio.run(run_all_tests())

if __name__ == "__main__":
    try:
        success = test_duplicate_reply_prevention()
        exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Test execution failed: {e}")
        exit(1)
