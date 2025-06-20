#!/usr/bin/env python3
"""
Test script to verify the GetTrendingCastsTool fix.
"""

import asyncio
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chatbot.tools.farcaster.discovery_tools import GetTrendingCastsTool
from chatbot.tools.base import ActionContext
from unittest.mock import AsyncMock, MagicMock


async def test_get_trending_casts_tool():
    """Test that the GetTrendingCastsTool can be instantiated and called."""
    
    # Create a mock context with farcaster_observer
    mock_context = MagicMock(spec=ActionContext)
    mock_context.farcaster_observer = AsyncMock()
    mock_context.world_state_manager = None
    
    # Mock the get_trending_casts method to return success
    mock_context.farcaster_observer.get_trending_casts.return_value = {
        "success": True,
        "casts": [
            {
                "id": "test_cast_123",
                "content": "This is a test trending cast",
                "sender_username": "test_user",
                "timestamp": 1640995200,
                "metadata": {
                    "reactions": {
                        "likes_count": 5,
                        "recasts_count": 2
                    },
                    "replies_count": 1
                }
            }
        ],
        "error": None
    }
    
    # Create the tool
    tool = GetTrendingCastsTool()
    
    # Test tool properties
    assert tool.name == "get_trending_casts"
    assert "trending" in tool.description.lower()
    
    # Test execution
    params = {"timeframe_hours": 24, "limit": 10}
    result = await tool.execute(params, mock_context)
    
    # Verify the result
    assert result["status"] == "success"
    assert "casts" in result
    assert len(result["casts"]) == 1
    assert result["casts"][0]["id"] == "test_cast_123"
    
    # Verify the mock was called correctly
    mock_context.farcaster_observer.get_trending_casts.assert_called_once_with(
        channel_id=None, timeframe_hours=24, limit=10
    )
    
    print("✅ GetTrendingCastsTool test passed!")


if __name__ == "__main__":
    asyncio.run(test_get_trending_casts_tool())
