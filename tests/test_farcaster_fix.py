#!/usr/bin/env python3
"""
Test script to verify the Farcaster empty content fix works.
"""
import asyncio
import logging
import pytest
from unittest.mock import AsyncMock, MagicMock

from chatbot.tools.base import ActionContext
from chatbot.tools.farcaster_tools import SendFarcasterPostTool


@pytest.mark.asyncio
async def test_farcaster_empty_content_with_image():
    """Test that Farcaster posting works with empty content when image is provided."""
    
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Create mock context
    context = ActionContext()
    context.farcaster_observer = AsyncMock()
    # Ensure no post_queue attribute to avoid scheduling path
    if hasattr(context.farcaster_observer, 'post_queue'):
        delattr(context.farcaster_observer, 'post_queue')
    context.farcaster_observer.post_cast = AsyncMock(return_value={
        "success": True,
        "cast": {"hash": "0x123456"}
    })
    
    # Mock world state manager
    context.world_state_manager = MagicMock()
    context.world_state_manager.has_sent_farcaster_post = MagicMock(return_value=False)
    context.world_state_manager.add_action_result = MagicMock(return_value="action_123")
    
    # Create tool instance
    tool = SendFarcasterPostTool()
    
    # Test parameters with empty content but with embed URL
    params = {
        "content": "",  # Empty content - this was causing the failure before
        "embed_url": "https://arweave.net/example_image_id"
    }
    
    # Execute the tool
    result = await tool.execute(params, context)
    
    print(f"Result: {result}")
    
    # Check that it succeeded
    assert result["status"] == "success", f"Expected success, got: {result}"
    
    # Verify that post_cast was called with non-empty content
    context.farcaster_observer.post_cast.assert_called_once()
    call_args = context.farcaster_observer.post_cast.call_args
    posted_content = call_args[1]["content"]
    
    print(f"Posted content: '{posted_content}'")
    
    # Verify content is not empty (should be emoji)
    assert posted_content, "Content should not be empty after processing"
    assert posted_content == "📎", f"Expected clip emoji content, got: '{posted_content}'"
    
    print("✅ Test passed! Empty content with image now works correctly.")


@pytest.mark.asyncio
async def test_farcaster_no_content_no_media_fails():
    """Test that Farcaster posting fails when no content and no media."""
    
    # Create mock context
    context = ActionContext()
    context.farcaster_observer = AsyncMock()
    
    # Create tool instance
    tool = SendFarcasterPostTool()
    
    # Test parameters with no content and no media
    params = {
        "content": ""  # Empty content with no media - should fail
    }
    
    # Execute the tool
    result = await tool.execute(params, context)
    
    print(f"Result: {result}")
    
    # Check that it failed as expected
    assert result["status"] == "failure", f"Expected failure, got: {result}"
    assert "content required when no embed is attached" in result["error"]
    
    print("✅ Test passed! No content + no media correctly fails.")


if __name__ == "__main__":
    asyncio.run(test_farcaster_empty_content_with_image())
    asyncio.run(test_farcaster_no_content_no_media_fails())
    print("🎉 All tests passed!")
