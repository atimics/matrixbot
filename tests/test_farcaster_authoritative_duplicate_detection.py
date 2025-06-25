"""
Tests for authoritative duplicate detection in SendFarcasterPostTool (reply functionality).
"""
import pytest
import time
from unittest.mock import AsyncMock, MagicMock
from chatbot.tools.farcaster import SendFarcasterPostTool
from chatbot.tools.base import ActionContext


@pytest.mark.asyncio
async def test_reply_succeeds_when_no_prior_reply_exists():
    """Test that reply succeeds when no prior reply exists in action history."""
    tool = SendFarcasterPostTool()
    
    # Mock Farcaster observer
    mock_obs = AsyncMock()
    mock_obs.reply_to_cast = AsyncMock(return_value={"success": True, "cast": {"hash": "new_reply_hash"}})
    mock_obs.reply_queue = None  # No queue, so it uses immediate execution
    
    # Mock world state manager - no previous reply in action history
    mock_world_state = MagicMock()
    mock_world_state.has_replied_to_cast.return_value = False
    mock_world_state.is_bot_turn_in_thread.return_value = True
    
    # Mock service registry
    mock_service_registry = MagicMock()
    mock_service_registry.get_service.return_value = mock_obs
    
    context = ActionContext(
        service_registry=mock_service_registry,
        world_state_manager=mock_world_state
    )
    
    params = {
        "content": "This is a test reply",
        "reply_to_hash": "test_cast_hash"
    }
    
    result = await tool.execute(params, context)
    
    # Should proceed and call reply_to_cast
    assert result["status"] == "success"
    mock_obs.reply_to_cast.assert_awaited_once_with("This is a test reply", "test_cast_hash")


@pytest.mark.asyncio 
async def test_reply_is_blocked_when_reply_exists_in_action_history():
    """Test that reply is blocked when bot's reply already exists in action history."""
    tool = SendFarcasterPostTool()
    
    # Mock Farcaster observer
    mock_obs = AsyncMock()
    
    # Mock world state manager - action history shows previous reply
    mock_world_state = MagicMock()
    mock_world_state.has_replied_to_cast.return_value = True  # Action history knows about the reply
    
    # Mock service registry
    mock_service_registry = MagicMock()
    mock_service_registry.get_service.return_value = mock_obs
    
    context = ActionContext(
        service_registry=mock_service_registry,
        world_state_manager=mock_world_state
    )
    
    params = {
        "content": "This would be a duplicate reply",
        "reply_to_hash": "test_cast_hash"
    }
    
    result = await tool.execute(params, context)
    
    # Should be blocked by action history check and NOT call reply_to_cast
    assert result["status"] == "failure"
    assert "DUPLICATE ACTION BLOCKED" in result["error"]
    mock_obs.reply_to_cast.assert_not_awaited()


@pytest.mark.asyncio
async def test_reply_with_scheduled_queue():
    """Test that reply works correctly when using the scheduled queue."""
    tool = SendFarcasterPostTool()
    
    # Mock Farcaster observer with reply queue
    mock_obs = AsyncMock()
    import asyncio
    mock_queue = asyncio.Queue()  # Use a real queue
    mock_obs.reply_queue = mock_queue
    mock_obs.schedule_reply = MagicMock()
    
    # Mock world state manager
    mock_world_state = MagicMock()
    mock_world_state.has_replied_to_cast.return_value = False
    mock_world_state.is_bot_turn_in_thread.return_value = True
    mock_world_state.add_action_result.return_value = "test_action_id"
    
    # Mock service registry
    mock_service_registry = MagicMock()
    mock_service_registry.get_service.return_value = mock_obs
    
    context = ActionContext(
        service_registry=mock_service_registry,
        world_state_manager=mock_world_state
    )
    
    params = {
        "content": "This is a scheduled reply",
        "reply_to_hash": "test_cast_hash"
    }
    
    result = await tool.execute(params, context)
    
    # Should be scheduled successfully
    assert result["status"] == "scheduled"
    assert "test_cast_hash" in result["message"]
    mock_obs.schedule_reply.assert_called_once_with("This is a scheduled reply", "test_cast_hash", "test_action_id")


