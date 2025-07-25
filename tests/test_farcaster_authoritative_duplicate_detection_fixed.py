"""
Tests for authoritative duplicate detection in SendFarcasterReplyTool.
"""
import pytest
import time
from unittest.mock import AsyncMock, MagicMock
from chatbot.tools.farcaster_tools import SendFarcasterReplyTool
from chatbot.tools.base import ActionContext


def create_mock_world_state_manager(has_replied=False, is_bot_cast=False, was_last_to_reply=False):
    """Create a properly mocked WorldStateManager for testing."""
    mock_world_state = MagicMock()
    mock_world_state.has_replied_to_cast.return_value = has_replied
    mock_world_state.is_bot_cast.return_value = is_bot_cast
    mock_world_state.was_last_to_reply_in_thread.return_value = was_last_to_reply
    mock_world_state.add_action_result = MagicMock()
    mock_world_state.state = MagicMock()
    mock_world_state.state.farcaster_reply_state = MagicMock()
    
    # Ensure no atomic_reply_to_cast to force fallback path
    def mock_hasattr(obj, name):
        if name == 'atomic_reply_to_cast':
            return False
        return original_hasattr(obj, name)
    
    import builtins
    original_hasattr = builtins.hasattr
    # We can't easily patch hasattr, so instead we explicitly make it not available
    mock_world_state.atomic_reply_to_cast = None
    mock_world_state.spec = ['has_replied_to_cast', 'is_bot_cast', 'was_last_to_reply_in_thread', 'add_action_result', 'state']
    
    return mock_world_state


@pytest.mark.asyncio
async def test_reply_succeeds_when_no_prior_reply_exists():
    """Test that reply succeeds when no prior reply exists in the conversation thread."""
    tool = SendFarcasterReplyTool()
    
    # Mock Farcaster observer and API client
    mock_obs = AsyncMock()
    mock_api_client = AsyncMock()
    mock_obs.api_client = mock_api_client
    mock_obs.bot_fid = "12345"
    mock_obs.reply_to_cast.return_value = {"success": True, "cast": {"hash": "new_reply_hash"}}
    
    # Mock conversation lookup - no existing replies from bot
    mock_api_client.lookup_cast_conversation.return_value = {
        "result": {
            "conversation": {
                "cast": {
                    "direct_replies": [
                        {
                            "author": {"fid": "67890"},  # Different FID
                            "text": "Someone else's reply"
                        }
                    ]
                },
                "casts": []
            }
        }
    }
    
    # Mock cast details lookup for thread context
    mock_api_client.lookup_cast_by_hash.return_value = {
        "result": {
            "cast": {
                "hash": "test_cast_hash",
                "thread_hash": "thread123"
            }
        }
    }
    
    # Mock world state manager
    mock_world_state = create_mock_world_state_manager()
    
    context = ActionContext(
        farcaster_observer=mock_obs,
        world_state_manager=mock_world_state
    )
    
    params = {
        "content": "This is a test reply",
        "reply_to_hash": "test_cast_hash"
    }
    
    result = await tool.execute(params, context)
    
    # Should proceed and call reply_to_cast
    assert result["status"] == "success"
    mock_api_client.lookup_cast_conversation.assert_awaited_once_with("test_cast_hash")
    mock_obs.reply_to_cast.assert_awaited_once_with("This is a test reply", "test_cast_hash")


