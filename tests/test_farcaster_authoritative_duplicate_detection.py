"""
Tests for authoritative duplicate detection in SendFarcasterPostTool (reply functionality).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from chatbot.tools.farcaster import SendFarcasterPostTool
from chatbot.tools.base import ActionContext


@pytest.mark.asyncio
async def test_reply_succeeds_when_no_prior_reply_exists():
    """Test that reply succeeds when no prior reply exists in persistent cache or API."""
    tool = SendFarcasterPostTool()
    
    # Mock Farcaster observer with API client
    mock_obs = AsyncMock()
    mock_obs.reply_to_cast = AsyncMock(return_value={"success": True, "cast": {"hash": "new_reply_hash"}})
    mock_obs.reply_queue = None  # No queue, so it uses immediate execution
    mock_obs.bot_fid = "12345"
    
    # Mock API client for authoritative check
    mock_api_client = AsyncMock()
    mock_api_client.lookup_cast_conversation = AsyncMock(return_value={
        "result": {
            "conversation": {
                "cast": {
                    "direct_replies": []  # No existing replies
                },
                "casts": []
            }
        }
    })
    mock_obs.api_client = mock_api_client
    
    # Mock database manager for persistent cache
    mock_db_manager = AsyncMock()
    mock_db_manager.has_replied_to = AsyncMock(return_value=False)
    mock_db_manager.add_replied_to_cast = AsyncMock()
    
    # Mock world state manager
    mock_world_state = MagicMock()
    mock_world_state.is_bot_turn_in_thread.return_value = True
    mock_world_state.has_replied_to_cast.return_value = False  # Internal state check passes
    
    # Mock service registry
    mock_service_registry = MagicMock()
    mock_service_registry.get_service.return_value = mock_obs
    
    context = ActionContext(
        service_registry=mock_service_registry,
        world_state_manager=mock_world_state,
        database_manager=mock_db_manager
    )
    
    params = {
        "content": "This is a test reply",
        "reply_to_hash": "test_cast_hash"
    }
    
    result = await tool.execute(params, context)
    
    # Should proceed and call reply_to_cast
    assert result["status"] == "success"
    mock_obs.reply_to_cast.assert_awaited_once_with("This is a test reply", "test_cast_hash")
    # Should check persistent cache
    mock_db_manager.has_replied_to.assert_awaited_once_with("test_cast_hash")
    # Should check API
    mock_api_client.lookup_cast_conversation.assert_awaited_once_with("test_cast_hash")
    # Should update cache after success
    mock_db_manager.add_replied_to_cast.assert_awaited_once_with("test_cast_hash", "new_reply_hash")


@pytest.mark.asyncio 
async def test_reply_is_blocked_by_persistent_cache():
    """Test that reply is blocked when bot's reply exists in persistent cache."""
    tool = SendFarcasterPostTool()
    
    # Mock database manager - cache shows previous reply
    mock_db_manager = AsyncMock()
    mock_db_manager.has_replied_to = AsyncMock(return_value=True)
    
    # Mock Farcaster observer
    mock_obs = AsyncMock()
    
    # Mock world state manager - internal state should return False to test persistent cache
    mock_world_state = MagicMock()
    mock_world_state.has_replied_to_cast.return_value = False  # Internal state check passes
    
    # Mock service registry
    mock_service_registry = MagicMock()
    mock_service_registry.get_service.return_value = mock_obs
    
    context = ActionContext(
        service_registry=mock_service_registry,
        world_state_manager=mock_world_state,
        database_manager=mock_db_manager
    )
    
    params = {
        "content": "This would be a duplicate reply",
        "reply_to_hash": "test_cast_hash"
    }
    
    result = await tool.execute(params, context)
    
    # Should be blocked by persistent cache check
    assert result["status"] == "failure"
    assert "Persistent cache indicates a reply" in result["error"]
    mock_obs.reply_to_cast.assert_not_awaited()
    mock_db_manager.has_replied_to.assert_awaited_once_with("test_cast_hash")


