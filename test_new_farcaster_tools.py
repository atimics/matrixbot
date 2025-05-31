#!/usr/bin/env python3
"""
Test script to verify new Farcaster like and quote cast functionality
"""

import asyncio
import logging
import time
from unittest.mock import AsyncMock, MagicMock

from chatbot.tools.farcaster_tools import LikeFarcasterPostTool, QuoteFarcasterPostTool
from chatbot.tools.base import ActionContext

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_like_tool():
    """Test the like Farcaster post tool"""
    # Create mock observer
    mock_observer = AsyncMock()
    mock_observer.like_cast.return_value = {
        "success": True,
        "cast_hash": "0x1234567890abcdef"
    }
    
    # Create action context
    context = ActionContext(
        farcaster_observer=mock_observer,
        matrix_observer=None,
        world_state_manager=None,
        context_manager=None
    )
    
    # Test the tool
    tool = LikeFarcasterPostTool()
    result = await tool.execute({
        "cast_hash": "0x1234567890abcdef"
    }, context)
    
    logger.info(f"Like tool result: {result}")
    assert result["status"] == "success"
    assert "Successfully liked" in result["message"]
    mock_observer.like_cast.assert_called_once_with("0x1234567890abcdef")


async def test_quote_tool():
    """Test the quote cast tool"""
    # Create mock observer
    mock_observer = AsyncMock()
    mock_observer.quote_cast.return_value = {
        "success": True,
        "cast_hash": "0xnewcast123",
        "quoted_cast": "0xoriginalcast456"
    }
    
    # Create action context
    context = ActionContext(
        farcaster_observer=mock_observer,
        matrix_observer=None,
        world_state_manager=None,
        context_manager=None
    )
    
    # Test the tool
    tool = QuoteFarcasterPostTool()
    result = await tool.execute({
        "content": "Great point! This aligns with my thoughts on decentralization.",
        "quoted_cast_hash": "0xoriginalcast456",
        "channel": "dev"
    }, context)
    
    logger.info(f"Quote tool result: {result}")
    assert result["status"] == "success"
    assert "Successfully posted quote cast" in result["message"]
    mock_observer.quote_cast.assert_called_once_with(
        "Great point! This aligns with my thoughts on decentralization.",
        "0xoriginalcast456",
        "dev"
    )


async def test_error_handling():
    """Test error handling in the tools"""
    # Test with no observer
    context = ActionContext(
        farcaster_observer=None,
        matrix_observer=None,
        world_state_manager=None,
        context_manager=None
    )
    
    like_tool = LikeFarcasterPostTool()
    result = await like_tool.execute({"cast_hash": "0x123"}, context)
    assert result["status"] == "failure"
    assert "not configured" in result["error"]
    
    # Test with missing parameters
    mock_observer = AsyncMock()
    context = ActionContext(
        farcaster_observer=mock_observer,
        matrix_observer=None,
        world_state_manager=None,
        context_manager=None
    )
    
    quote_tool = QuoteFarcasterPostTool()
    result = await quote_tool.execute({"content": "test"}, context)  # Missing quoted_cast_hash
    assert result["status"] == "failure"
    assert "Missing required parameters" in result["error"]


async def main():
    """Run all tests"""
    logger.info("Testing new Farcaster tools...")
    
    await test_like_tool()
    logger.info("✅ Like tool test passed")
    
    await test_quote_tool()
    logger.info("✅ Quote tool test passed")
    
    await test_error_handling()
    logger.info("✅ Error handling test passed")
    
    logger.info("🎉 All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