@pytest.mark.asyncio 
async def test_reply_is_skipped_when_reply_exists_in_direct_replies():
    """Test that reply is skipped when bot's reply already exists in direct_replies."""
    tool = SendFarcasterReplyTool()
    
    # Mock Farcaster observer and API client
    mock_obs = AsyncMock()
    mock_api_client = AsyncMock()
    mock_obs.api_client = mock_api_client
    mock_obs.bot_fid = "12345"
    
    # Mock conversation lookup - bot already replied
    mock_api_client.lookup_cast_conversation.return_value = {
        "result": {
            "conversation": {
                "cast": {
                    "direct_replies": [
                        {
                            "author": {"fid": "12345"},  # Bot's FID
                            "text": "Bot's existing reply"
                        },
                        {
                            "author": {"fid": "67890"},  # Different FID
                            "text": "Someone else's reply"
                        }
                    ]
                },
                "casts": []
            }
        }
    }
    
    # Mock cast details lookup for thread context
    mock_api_client.lookup_cast_by_hash.return_value = {
        "result": {
            "cast": {
                "hash": "test_cast_hash",
                "thread_hash": "thread123"
            }
        }
    }
    
    # Mock world state manager
    mock_world_state = create_mock_world_state_manager(has_replied=False)  # Internal state doesn't know
    
    context = ActionContext(
        farcaster_observer=mock_obs,
        world_state_manager=mock_world_state
    )
    
    params = {
        "content": "This would be a duplicate reply",
        "reply_to_hash": "test_cast_hash"
    }
    
    result = await tool.execute(params, context)
    
    # Should be skipped and NOT call reply_to_cast
    assert result["status"] == "skipped"
    assert "Duplicate reply already exists" in result["message"]
    mock_api_client.lookup_cast_conversation.assert_awaited_once_with("test_cast_hash")
    mock_obs.reply_to_cast.assert_not_awaited()
    
    # Should update internal state to correct the drift
    mock_world_state.add_action_result.assert_called_once()


@pytest.mark.asyncio
async def test_reply_is_skipped_when_reply_exists_in_casts():
    """Test that reply is skipped when bot's reply already exists in casts array."""
    tool = SendFarcasterReplyTool()
    
    # Mock Farcaster observer and API client
    mock_obs = AsyncMock()
    mock_api_client = AsyncMock()
    mock_obs.api_client = mock_api_client
    mock_obs.bot_fid = "12345"
    
    # Mock conversation lookup - bot already replied in casts array
    mock_api_client.lookup_cast_conversation.return_value = {
        "result": {
            "conversation": {
                "cast": {
                    "direct_replies": []
                },
                "casts": [
                    {
                        "author": {"fid": "67890"},  # Different FID
                        "text": "Someone else's reply"
                    },
                    {
                        "author": {"fid": "12345"},  # Bot's FID
                        "text": "Bot's existing reply"
                    }
                ]
            }
        }
    }
    
    # Mock cast details lookup for thread context
    mock_api_client.lookup_cast_by_hash.return_value = {
        "result": {
            "cast": {
                "hash": "test_cast_hash",
                "thread_hash": "thread123"
            }
        }
    }
    
    # Mock world state manager
    mock_world_state = create_mock_world_state_manager(has_replied=False)
    
    context = ActionContext(
        farcaster_observer=mock_obs,
        world_state_manager=mock_world_state
    )
    
    params = {
        "content": "This would be a duplicate reply",
        "reply_to_hash": "test_cast_hash"
    }
    
    result = await tool.execute(params, context)
    
    # Should be skipped and NOT call reply_to_cast
    assert result["status"] == "skipped"
    assert "Duplicate reply already exists" in result["message"]
    mock_obs.reply_to_cast.assert_not_awaited()


@pytest.mark.asyncio
async def test_reply_proceeds_if_thread_check_fails():
    """Test that reply proceeds if the authoritative thread check fails."""
    tool = SendFarcasterReplyTool()
    
    # Mock Farcaster observer and API client
    mock_obs = AsyncMock()
    mock_api_client = AsyncMock()
    mock_obs.api_client = mock_api_client
    mock_obs.bot_fid = "12345"
    mock_obs.reply_to_cast.return_value = {"success": True, "cast": {"hash": "new_reply_hash"}}
    
    # Mock conversation lookup to raise an exception
    mock_api_client.lookup_cast_conversation.side_effect = Exception("API Error")
    
    # Mock cast details lookup for thread context to also raise exception
    mock_api_client.lookup_cast_by_hash.side_effect = Exception("API Error")
    
    # Mock world state manager
    mock_world_state = create_mock_world_state_manager(has_replied=False)
    
    context = ActionContext(
        farcaster_observer=mock_obs,
        world_state_manager=mock_world_state
    )
    
    params = {
        "content": "This is a test reply",
        "reply_to_hash": "test_cast_hash"
    }
    
    result = await tool.execute(params, context)
    
    # Should proceed despite the API error (fail-open strategy)
    assert result["status"] == "success"
    mock_api_client.lookup_cast_conversation.assert_awaited_once_with("test_cast_hash")
    mock_obs.reply_to_cast.assert_awaited_once_with("This is a test reply", "test_cast_hash")