@pytest.mark.asyncio
async def test_reply_is_blocked_by_authoritative_api_check():
    """Test that reply is blocked when API shows existing reply from bot."""
    tool = SendFarcasterPostTool()
    
    # Mock Farcaster observer with API client
    mock_obs = AsyncMock()
    mock_obs.bot_fid = "12345"
    
    # Mock API client showing existing reply from bot
    mock_api_client = AsyncMock()
    mock_api_client.lookup_cast_conversation = AsyncMock(return_value={
        "result": {
            "conversation": {
                "cast": {
                    "direct_replies": [
                        {
                            "author": {"fid": "12345"},  # Bot's FID
                            "hash": "existing_reply_hash",
                            "text": "Bot's existing reply"
                        }
                    ]
                },
                "casts": []
            }
        }
    })
    mock_obs.api_client = mock_api_client
    
    # Mock database manager - cache doesn't know about reply
    mock_db_manager = AsyncMock()
    mock_db_manager.has_replied_to = AsyncMock(return_value=False)
    mock_db_manager.add_replied_to_cast = AsyncMock()
    
    # Mock world state manager
    mock_world_state = MagicMock()
    mock_world_state.has_replied_to_cast.return_value = False  # Allow API check
    
    # Mock service registry
    mock_service_registry = MagicMock()
    mock_service_registry.get_service.return_value = mock_obs
    
    context = ActionContext(
        service_registry=mock_service_registry,
        world_state_manager=mock_world_state,
        database_manager=mock_db_manager
    )
    
    params = {
        "content": "This would be a duplicate reply",
        "reply_to_hash": "test_cast_hash"
    }
    
    result = await tool.execute(params, context)
    
    # Should be blocked by authoritative API check
    assert result["status"] == "failure"
    assert "Authoritative API check found existing reply" in result["error"]
    mock_obs.reply_to_cast.assert_not_awaited()
    # Should update cache with discovered reply
    mock_db_manager.add_replied_to_cast.assert_awaited_once_with("test_cast_hash", "existing_reply_hash")


@pytest.mark.asyncio
async def test_reply_is_blocked_when_not_bot_turn():
    """Test that reply is blocked when it's not the bot's turn in the thread."""
    tool = SendFarcasterPostTool()
    
    # Mock Farcaster observer with API client
    mock_obs = AsyncMock()
    mock_obs.bot_fid = "12345"
    
    # Mock API client - no existing replies
    mock_api_client = AsyncMock()
    mock_api_client.lookup_cast_conversation = AsyncMock(return_value={
        "result": {
            "conversation": {
                "cast": {
                    "direct_replies": []  # No existing replies
                },
                "casts": []
            }
        }
    })
    mock_obs.api_client = mock_api_client
    
    # Mock database manager - no previous reply
    mock_db_manager = AsyncMock()
    mock_db_manager.has_replied_to = AsyncMock(return_value=False)
    
    # Mock world state manager - not bot's turn
    mock_world_state = MagicMock()
    mock_world_state.is_bot_turn_in_thread.return_value = False  # Not bot's turn
    
    # Mock service registry
    mock_service_registry = MagicMock()
    mock_service_registry.get_service.return_value = mock_obs
    
    context = ActionContext(
        service_registry=mock_service_registry,
        world_state_manager=mock_world_state,
        database_manager=mock_db_manager
    )
    
    params = {
        "content": "This reply should be blocked",
        "reply_to_hash": "test_cast_hash"
    }
    
    result = await tool.execute(params, context)
    
    # Should be blocked by thread turn validation (but authoritative check passes)
    # Note: With our new implementation, the bot might still proceed if authoritative check passes
    # but we'll log a warning about the thread turn issue
    assert result["status"] in ["blocked", "failure"] 
    mock_obs.reply_to_cast.assert_not_awaited()


@pytest.mark.asyncio
async def test_reply_handles_api_error_gracefully():
    """Test that reply handles API errors gracefully during authoritative check."""
    tool = SendFarcasterPostTool()
    
    # Mock Farcaster observer with API client that throws error
    mock_obs = AsyncMock()
    mock_obs.bot_fid = "12345"
    
    # Mock API client that throws exception
    mock_api_client = AsyncMock()
    mock_api_client.lookup_cast_conversation = AsyncMock(side_effect=Exception("API Error"))
    mock_obs.api_client = mock_api_client
    
    # Mock database manager - no previous reply
    mock_db_manager = AsyncMock()
    mock_db_manager.has_replied_to = AsyncMock(return_value=False)
    
    # Mock world state manager
    mock_world_state = MagicMock()
    mock_world_state.has_replied_to_cast.return_value = False  # Allow API check which will fail
    
    # Mock service registry
    mock_service_registry = MagicMock()
    mock_service_registry.get_service.return_value = mock_obs
    
    context = ActionContext(
        service_registry=mock_service_registry,
        world_state_manager=mock_world_state,
        database_manager=mock_db_manager
    )
    
    params = {
        "content": "This is a test reply",
        "reply_to_hash": "test_cast_hash"
    }
    
    result = await tool.execute(params, context)
    
    # Should handle the exception gracefully and fail safely
    assert result["status"] == "failure"
    assert "API error" in result["error"]
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
