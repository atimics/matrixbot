"""
Tests for authoritative duplicate detection in SendFarcasterReplyTool.
"""
import pytest
import time
from unittest.mock import AsyncMock, MagicMock
from chatbot.tools.farcaster_tools import SendFarcasterReplyTool
from chatbot.tools.base import ActionContext


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
    
    # Mock world state manager
    mock_world_state = MagicMock()
    mock_world_state.has_replied_to_cast.return_value = False
    
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
    
    # Mock world state manager
    mock_world_state = MagicMock()
    mock_world_state.has_replied_to_cast.return_value = False  # Internal state doesn't know
    
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
    """Test that reply is skipped when bot's reply exists in the casts array."""
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
    
    # Mock world state manager
    mock_world_state = MagicMock()
    mock_world_state.has_replied_to_cast.return_value = False  # Internal state doesn't know
    
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
    
    # Mock world state manager
    mock_world_state = MagicMock()
    mock_world_state.has_replied_to_cast.return_value = False
    
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
    mock_world_state = MagicMock()
    mock_world_state.has_replied_to_cast.return_value = True  # Internal state knows about reply
    
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
    assert result["status"] == "failure"
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
    mock_world_state = MagicMock()
    mock_world_state.has_replied_to_cast.return_value = False
    
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
    
    # Mock world state manager
    mock_world_state = MagicMock()
    mock_world_state.has_replied_to_cast.return_value = False
    
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
    mock_api_client.lookup_cast_conversation.assert_awaited_once_with("test_cast_hash")
    mock_obs.reply_to_cast.assert_awaited_once_with("This is a test reply", "test_cast_hash")