@pytest.mark.asyncio
async def test_reply_is_blocked_when_not_bot_turn():
    """Test that reply is blocked when it's not the bot's turn in the thread."""
    tool = SendFarcasterPostTool()
    
    # Mock Farcaster observer
    mock_obs = AsyncMock()
    
    # Mock world state manager - no duplicate but not bot's turn
    mock_world_state = MagicMock()
    mock_world_state.has_replied_to_cast.return_value = False  # No previous reply
    mock_world_state.is_bot_turn_in_thread.return_value = False  # Not bot's turn
    
    # Mock service registry
    mock_service_registry = MagicMock()
    mock_service_registry.get_service.return_value = mock_obs
    
    context = ActionContext(
        service_registry=mock_service_registry,
        world_state_manager=mock_world_state
    )
    
    params = {
        "content": "This reply should be blocked",
        "reply_to_hash": "test_cast_hash"
    }
    
    result = await tool.execute(params, context)
    
    # Should be blocked by thread turn validation
    assert result["status"] == "blocked"
    assert result["reason"] == "not_bot_turn"
    mock_obs.reply_to_cast.assert_not_awaited()


@pytest.mark.asyncio
async def test_reply_succeeds_with_exception_handling():
    """Test that reply handles validation exceptions gracefully."""
    tool = SendFarcasterPostTool()
    
    # Mock Farcaster observer
    mock_obs = AsyncMock()
    
    # Mock world state manager that throws an exception during validation
    mock_world_state = MagicMock()
    mock_world_state.has_replied_to_cast.side_effect = Exception("Validation error")
    
    # Mock service registry
    mock_service_registry = MagicMock()
    mock_service_registry.get_service.return_value = mock_obs
    
    context = ActionContext(
        service_registry=mock_service_registry,
        world_state_manager=mock_world_state
    )
    
    params = {
        "content": "This is a test reply",
        "reply_to_hash": "test_cast_hash"
    }
    
    result = await tool.execute(params, context)
    
    # Should handle the exception gracefully
    assert result["status"] == "failure"
    assert "Internal error during reply validation" in result["error"]
    mock_obs.reply_to_cast.assert_not_awaited()


@pytest.mark.asyncio
async def test_reply_skipped_by_internal_check_skips_authoritative_check():
    """Test that if internal check already blocks the reply, no further processing occurs."""
    tool = SendFarcasterPostTool()
    
    # Mock Farcaster observer
    mock_obs = AsyncMock()
    
    # Mock world state manager - internal check blocks
    mock_world_state = MagicMock()
    mock_world_state.has_replied_to_cast.return_value = True  # Internal state knows about reply
    
    # Mock service registry
    mock_service_registry = MagicMock()
    mock_service_registry.get_service.return_value = mock_obs
    
    context = ActionContext(
        service_registry=mock_service_registry,
        world_state_manager=mock_world_state
    )
    
    params = {
        "content": "This would be a duplicate reply",
        "reply_to_hash": "test_cast_hash"
    }
    
    result = await tool.execute(params, context)
    
    # Should be blocked by internal check
    assert result["status"] == "failure"
    assert "DUPLICATE ACTION BLOCKED" in result["error"]
    
    # No further processing should occur
    mock_obs.reply_to_cast.assert_not_awaited()


@pytest.mark.asyncio
async def test_reply_works_with_missing_service_registry():
    """Test that appropriate error is returned when service registry is missing."""
    tool = SendFarcasterPostTool()
    
    # Mock world state manager
    mock_world_state = MagicMock()
    mock_world_state.has_replied_to_cast.return_value = False
    mock_world_state.is_bot_turn_in_thread.return_value = True
    
    # Context without service registry
    context = ActionContext(
        service_registry=None,
        world_state_manager=mock_world_state
    )
    
    params = {
        "content": "This is a test reply",
        "reply_to_hash": "test_cast_hash"
    }
    
    result = await tool.execute(params, context)
    
    # Should return error about missing Farcaster integration
    assert result["status"] == "failure"
    assert "Farcaster integration" in result["error"]


@pytest.mark.asyncio
async def test_reply_works_with_missing_world_state_manager():
    """Test that appropriate error is returned when world state manager is missing."""
    tool = SendFarcasterPostTool()
    
    # Mock Farcaster observer
    mock_obs = AsyncMock()
    
    # Mock service registry
    mock_service_registry = MagicMock()
    mock_service_registry.get_service.return_value = mock_obs
    
    # Context without world state manager
    context = ActionContext(
        service_registry=mock_service_registry,
        world_state_manager=None
    )
    
    params = {
        "content": "This is a test reply", 
        "reply_to_hash": "test_cast_hash"
    }
    
    result = await tool.execute(params, context)
    
    # Should return error about missing world state manager
    assert result["status"] == "failure"
    assert "world state manager not available" in result["error"]
