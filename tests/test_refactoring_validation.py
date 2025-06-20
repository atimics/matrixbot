"""
Test script for validating the refactored tool architecture.

This script tests the key improvements made in the refactoring:
1. Service-oriented tool execution
2. ActionExecutor integration
3. Explicit media chaining with media_id
4. Deprecation warnings for direct observer access
"""

import asyncio
import logging
import warnings
from unittest.mock import AsyncMock, MagicMock

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_service_oriented_execution():
    """Test that tools use service-oriented approach"""
    print("\n=== Testing Service-Oriented Tool Execution ===")
    
    # Mock service registry and services
    mock_service_registry = MagicMock()
    mock_farcaster_service = AsyncMock()
    mock_farcaster_service.is_available.return_value = True
    mock_farcaster_service.create_post.return_value = {
        "status": "success",
        "message": "Post created successfully",
        "cast_hash": "0x123abc"
    }
    
    mock_service_registry.get_social_service.return_value = mock_farcaster_service
    
    # Create ActionContext with service registry
    from chatbot.tools.base import ActionContext
    context = ActionContext(service_registry=mock_service_registry)
    
    # Test SendFarcasterPostTool
    from chatbot.tools.farcaster_tools import SendFarcasterPostTool
    tool = SendFarcasterPostTool()
    
    params = {
        "content": "Test post from refactored architecture!"
    }
    
    result = await tool.execute(params, context)
    print(f"SendFarcasterPostTool result: {result}")
    
    # Verify service was called
    mock_farcaster_service.create_post.assert_called_once()
    assert result["status"] == "success"
    print("✅ Service-oriented execution working correctly")


async def test_media_chaining():
    """Test explicit media chaining with media_id"""
    print("\n=== Testing Explicit Media Chaining ===")
    
    # Mock world state manager
    mock_world_state = MagicMock()
    mock_world_state.get_media_url_by_id.return_value = "https://arweave.net/test-image-url"
    
    # Mock service registry
    mock_service_registry = MagicMock()
    mock_farcaster_service = AsyncMock()
    mock_farcaster_service.is_available.return_value = True
    mock_farcaster_service.create_post.return_value = {
        "status": "success", 
        "message": "Post with media created"
    }
    mock_service_registry.get_social_service.return_value = mock_farcaster_service
    
    # Create context
    from chatbot.tools.base import ActionContext
    context = ActionContext(
        service_registry=mock_service_registry,
        world_state_manager=mock_world_state
    )
    
    # Test posting with media_id
    from chatbot.tools.farcaster_tools import SendFarcasterPostTool
    tool = SendFarcasterPostTool()
    
    params = {
        "content": "Check out this generated image!",
        "media_id": "media_img_123456"
    }
    
    result = await tool.execute(params, context)
    print(f"Post with media_id result: {result}")
    
    # Verify media was resolved
    mock_world_state.get_media_url_by_id.assert_called_with("media_img_123456")
    
    # Verify service was called with resolved URL
    call_args = mock_farcaster_service.create_post.call_args
    assert "https://arweave.net/test-image-url" in call_args[1]["embed_urls"]
    print("✅ Media chaining working correctly")


def test_deprecation_warnings():
    """Test that deprecation warnings are issued for direct observer access"""
    print("\n=== Testing Deprecation Warnings ===")
    
    from chatbot.tools.base import ActionContext
    
    # Create context with observers
    mock_matrix_observer = MagicMock()
    mock_farcaster_observer = MagicMock()
    
    context = ActionContext(
        matrix_observer=mock_matrix_observer,
        farcaster_observer=mock_farcaster_observer
    )
    
    # Capture warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        
        # Access deprecated properties
        _ = context.matrix_observer
        _ = context.farcaster_observer
        
        # Check warnings were issued
        assert len(w) == 2
        assert issubclass(w[0].category, DeprecationWarning)
        assert issubclass(w[1].category, DeprecationWarning)
        assert "get_messaging_service" in str(w[0].message)
        assert "get_social_service" in str(w[1].message)
        
    print("✅ Deprecation warnings working correctly")


async def test_action_executor():
    """Test ActionExecutor functionality"""
    print("\n=== Testing ActionExecutor ===")
    
    # Mock tool registry
    from chatbot.tools.registry import ToolRegistry
    from chatbot.core.orchestration.action_executor import ActionExecutor, ActionPlan
    
    tool_registry = ToolRegistry()
    
    # Create a simple mock tool
    mock_tool = MagicMock()
    mock_tool.name = "test_tool"
    mock_tool.parameters_schema = {"required": ["param1"]}
    mock_tool.execute = AsyncMock(return_value={"status": "success", "message": "Mock executed"})
    
    tool_registry.register_tool(mock_tool)
    
    # Create ActionExecutor
    executor = ActionExecutor(tool_registry)
    
    # Create ActionPlan
    action_plan = ActionPlan("test_tool", {"param1": "value1"})
    
    # Mock context
    mock_context = MagicMock()
    
    # Execute action
    result = await executor.execute_action(action_plan, mock_context)
    
    print(f"ActionExecutor result: {result}")
    
    # Verify execution
    assert result["status"] == "success"
    assert result["tool_name"] == "test_tool"
    assert "execution_time" in result
    
    mock_tool.execute.assert_called_once_with({"param1": "value1"}, mock_context)
    print("✅ ActionExecutor working correctly")


async def main():
    """Run all validation tests"""
    print("Starting Chatbot Architecture Refactoring Validation Tests")
    print("=" * 60)
    
    try:
        await test_service_oriented_execution()
        await test_media_chaining()
        test_deprecation_warnings()
        await test_action_executor()
        
        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED! Refactoring validation successful.")
        print("\nKey improvements validated:")
        print("• Service-oriented tool execution")
        print("• Explicit media chaining with media_id")
        print("• Deprecation warnings for old patterns")
        print("• Centralized ActionExecutor")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