@pytest.mark.asyncio
async def test_reply_skipped_by_internal_check_skips_authoritative_check():
    """Test that if internal check already blocks the reply, authoritative check is not performed."""
    tool = SendFarcasterReplyTool()
    
    # Mock Farcaster observer and API client
    mock_obs = AsyncMock()
    mock_api_client = AsyncMock()
    mock_obs.api_client = mock_api_client
    mock_obs.bot_fid = "12345"
    
    # Mock world state manager - internal check blocks
    mock_world_state = create_mock_world_state_manager(has_replied=True)  # Internal state knows about reply
    
    context = ActionContext(
        farcaster_observer=mock_obs,
        world_state_manager=mock_world_state
    )
    
    params = {
        "content": "This would be a duplicate reply",
        "reply_to_hash": "test_cast_hash"
    }
    
    result = await tool.execute(params, context)
    
    # Should be blocked by internal check
    assert result["status"] == "skipped"
    assert "Already replied to cast" in result["error"]
    
    # Authoritative check should NOT be performed
    mock_api_client.lookup_cast_conversation.assert_not_awaited()
    mock_obs.reply_to_cast.assert_not_awaited()


@pytest.mark.asyncio
async def test_authoritative_check_handles_missing_bot_fid():
    """Test that authoritative check handles missing bot FID gracefully."""
    tool = SendFarcasterReplyTool()
    
    # Mock Farcaster observer and API client
    mock_obs = AsyncMock()
    mock_api_client = AsyncMock()
    mock_obs.api_client = mock_api_client
    mock_obs.bot_fid = None  # Missing bot FID
    mock_obs.reply_to_cast.return_value = {"success": True, "cast": {"hash": "new_reply_hash"}}
    
    # Mock world state manager
    mock_world_state = create_mock_world_state_manager(has_replied=False)
    
    context = ActionContext(
        farcaster_observer=mock_obs,
        world_state_manager=mock_world_state
    )
    
    params = {
        "content": "This is a test reply",
        "reply_to_hash": "test_cast_hash"
    }
    
    result = await tool.execute(params, context)
    
    # Should proceed despite missing bot FID
    assert result["status"] == "success"
    mock_obs.reply_to_cast.assert_awaited_once_with("This is a test reply", "test_cast_hash")


@pytest.mark.asyncio
async def test_authoritative_check_handles_malformed_api_response():
    """Test that authoritative check handles malformed API responses gracefully."""
    tool = SendFarcasterReplyTool()
    
    # Mock Farcaster observer and API client
    mock_obs = AsyncMock()
    mock_api_client = AsyncMock()
    mock_obs.api_client = mock_api_client
    mock_obs.bot_fid = "12345"
    mock_obs.reply_to_cast.return_value = {"success": True, "cast": {"hash": "new_reply_hash"}}
    
    # Mock conversation lookup with malformed response
    mock_api_client.lookup_cast_conversation.return_value = {
        "malformed": "response"  # Missing expected structure
    }
    
    # Mock cast details lookup for thread context
    mock_api_client.lookup_cast_by_hash.return_value = {
        "result": {
            "cast": {
                "hash": "test_cast_hash",
                "thread_hash": "thread123"
            }
        }
    }
    
    # Mock world state manager
    mock_world_state = create_mock_world_state_manager(has_replied=False)
    
    context = ActionContext(
        farcaster_observer=mock_obs,
        world_state_manager=mock_world_state
    )
    
    params = {
        "content": "This is a test reply", 
        "reply_to_hash": "test_cast_hash"
    }
    
    result = await tool.execute(params, context)
    
    # Should proceed despite malformed response
    assert result["status"] == "success"
    mock_obs.reply_to_cast.assert_awaited_once_with("This is a test reply", "test_cast_hash")
