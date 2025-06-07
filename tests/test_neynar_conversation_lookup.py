"""
Tests for the new lookup_cast_conversation method in NeynarAPIClient.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from chatbot.integrations.farcaster.neynar_api_client import NeynarAPIClient


@pytest.mark.asyncio
async def test_lookup_cast_conversation_success():
    """Test that lookup_cast_conversation calls the correct API endpoint."""
    # Create a client with a mock HTTP client
    client = NeynarAPIClient(api_key="test_key", signer_uuid="test_uuid", bot_fid="12345")
    
    # Mock the HTTP client and response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "result": {
            "conversation": {
                "cast": {
                    "direct_replies": []
                },
                "casts": []
            }
        }
    }
    
    # Mock the _make_request method
    client._make_request = AsyncMock(return_value=mock_response)
    
    # Call the method
    result = await client.lookup_cast_conversation("test_cast_hash")
    
    # Verify the correct API call was made
    client._make_request.assert_awaited_once_with(
        "GET",
        "/farcaster/cast/conversation",
        params={
            "type": "hash",
            "identifier": "test_cast_hash",
            "reply_depth": 5,
            "include_chronological_parent_casts": False
        }
    )
    
    # Verify the response
    assert result == mock_response.json.return_value


@pytest.mark.asyncio
async def test_lookup_cast_conversation_strips_whitespace():
    """Test that lookup_cast_conversation strips whitespace from cast hash."""
    # Create a client with a mock HTTP client
    client = NeynarAPIClient(api_key="test_key", signer_uuid="test_uuid", bot_fid="12345")
    
    # Mock the HTTP client and response
    mock_response = MagicMock()
    mock_response.json.return_value = {"result": {"conversation": {}}}
    
    # Mock the _make_request method
    client._make_request = AsyncMock(return_value=mock_response)
    
    # Call the method with whitespace around the hash
    await client.lookup_cast_conversation("  test_cast_hash  ")
    
    # Verify whitespace was stripped
    client._make_request.assert_awaited_once_with(
        "GET",
        "/farcaster/cast/conversation",
        params={
            "type": "hash",
            "identifier": "test_cast_hash",  # Should be stripped
            "reply_depth": 5,
            "include_chronological_parent_casts": False
        }
    )


@pytest.mark.asyncio
async def test_lookup_cast_conversation_handles_api_error():
    """Test that lookup_cast_conversation properly propagates API errors."""
    # Create a client with a mock HTTP client
    client = NeynarAPIClient(api_key="test_key", signer_uuid="test_uuid", bot_fid="12345")
    
    # Mock the _make_request method to raise an exception
    client._make_request = AsyncMock(side_effect=Exception("API Error"))
    
    # Call the method and expect the exception to be raised
    with pytest.raises(Exception, match="API Error"):
        await client.lookup_cast_conversation("test_cast_hash")
